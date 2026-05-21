# =============================================================
# GÉOPOL — ETL Comtrade (Commerce bilatéral)
# API : https://comtradeplus.un.org/
# Doc : https://comtradedeveloper.un.org/
# Nécessite une clé gratuite : COMTRADE_API_KEY dans les secrets
#
# STRATÉGIE DE REPRISE :
# Un fichier checkpoint.json enregistre la progression.
# Si le script est interrompu, il repart où il s'était arrêté.
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
API_BASE        = "https://comtradeapi.un.org/data/v1/get"
SOURCE          = "UN Comtrade"
PAUSE           = 2.0     # secondes entre requêtes
PAUSE_RATE      = 60.0    # pause si rate limit atteint
MAX_RETRIES     = 3       # tentatives par requête
PATH_CHECKPOINT = os.path.join(DIR_ETL, "comtrade_checkpoint.json")

# Sections HS niveau 2 (codes 2 chiffres)
# 01-97 couvrent l'ensemble des marchandises
HS2_SECTIONS = [str(i).zfill(2) for i in range(1, 98)]

# Flows : X = Export, M = Import
FLOWS = {"X": "export_commercial", "M": "import_commercial"}

# -------------------------------------------------------------
# CHECKPOINT — stratégie de reprise
# -------------------------------------------------------------

def load_checkpoint():
    """Charge la progression sauvegardée."""
    if os.path.exists(PATH_CHECKPOINT):
        with open(PATH_CHECKPOINT, "r") as f:
            return json.load(f)
    return {"done_reporters": [], "current_reporter": None}


def save_checkpoint(done_reporters, current_reporter=None):
    """Sauvegarde la progression après chaque pays traité."""
    with open(PATH_CHECKPOINT, "w") as f:
        json.dump({
            "done_reporters":    done_reporters,
            "current_reporter":  current_reporter,
        }, f)


def clear_checkpoint():
    """Supprime le checkpoint quand tout est terminé."""
    if os.path.exists(PATH_CHECKPOINT):
        os.remove(PATH_CHECKPOINT)


# -------------------------------------------------------------
# RÉCUPÉRATION LISTE DES PAYS
# -------------------------------------------------------------

