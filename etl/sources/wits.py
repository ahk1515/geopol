# =============================================================
# GÉOPOL — ETL WITS (World Integrated Trade Solution)
# API : https://wits.worldbank.org/API/V1/
# Doc : https://wits.worldbank.org/witsapiintro.aspx
#
# Pourquoi WITS plutôt que COMTRADE direct :
#   - WITS pompe les données UN COMTRADE en sous-main
#   - API gratuite, sans clé requise
#   - Plus généreuse en débit que l'API Comtrade publique
#
# STRATÉGIE :
#   On ne télécharge QUE les imports déclarés par chaque pays reporter.
#   Convention internationale (UN/FMI) : les imports sont plus fiables
#   (douanes du pays importateur = intérêt fiscal direct, donc surveillance).
#   Pour chaque flux import enregistré, on génère AUSSI la ligne export
#   miroir (P→R = même valeur que R imports from P). Couvre les deux sens
#   sans doubler le nombre de requêtes API.
#
# GRANULARITÉ :
#   Total marchandises (subcategory_1 = 'total'), pas de détail HS.
#   Cohérent avec l'usage actuel de l'app (chiffre agrégé par couple/an).
#
# REPRISE :
#   checkpoint après chaque reporter. Reprise transparente sur incident.
# =============================================================

import requests
import sqlite3
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB, DIR_ETL

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------

# Endpoint SDMX-JSON pour données commerce stats trade
# Format : .../datasource/tradestats-trade/reporter/{reporter}/year/all/partner/all/product/all/indicator/MPRT-TRD-VL
#   tradestats-trade  = jeu de données "Trade Stats Trade"
#   MPRT-TRD-VL       = "Merchandise import trade value" (valeur imports marchandises en USD)
#   product=all       = toutes marchandises confondues (granularité totale)
#   partner=all       = par partenaire
#   year=all          = toutes années (filtrées ensuite côté Python)
# Le format JSON retourne les obs dans dataSets[0].series[<key>].observations
API_BASE       = "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade"
INDICATOR_CODE = "MPRT-TRD-VL"   # Merchandise Imports Trade Value (USD)
SOURCE         = "WITS (UN Comtrade)"
PAUSE          = 1.2     # secondes entre requêtes — confortable
PAUSE_RATE     = 60.0    # pause longue si rate limit
MAX_RETRIES    = 3       # tentatives par requête

PATH_CHECKPOINT = os.path.join(DIR_ETL, "wits_checkpoint.json")

# Subcategory sentinelle : la PK de la table flux inclut subcategory_1,
# et NULL ne déclenche pas l'unicité côté SQLite. On utilise 'total' pour
# marquer qu'il s'agit d'un total marchandises, distinct des éventuelles
# entrées HS2 héritées de Comtrade ('01'..'97').
SUBCAT_TOTAL   = "total"

# -------------------------------------------------------------
# CHECKPOINT — stratégie de reprise
# -------------------------------------------------------------

def load_checkpoint():
    """Charge la progression sauvegardée."""
    if os.path.exists(PATH_CHECKPOINT):
        try:
            with open(PATH_CHECKPOINT, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"done_reporters": []}


def save_checkpoint(done_reporters):
    """Sauvegarde la progression après chaque pays traité."""
    with open(PATH_CHECKPOINT, "w") as f:
        json.dump({"done_reporters": done_reporters}, f)


def clear_checkpoint():
    """Nettoie le checkpoint à la fin d'un run complet."""
    if os.path.exists(PATH_CHECKPOINT):
        os.remove(PATH_CHECKPOINT)


# -------------------------------------------------------------
# LISTE DES REPORTERS
# -------------------------------------------------------------
# WITS attend des codes ISO3 standard (contrairement à COMTRADE qui veut du M49 numérique).
# On utilise la liste des pays déjà présents dans la table 'pays' de la DB pour rester
# cohérent avec le reste de l'ETL (et éviter les codes WITS exotiques type 'EUN').

