# =============================================================
# GÉOPOL — ETL IMF IMTS (International Trade in Goods by partner)
# API : https://api.imf.org/external/sdmx/3.0/
# Doc : https://data.imf.org/en/Resource-Pages/IMF-API
# Dataset : IMTS (ex-DOTS, renommé en septembre 2025)
#
# Pourquoi IMF IMTS plutôt que COMTRADE/WITS direct :
#   - API officielle, gratuite, sans clé requise (auth optionnelle)
#   - Endpoint actif, maintenu, et documenté (vs DOTS legacy déprécié en 2025)
#   - Couvre 1948-aujourd'hui pour ~220 pays
#   - Données primaires : agrégat USD par couple/an, exactement ce qu'on veut
#   - Granularité totale (pas de HS — l'IMF ne publie PAS le commerce par produit ;
#     pour du détail HS il faudrait UN Comtrade / WITS, autre source)
#
# STRATÉGIE :
#   On télécharge UNIQUEMENT les imports déclarés par chaque pays reporter (MG_CIF_USD).
#   Convention internationale (UN/FMI) : les imports sont plus fiables
#   (douanes du pays importateur = intérêt fiscal direct, donc surveillance).
#   Pour chaque flux import enregistré, on génère AUSSI la ligne export miroir
#   (P→R = même valeur que R imports from P). Couvre les deux sens.
#
# OPTIMISATIONS :
#   - 1 requête par reporter (et non 220×220) grâce au wildcard partenaire '*'
#   - Format CSV (plus léger à parser que SDMX-JSON)
#   - Rate limit officiel : 10 req / 5s. On prend 0.6s entre 2 calls (marge confortable).
#   - Filtre seuil minimum 100 000 USD : élimine ~30% du bruit sans perte d'info utile.
#
# REPRISE :
#   Checkpoint après chaque reporter dans etl/imf_imts_checkpoint.json
#
# ─── NOTES DE MAINTENANCE (pièges validés en juin 2026) ──────────────
#   1) PARTENAIRE = '*' (wildcard). Laisser le slot VIDE ('..A') renvoie HTTP 200
#      mais ZÉRO ligne de données (seulement des métadonnées STRUCTURE). C'était
#      LE bug qui faisait "0 ligne, 20 reporters sans données".
#      La clé correcte est : {COUNTRY}.{INDICATOR}.*.{FREQUENCY}
#   2) SCALE : la colonne SCALE vaut 6 mais OBS_VALUE est DÉJÀ en USD bruts.
#      NE PAS multiplier par 10^SCALE. (Vérité-terrain : FRA->USA 2022 = 56 004 917 567
#      = ~56 Md USD, conforme à la réalité. Multiplier donnerait 5.6e16, absurde.)
#   3) Filtre temporel c[TIME_PERIOD]=ge:{année} INDISPENSABLE : sans lui, un seul
#      reporter renvoie ~16 Mo (toutes les années depuis 1948).
# =============================================================

import requests
import sqlite3
import json
import time
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB, DIR_ETL

# Pandas pour parser le CSV de l'API
try:
    import pandas as pd
except ImportError:
    pd = None

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------

API_BASE      = "https://api.imf.org/external/sdmx/3.0"
DATAFLOW      = "IMF.STA/IMTS/~"   # ~ = latest version
INDICATOR     = "MG_CIF_USD"       # imports CIF, USD (les exports seront déduits par miroir)
FREQUENCY     = "A"                # annuel
SOURCE        = "IMF IMTS"

# Rate limit officiel IMF : 10 req / 5s. On prend 0.6s entre 2 calls (marge sûre).
PAUSE         = 0.6
PAUSE_RATE    = 30.0   # pause longue si 429
MAX_RETRIES   = 3
TIMEOUT       = 90     # secondes par requête (une réponse '*' peut faire ~1 Mo)

PATH_CHECKPOINT = os.path.join(DIR_ETL, "imf_imts_checkpoint.json")

# Subcategory sentinelle : la PK de la table flux inclut subcategory_1, et NULL ne
# déclenche pas l'unicité côté SQLite. 'total' marque un total marchandises,
# distinct des éventuelles entrées HS2 héritées d'autres sources.
SUBCAT_TOTAL  = "total"