def get_reporter_codes(api_key):
    """
    Récupère la liste des pays déclarants depuis l'API Comtrade.
    Retourne une liste de codes numériques.
    """
    url = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
    try:
        resp = requests.get(url, headers={"Ocp-Apim-Subscription-Key": api_key}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # On exclut les agrégats (id > 900 = zones économiques spéciales)
        return [
            str(r["id"]) for r in data.get("results", [])
            if r.get("isGroup") is False and int(r["id"]) < 900
        ]
    except Exception as e:
        print(f"  ⚠️  Erreur récupération pays : {e}")
        return []


# -------------------------------------------------------------
# APPEL API COMTRADE
# -------------------------------------------------------------

def fetch_trade(api_key, reporter, flow_code, year, hs2_list):
    """
    Récupère les flux commerciaux d'un pays pour une année.
    Retourne une liste de dicts.
    Gère les retries et le rate limiting.
    """
    # On regroupe les sections HS en une seule requête (max 20 codes)
    BATCH_HS = 20
    rows = []

    for i in range(0, len(hs2_list), BATCH_HS):
        batch = hs2_list[i:i + BATCH_HS]
        cmd_code = ",".join(batch)

        params = {
            "typeCode":     "C",          # marchandises
            "freqCode":     "A",          # annuel
            "clCode":       "HS",         # classification HS
            "period":       str(year),
            "reporterCode": reporter,
            "partnerCode":  "ALL",        # tous les partenaires
            "partner2Code": "0",
            "cmdCode":      cmd_code,
            "flowCode":     flow_code,
            "customsCode":  "C00",
            "motCode":      "0",
        }

        headers = {"Ocp-Apim-Subscription-Key": api_key}

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(API_BASE, params=params, headers=headers, timeout=60)

                # Rate limit atteint
                if resp.status_code == 429:
                    print(f"  ⏳ Rate limit — pause {PAUSE_RATE}s")
                    time.sleep(PAUSE_RATE)
                    continue

                resp.raise_for_status()
                data = resp.json()

                for entry in data.get("data", []):
                    partner_iso3 = entry.get("partnerISO", "").strip()
                    hs2          = str(entry.get("cmdCode", "")).zfill(2)[:2]
                    value        = entry.get("primaryValue")

                    # Règle transparence : valeur absente → on ignore
                    if not partner_iso3 or len(partner_iso3) != 3:
                        continue
                    if value is None:
                        continue

                    rows.append({
                        "partner_iso3": partner_iso3,
                        "hs2":          hs2,
                        "value":        float(value),
                    })
                break  # succès → sortir des retries

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(PAUSE * 2)
                else:
                    print(f"  ⚠️  Échec après {MAX_RETRIES} tentatives : {e}")

        time.sleep(PAUSE)

    return rows


# -------------------------------------------------------------
# INSERTION EN BASE
# -------------------------------------------------------------

def ensure_flux_table(conn):
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


def upsert_flux_rows(conn, reporter_iso3, flow_indicator, year, rows):
    """
    Insère ou remplace les lignes dans la table flux.
    Pour exports : country_from = reporter, country_to = partner
    Pour imports : country_from = partner, country_to = reporter
    """
    is_export = (flow_indicator == "export_commercial")
    data = []

    for row in rows:
        if is_export:
            country_from = reporter_iso3
            country_to   = row["partner_iso3"]
        else:
            country_from = row["partner_iso3"]
            country_to   = reporter_iso3

        data.append((
            country_from,
            country_to,
            flow_indicator,
            year,
            row["value"],
            "USD",
            SOURCE,
            row["hs2"],   # subcategory_1 = section HS niveau 2
            None,
            None,
        ))

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
    api_key = os.environ.get("COMTRADE_API_KEY")
    if not api_key:
        print("⏭️  COMTRADE_API_KEY manquante — source ignorée.")
        print("   Ajoute-la dans les secrets GitHub Actions pour activer.")
        return 0

    print("=" * 60)
    print("ETL — UN Comtrade (Commerce bilatéral)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    # Chargement checkpoint
    checkpoint     = load_checkpoint()
    done_reporters = checkpoint["done_reporters"]
    if done_reporters:
        print(f"  ↩️  Reprise — {len(done_reporters)} pays déjà traités")

    # Liste des pays
    print("\nRécupération des pays déclarants...")
    all_reporters = get_reporter_codes(api_key)
    remaining     = [r for r in all_reporters if r not in done_reporters]
    print(f"{len(all_reporters)} pays trouvés, {len(remaining)} restants.")

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)

    total_insere = 0

    for reporter in remaining:
        print(f"\n→ Pays {reporter} ({done_reporters.__len__() + 1}/{len(all_reporters)})")
        save_checkpoint(done_reporters, current_reporter=reporter)

        for year in range(ANNEE_DEBUT, ANNEE_FIN + 1):
            for flow_code, indicator in FLOWS.items():
                rows = fetch_trade(api_key, reporter, flow_code, year, HS2_SECTIONS)
                if not rows:
                    continue

                # On a besoin de l'ISO3 du reporter
                # Comtrade renvoie le code numérique — on cherche l'ISO3
                # depuis les données reçues (le reporter apparaît comme partenaire
                # dans les données des autres pays — ici on utilise une table
                # de correspondance simplifiée via l'API metadata)
                reporter_iso3 = get_iso3_from_numeric(reporter, api_key)
                if not reporter_iso3:
                    continue

                nb = upsert_flux_rows(conn, reporter_iso3, indicator, year, rows)
                total_insere += nb
                print(f"  {flow_code} {year} — {nb} lignes")

        done_reporters.append(reporter)
        save_checkpoint(done_reporters)

    conn.close()
    clear_checkpoint()

    print(f"\n{'='*60}")
    print(f"Comtrade terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


# Cache ISO3 pour éviter de rappeler l'API à chaque pays
_iso3_cache = {}

def get_iso3_from_numeric(numeric_code, api_key):
    """Convertit un code numérique Comtrade en ISO3."""
    if numeric_code in _iso3_cache:
        return _iso3_cache[numeric_code]
    try:
        url = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
        resp = requests.get(url, headers={"Ocp-Apim-Subscription-Key": api_key}, timeout=30)
        data = resp.json()
        for r in data.get("results", []):
            _iso3_cache[str(r["id"])] = r.get("iso3")
    except Exception:
        pass
    return _iso3_cache.get(numeric_code)


if __name__ == "__main__":
    run()