def get_reporters_from_db():
    """Retourne la liste des ISO3 des pays connus de la DB."""
    if not os.path.exists(PATH_DB):
        # Premier run, pas de DB encore : on utilisera la liste WITS officielle
        return None
    conn = sqlite3.connect(PATH_DB)
    try:
        rows = conn.execute("SELECT DISTINCT iso3 FROM pays WHERE iso3 IS NOT NULL").fetchall()
        return sorted([r[0] for r in rows if r[0] and len(r[0]) == 3])
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def get_reporters_from_wits():
    """Fallback : récupère la liste des reporters depuis WITS si la DB n'a pas encore de pays."""
    url = "https://wits.worldbank.org/API/V1/SDMX/V21/codelist/all/CL_COUNTRY_WITS"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        # WITS renvoie du SDMX-JSON : codes dans Structure.Codelists.Codelist[0].Code
        data = resp.json()
        codes = data.get("Structure", {}).get("Codelists", {}).get("Codelist", [{}])[0].get("Code", [])
        # On garde uniquement les ISO3 (3 lettres, pas les groupes type 'EUN')
        return sorted([c.get("@value") for c in codes if c.get("@value") and len(c.get("@value", "")) == 3])
    except Exception as e:
        print(f"  ⚠️  Impossible de récupérer la liste WITS : {e}")
        return []


# -------------------------------------------------------------
# RÉCUPÉRATION DES DONNÉES PAR REPORTER
# -------------------------------------------------------------

def fetch_imports_for_reporter(reporter_iso3, year_min, year_max):
    """
    Récupère TOUS les imports d'un pays reporter sur la période demandée,
    par partenaire, en un seul appel API.

    Retourne une liste de dicts : [{partner_iso3, year, value}].
    Les valeurs sont en USD (déclarations douanières du reporter).
    """
    url = (
        f"{API_BASE}/reporter/{reporter_iso3}"
        f"/year/all/partner/all/product/all/indicator/{INDICATOR_CODE}"
        f"?format=JSON"
    )

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 429:
                # Rate limit
                print(f"  ⏳ Rate limit (429) — pause {PAUSE_RATE}s")
                time.sleep(PAUSE_RATE)
                continue
            if resp.status_code == 404:
                # Pays inconnu de WITS ou pas de données
                return []
            resp.raise_for_status()
            data = resp.json()
            return parse_sdmx_response(data, reporter_iso3, year_min, year_max)
        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"  ⚠️  Tentative {attempt+1}/{MAX_RETRIES} échouée : {e}")
            time.sleep(PAUSE * (attempt + 1))
        except Exception as e:
            print(f"  ❌ Erreur fetch {reporter_iso3} : {e}")
            return []

    print(f"  ❌ Abandon {reporter_iso3} après {MAX_RETRIES} tentatives")
    return []


def parse_sdmx_response(data, reporter_iso3, year_min, year_max):
    """
    Parse la réponse SDMX-JSON de WITS.

    Structure attendue :
      dataSets[0].series : dict { "0:0:0:0:0:0" : { observations: { "0": [value, ...], ... } } }
      structure.dimensions.series : liste des dimensions (REPORTER, PARTNER, PRODUCT, INDICATOR, FREQ)
      structure.dimensions.observation : observation (TIME_PERIOD = année)
    Chaque clé "i:j:k:l:m" pointe vers une combinaison reporter/partner/product/etc.,
    où chaque entier est un index dans la liste des valeurs de cette dimension.
    """
    rows = []
    try:
        datasets = data.get("dataSets", [])
        structure = data.get("structure", {})
        if not datasets or not structure:
            return []

        series = datasets[0].get("series", {})
        dim_series = structure.get("dimensions", {}).get("series", [])
        dim_obs = structure.get("dimensions", {}).get("observation", [])

        # Trouver l'index de la dimension PARTNER
        partner_dim_idx = None
        for i, d in enumerate(dim_series):
            if d.get("id") in ("PARTNER", "Partner"):
                partner_dim_idx = i
                break
        if partner_dim_idx is None:
            return []

        # Récupérer la liste des partenaires (index → ISO3)
        partner_values = dim_series[partner_dim_idx].get("values", [])

        # Récupérer la liste des années (dimension d'observation)
        year_values = []
        for d in dim_obs:
            if d.get("id") in ("TIME_PERIOD", "Year"):
                year_values = d.get("values", [])
                break

        # Parser chaque série
        for series_key, series_data in series.items():
            indices = series_key.split(":")
            if partner_dim_idx >= len(indices):
                continue
            partner_idx = int(indices[partner_dim_idx])
            if partner_idx >= len(partner_values):
                continue
            partner_iso3 = partner_values[partner_idx].get("id") or partner_values[partner_idx].get("@id")
            if not partner_iso3 or len(partner_iso3) != 3:
                continue   # On ignore les agrégats régionaux type 'WLD', 'EUN', etc.
            if partner_iso3 == reporter_iso3:
                continue   # auto-flux

            observations = series_data.get("observations", {})
            for obs_idx_str, obs_val in observations.items():
                obs_idx = int(obs_idx_str)
                if obs_idx >= len(year_values):
                    continue
                year_str = year_values[obs_idx].get("id") or year_values[obs_idx].get("@id")
                if not year_str:
                    continue
                try:
                    year = int(year_str)
                except ValueError:
                    continue
                if year < year_min or year > year_max:
                    continue

                # obs_val est typiquement une liste [valeur, ...] ; la valeur est en USD
                if isinstance(obs_val, list) and obs_val:
                    value = obs_val[0]
                else:
                    value = obs_val
                if value is None:
                    continue
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    continue
                if value <= 0:
                    continue

                rows.append({
                    "partner_iso3": partner_iso3,
                    "year":         year,
                    "value":        value,
                })
    except Exception as e:
        print(f"  ⚠️  Parse error : {e}")
        return []
    return rows