# Seuil minimum (USD) : élimine les flux insignifiants (< 100k USD).
# Une France-Andorre à 50k USD n'a pas d'utilité analytique mais pèse en volume.
# Avec ce seuil on perd ~30% des lignes en nombre, < 0.01% de la valeur totale.
SEUIL_MIN_USD = 100_000

# Codes d'agrégats IMF à exclure (non-pays). Format IMF : G001=World, G998=EU, etc.
# Tous ces codes commencent par 'G'. On les exclut systématiquement.
def _is_aggregate_code(code):
    if not code or len(code) != 3:
        return True
    if code[0] == 'G':   # codes IMF d'agrégats (G001, G998, etc.)
        return True
    return False

# -------------------------------------------------------------
# CHECKPOINT — stratégie de reprise
# -------------------------------------------------------------

def load_checkpoint():
    if os.path.exists(PATH_CHECKPOINT):
        try:
            with open(PATH_CHECKPOINT, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"done_reporters": []}


def save_checkpoint(done_reporters):
    with open(PATH_CHECKPOINT, "w") as f:
        json.dump({"done_reporters": done_reporters}, f)


def clear_checkpoint():
    if os.path.exists(PATH_CHECKPOINT):
        os.remove(PATH_CHECKPOINT)


# -------------------------------------------------------------
# LISTE DES REPORTERS
# -------------------------------------------------------------
# On utilise la liste des pays déjà présents dans la DB (table identite, alimentée
# par la Banque Mondiale qui passe AVANT IMF dans le PIPELINE). On reste tolérant :
# on essaie plusieurs schémas possibles, puis on retombe sur un fallback minimal.

def get_reporters_from_db():
    """
    Retourne la liste des ISO3 connus de la DB, ou None si indisponible.
    Essaie, dans l'ordre :
      1. table 'pays'      (colonne iso3)            — schéma historique éventuel
      2. table 'identite'  (colonne country_iso3)    — schéma réel actuel
    """
    if not os.path.exists(PATH_DB):
        return None
    conn = sqlite3.connect(PATH_DB)
    try:
        candidates = [
            ("pays", "iso3"),
            ("identite", "country_iso3"),
        ]
        for table, col in candidates:
            try:
                rows = conn.execute(
                    f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL"
                ).fetchall()
            except sqlite3.OperationalError:
                continue   # table ou colonne absente → on tente la suivante
            isos = sorted({
                r[0] for r in rows
                if r[0] and len(r[0]) == 3 and r[0].isalpha() and r[0].isupper()
            })
            if isos:
                print(f"  ✓ {len(isos)} reporters depuis la table '{table}'")
                return isos
        return None
    finally:
        conn.close()


# Fallback : si la DB n'a pas encore de pays (tout premier run à froid).
# La Banque Mondiale passe avant IMF dans le PIPELINE, donc en pratique
# get_reporters_from_db() devrait quasi toujours réussir. Ce fallback ne sert
# qu'au cas extrême d'une DB totalement vierge.
def get_reporters_fallback():
    """Liste minimale d'ISO3 si la DB n'a pas encore de pays."""
    return [
        'USA', 'CHN', 'JPN', 'DEU', 'IND', 'GBR', 'FRA', 'ITA', 'BRA', 'CAN',
        'RUS', 'KOR', 'AUS', 'ESP', 'MEX', 'IDN', 'NLD', 'SAU', 'TUR', 'CHE',
    ]


# -------------------------------------------------------------
# RÉCUPÉRATION DES DONNÉES PAR REPORTER
# -------------------------------------------------------------

def build_query_url(reporter_iso3, year_min):
    """
    Construit l'URL pour récupérer les imports d'un pays, tous partenaires.
    Format SDMX 3.0 :
      .../data/dataflow/{AGENCY}/{DATAFLOW}/{VERSION}/{KEY}
    KEY pour IMTS : {COUNTRY}.{INDICATOR}.{COUNTERPART_COUNTRY}.{FREQUENCY}
      - COUNTRY             = reporter (ex: FRA)
      - INDICATOR           = MG_CIF_USD (imports CIF en USD)
      - COUNTERPART_COUNTRY = '*'  → TOUS les partenaires (un slot vide ne marche PAS)
      - FREQUENCY           = A (annuel)
    Filtrage temporel : c[TIME_PERIOD]=ge:{YEAR}  (indispensable, voir notes en tête)
    """
    key = f"{reporter_iso3}.{INDICATOR}.*.{FREQUENCY}"
    # %5B / %5D = encodage URL des crochets [ ]
    return (
        f"{API_BASE}/data/dataflow/{DATAFLOW}/{key}"
        f"?c%5BTIME_PERIOD%5D=ge:{year_min}"
    )


def fetch_imports_for_reporter(reporter_iso3, year_min, year_max):
    """
    Récupère les imports d'un pays reporter, en CSV.
    Retourne une liste de dicts : [{partner_iso3, year, value}].
    """
    url = build_query_url(reporter_iso3, year_min)
    headers = {"Accept": "text/csv", "User-Agent": "geopol-etl/1.0"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 429:
                print(f"  ⏳ Rate limit (429) — pause {PAUSE_RATE}s")
                time.sleep(PAUSE_RATE)
                continue
            if resp.status_code == 404:
                # Reporter inconnu de l'API ou pas de données
                return []
            if resp.status_code != 200:
                print(f"  ⚠️  HTTP {resp.status_code} pour {reporter_iso3}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(PAUSE * (attempt + 2))
                    continue
                return []
            # Parser le CSV
            text = resp.text
            if not text or len(text) < 50:
                # Réponse vide ou trop courte : pas de données pour ce pays
                return []
            return parse_csv_response(text, reporter_iso3, year_min, year_max)
        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"  ⚠️  Tentative {attempt+1}/{MAX_RETRIES} : {e}")
            time.sleep(PAUSE * (attempt + 1))
        except Exception as e:
            print(f"  ❌ Erreur fetch {reporter_iso3} : {e}")
            return []

    print(f"  ❌ Abandon {reporter_iso3} après {MAX_RETRIES} tentatives")
    return []


def parse_csv_response(csv_text, reporter_iso3, year_min, year_max):
    """
    Parse la réponse CSV de l'API IMF.

    Format réel (validé juin 2026) — première colonne = 'STRUCTURE[;]' :
      STRUCTURE[;],STRUCTURE_ID,ACTION,COUNTRY,INDICATOR,COUNTERPART_COUNTRY,
      FREQUENCY,TIME_PERIOD,OBS_VALUE,SCALE,PRECISION,DECIMALS_DISPLAYED,
      TRADE_FLOW,VALUATION,UNIT,DERIVATION_TYPE,OVERLAP,STATUS
      dataflow,IMF.STA:IMTS(1.0.0),R,FRA,MG_CIF_USD,USA,A,2022,56004917567,6,...

    On lit par NOM de colonne (l'ordre peut varier). OBS_VALUE est en USD bruts
    (NE PAS appliquer SCALE — voir notes en tête de fichier).
    """
    if pd is not None:
        return _parse_with_pandas(csv_text, reporter_iso3, year_min, year_max)
    else:
        return _parse_without_pandas(csv_text, reporter_iso3, year_min, year_max)


def _parse_with_pandas(csv_text, reporter_iso3, year_min, year_max):
    """Parsing avec pandas (rapide, robuste, lecture par nom de colonne)."""
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:
        print(f"  ⚠️  Parse CSV pandas : {e}")
        return []
    if df.empty:
        return []
    # Vérifier colonnes critiques
    required = ['COUNTERPART_COUNTRY', 'TIME_PERIOD', 'OBS_VALUE']
    for col in required:
        if col not in df.columns:
            print(f"  ⚠️  Colonne manquante : {col} (présentes : {list(df.columns)})")
            return []

    rows = []
    for _, r in df.iterrows():
        partner = str(r['COUNTERPART_COUNTRY']).strip()
        if _is_aggregate_code(partner):
            continue   # exclure G001, G998, etc.
        if partner == reporter_iso3:
            continue   # auto-flux
        # TIME_PERIOD = "2020" pour l'annuel
        period = str(r['TIME_PERIOD']).strip()
        try:
            year = int(period.split('-')[0]) if '-' in period else int(period)
        except (ValueError, AttributeError):
            continue
        if year < year_min or year > year_max:
            continue
        try:
            value = float(r['OBS_VALUE'])
        except (ValueError, TypeError):
            continue
        if value < SEUIL_MIN_USD:
            continue   # seuil minimum, élimine le bruit
        rows.append({
            'partner_iso3': partner,
            'year':         year,
            'value':        value,
        })
    return rows


def _parse_without_pandas(csv_text, reporter_iso3, year_min, year_max):
    """Parser sans pandas (fallback, lecture par nom de colonne via DictReader)."""
    import csv
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for r in reader:
        partner = (r.get('COUNTERPART_COUNTRY') or '').strip()
        if _is_aggregate_code(partner) or partner == reporter_iso3:
            continue
        period = (r.get('TIME_PERIOD') or '').strip()
        try:
            year = int(period.split('-')[0]) if '-' in period else int(period)
        except ValueError:
            continue
        if year < year_min or year > year_max:
            continue
        try:
            value = float(r.get('OBS_VALUE') or 0)
        except ValueError:
            continue
        if value < SEUIL_MIN_USD:
            continue
        rows.append({'partner_iso3': partner, 'year': year, 'value': value})
    return rows


# -------------------------------------------------------------
# TABLE FLUX
# -------------------------------------------------------------

def ensure_flux_table(conn):
    """Crée la table flux si elle n'existe pas."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flux (
            country_from  TEXT,
            country_to    TEXT,
            indicator     TEXT,
            year          INTEGER,
            value         REAL,
            unit          TEXT,
            source        TEXT,
            subcategory_1 TEXT,
            subcategory_2 TEXT,
            subcategory_3 TEXT,
            PRIMARY KEY (country_from, country_to, indicator, year, subcategory_1)
        )
    """)
    conn.commit()