# -------------------------------------------------------------
# TABLE FLUX
# -------------------------------------------------------------

def ensure_flux_table(conn):
    """Crée la table flux si elle n'existe pas. Schéma identique aux autres parsers."""
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
    Pour chaque ligne (import déclaré par le reporter) :
      - Insère 'import_commercial' avec country_to = reporter, country_from = partner
      - Insère AUSSI 'export_commercial' miroir avec country_to = partner, country_from = reporter
        (même valeur — par convention, import déclaré = export inverse présumé)

    Cela couvre les 2 sens du commerce sans dupliquer les appels API et garantit
    que l'app fonctionne sans modification (elle interroge les deux indicators).
    """
    data = []
    for row in rows:
        partner = row["partner_iso3"]
        year    = row["year"]
        value   = row["value"]

        # Ligne import : R importe X de P
        data.append((
            partner,            # country_from = partenaire (fournisseur)
            reporter_iso3,      # country_to   = reporter (importateur)
            "import_commercial",
            year, value, "USD", SOURCE, SUBCAT_TOTAL, None, None,
        ))
        # Ligne export miroir : P exporte X vers R (même valeur)
        data.append((
            partner,            # country_from = partenaire (exportateur)
            reporter_iso3,      # country_to   = reporter (destinataire)
            "export_commercial",
            year, value, "USD", SOURCE, SUBCAT_TOTAL, None, None,
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
    print("ETL — WITS (Commerce bilatéral, imports déclarés)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    # 1) Liste des reporters
    reporters = get_reporters_from_db()
    if not reporters:
        print("  ↪️  Liste pays DB vide, fallback sur catalogue WITS…")
        reporters = get_reporters_from_wits()
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

    # 4) Avant de commencer, nettoyer les anciennes lignes WITS pour la période
    # (évite les vestiges d'un run précédent en cas de changement de partenaires).
    # On ne supprime QUE les lignes source = WITS (les lignes Comtrade existantes sont préservées).
    if not done_reporters:
        print("  🧹 Nettoyage des anciennes lignes WITS pour la période…")
        conn.execute(
            "DELETE FROM flux WHERE source = ? AND year BETWEEN ? AND ?",
            (SOURCE, ANNEE_DEBUT, ANNEE_FIN),
        )
        conn.commit()

    total_insere = 0

    # 5) Boucle principale
    for i, reporter in enumerate(remaining, start=1):
        global_idx = len(done_reporters) + 1
        print(f"\n→ {reporter} ({global_idx}/{len(reporters)})")
        time.sleep(PAUSE)

        rows = fetch_imports_for_reporter(reporter, ANNEE_DEBUT, ANNEE_FIN)
        if rows:
            nb = upsert_flux_rows(conn, reporter, rows)
            total_insere += nb
            print(f"  ✓ {len(rows)} obs → {nb} lignes insérées (import + miroir export)")
        else:
            print(f"  ∅ aucune donnée")

        done_reporters.append(reporter)
        save_checkpoint(done_reporters)

    conn.close()
    clear_checkpoint()

    print(f"\n{'='*60}")
    print(f"WITS terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