def upsert_flux_rows(conn, reporter_iso3, rows):
    """
    Pour chaque ligne (import déclaré par le reporter R, depuis le partenaire P) :

      Donnée brute : "R a importé X depuis P" (déclaration douanière de R)

      Conséquence : il y a 2 flux LOGIQUES (mais 1 seule réalité économique) :
        - Flux d'import : "R importe X depuis P"
        - Flux d'export : "P exporte X vers R" (même flux vu de l'autre côté)

      L'app distingue les deux via l'indicator + les colonnes :

         indicator = 'import_commercial' :
           subjectCol = country_to    → le sujet est l'IMPORTATEUR (qui reçoit le flux)
           partnerCol = country_from  → le partenaire est le fournisseur

         indicator = 'export_commercial' :
           subjectCol = country_from  → le sujet est l'EXPORTATEUR (qui envoie le flux)
           partnerCol = country_to    → le partenaire est le destinataire

      Donc pour qu'on retrouve dans l'app :
        - "France importe X depuis USA" : country_from=USA, country_to=FRA, indicator=import_commercial
        - "USA exporte X vers France"   : country_from=USA, country_to=FRA, indicator=export_commercial

      Les DEUX lignes ont la même paire (country_from, country_to) !
      Seul l'indicator change. C'est cohérent : c'est le même flux économique.
    """
    data = []
    for row in rows:
        partner = row['partner_iso3']
        year    = row['year']
        value   = row['value']
        # Vue "import" du flux : country_from=fournisseur(P), country_to=importateur(R)
        data.append((
            partner,        # country_from  (le partenaire est le fournisseur)
            reporter_iso3,  # country_to    (le reporter est l'importateur)
            'import_commercial',
            year, value, 'USD', SOURCE, SUBCAT_TOTAL, None, None,
        ))
        # Vue "export" du même flux : mêmes country_from/country_to.
        data.append((
            partner,        # country_from  (le partenaire est l'exportateur)
            reporter_iso3,  # country_to    (le reporter est le destinataire)
            'export_commercial',
            year, value, 'USD', SOURCE, SUBCAT_TOTAL, None, None,
        ))

    if not data:
        return 0
    conn.executemany("""
        INSERT OR REPLACE INTO flux
            (country_from, country_to, indicator, year, value,
             unit, source, subcategory_1, subcategory_2, subcategory_3)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, data)
    conn.commit()
    return len(data)


# -------------------------------------------------------------
# POINT D'ENTRÉE
# -------------------------------------------------------------

def run():
    print("=" * 60)
    print("ETL — IMF IMTS (Commerce bilatéral, imports déclarés)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print(f"Seuil minimum : {SEUIL_MIN_USD:,} USD")
    print("=" * 60)

    if pd is None:
        print("  ⚠️  pandas non disponible — utilisation du parser de secours (plus lent)")

    # 1) Liste des reporters
    reporters = get_reporters_from_db()
    if not reporters:
        print("  ↪️  Liste pays DB vide, fallback minimal")
        reporters = get_reporters_fallback()
    if not reporters:
        print("❌ Aucun reporter disponible, abandon.")
        return 0

    # 2) Checkpoint
    checkpoint     = load_checkpoint()
    done_reporters = checkpoint["done_reporters"]
    if done_reporters:
        print(f"  ↩️  Reprise — {len(done_reporters)} pays déjà traités")
    remaining = [r for r in reporters if r not in done_reporters]
    print(f"{len(reporters)} reporters au total, {len(remaining)} restants.")

    # 3) Préparer DB
    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)

    # 4) Au premier run (pas de checkpoint), nettoyer les anciennes lignes IMF IMTS
    # (évite les vestiges si on relance après changement de période ou de seuil).
    # On ne supprime QUE les lignes source = IMF IMTS, pas les autres parsers.
    if not done_reporters:
        print(f"  🧹 Nettoyage des anciennes lignes {SOURCE}…")
        conn.execute(
            "DELETE FROM flux WHERE source = ? AND year BETWEEN ? AND ?",
            (SOURCE, ANNEE_DEBUT, ANNEE_FIN),
        )
        conn.commit()

    total_insere = 0
    skipped = 0
    nb_reporters = len(reporters)

    # 5) Boucle principale
    for reporter in remaining:
        global_idx = len(done_reporters) + 1
        print(f"\n→ {reporter} ({global_idx}/{nb_reporters})")
        time.sleep(PAUSE)

        rows = fetch_imports_for_reporter(reporter, ANNEE_DEBUT, ANNEE_FIN)
        if rows:
            nb = upsert_flux_rows(conn, reporter, rows)
            total_insere += nb
            print(f"  ✓ {len(rows)} obs → {nb} lignes insérées (import + miroir export)")
        else:
            skipped += 1
            print(f"  ∅ aucune donnée")

        done_reporters.append(reporter)
        save_checkpoint(done_reporters)

    conn.close()
    clear_checkpoint()

    print(f"\n{'='*60}")
    print(f"IMF IMTS terminé")
    print(f"  • {total_insere} lignes insérées")
    print(f"  • {skipped} reporters sans données")
    print(f"  • {nb_reporters - skipped} reporters avec données")
    print(f"{'='*60}")

    # 6) GARDE-FOU ANTI-SILENCE.
    # Si AUCUNE ligne n'a été insérée alors qu'on avait des reporters à traiter,
    # c'est anormal (API en panne, format changé, codes invalides…). On lève une
    # exception pour que le run GitHub apparaisse en ÉCHEC (rouge) au lieu d'un
    # faux-succès "0 ligne". Conforme à la convention : erreur → raise Exception.
    # Note : on ne déclenche le garde-fou que si remaining n'était pas vide au départ
    # (sinon une reprise déjà complète depuis checkpoint serait considérée à tort
    #  comme un échec).
    if total_insere == 0 and remaining:
        raise Exception(
            "IMF IMTS : 0 ligne insérée pour "
            f"{len(remaining)} reporters traités. "
            "Anomalie probable (API/clé/format). Vérifier build_query_url et l'endpoint."
        )

    return total_insere


if __name__ == "__main__":
    run()
