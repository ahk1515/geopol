# =============================================================
# GÉOPOL — ETL Dette bilatérale (World Bank IDS)
# Source : International Debt Statistics (IDS) — source ID 6
# Doc : https://worldbank.github.io/debt-data/api-guide/
#
# Indicateurs importés (subcategory_1) :
#   DT.DOD.BLAT.CD → bilaterale
#   DT.DOD.MLAT.CD → multilaterale
#   DT.DOD.PBND.CD → obligations_privees
#   DT.DOD.PROP.CD → crediteurs_prives
#
# Schéma flux :
#   country_from = pays créditeur (ISO3)
#   country_to   = pays débiteur (ISO3)
#   indicator    = dette_exterieure
#   subcategory_1 = type de créditeur
#
# Limite : couvre uniquement les pays débiteurs
# à revenus faibles/intermédiaires (DRS)
# =============================================================

import requests
import sqlite3
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
IDS_API_BASE = "https://api.worldbank.org/v2/sources/6"
WB_API_BASE  = "https://api.worldbank.org/v2"
SOURCE       = "Banque Mondiale IDS"
PAUSE        = 0.5
PER_PAGE     = 32000

# Indicateurs IDS à importer
IDS_INDICATORS = {
    "DT.DOD.BLAT.CD": "bilaterale",
    "DT.DOD.MLAT.CD": "multilaterale",
    "DT.DOD.PBND.CD": "obligations_privees",
    "DT.DOD.PROP.CD": "crediteurs_prives",
}

# Correspondance manuelle codes numériques IDS → ISO3
# pour les principaux créditeurs (complétée dynamiquement)
CREDITOR_ISO3_MAP = {
    "001": "AUT", "002": "BEL", "003": "DNK", "004": "FRA",
    "005": "DEU", "006": "ITA", "007": "NLD", "008": "NOR",
    "009": "PRT", "010": "SWE", "011": "CHE", "012": "GBR",
    "013": "CAN", "014": "USA", "015": "JPN", "016": "FIN",
    "017": "AUS", "018": "NZL", "019": "ESP", "020": "GRC",
    "021": "IRL", "742": "CHN", "730": "KOR", "566": "RUS",
    "682": "SAU", "356": "IND", "076": "BRA", "484": "MEX",
    "710": "ZAF", "792": "TUR", "818": "EGY", "012": "DZA",
    "504": "MAR",
}

# -------------------------------------------------------------
# CHARGEMENT TABLE DE CORRESPONDANCE CRÉDITEURS
# -------------------------------------------------------------

def load_creditor_codes():
    """
    Charge la table complète des codes créditeurs IDS depuis l'API.
    Complète CREDITOR_ISO3_MAP avec une correspondance nom → ISO3
    via l'API WB standard.
    """
    print("  Chargement des codes créditeurs IDS...")
    creditor_names = {}  # code_num → nom

    page = 1
    while True:
        url = f"{IDS_API_BASE}/counterpart-area?per_page=300&format=json&page={page}"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            variables = data["source"][0]["concept"][0]["variable"]
            for v in variables:
                creditor_names[v["id"]] = v["value"]
            total_pages = data["pages"]
            if page >= total_pages:
                break
            page += 1
            time.sleep(PAUSE)
        except Exception as e:
            print(f"  ⚠️  Erreur chargement créditeurs page {page} : {e}")
            break

    print(f"  {len(creditor_names)} codes créditeurs chargés.")

    # Enrichir avec correspondance nom → ISO3 via API WB
    name_to_iso3 = load_name_to_iso3()
    for code, name in creditor_names.items():
        if code not in CREDITOR_ISO3_MAP:
            iso3 = name_to_iso3.get(name.lower())
            if iso3:
                CREDITOR_ISO3_MAP[code] = iso3

    return creditor_names


def load_name_to_iso3():
    """
    Charge la liste des pays WB pour faire correspondance nom → ISO3.
    """
    url = f"{WB_API_BASE}/country?format=json&per_page=300"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {
            c["name"].lower(): c["iso2Code"] and c.get("id", "")
            for c in data[1]
            if c.get("capitalCity")
        }
    except Exception:
        return {}


# -------------------------------------------------------------
# CHARGEMENT LISTE DES PAYS DÉBITEURS
# -------------------------------------------------------------

def load_debtor_countries():
    """
    Charge la liste des pays débiteurs IDS (pays DRS).
    """
    url = f"{IDS_API_BASE}/country?per_page=300&format=json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        countries = data["source"][0]["concept"][0]["variable"]
        # Retourne les codes ISO3/WB des pays débiteurs
        return [c["id"] for c in countries if len(c["id"]) == 3]
    except Exception as e:
        print(f"  ⚠️  Erreur chargement pays débiteurs : {e}")
        return []


# -------------------------------------------------------------
# FETCH DONNÉES IDS
# -------------------------------------------------------------

def fetch_ids(debtor_iso3, series_code, annee_debut, annee_fin):
    """
    Récupère les données IDS bilatérales pour un pays débiteur.
    Retourne une liste de dicts {creditor_code, year, value}.
    """
    # time/all puis filtre Python (filtre temporel non supporté par cette API)
    url = (
        f"{IDS_API_BASE}/country/{debtor_iso3}"
        f"/series/{series_code}"
        f"/counterpart-area/all"
        f"/time/all"
        f"?format=json&per_page={PER_PAGE}"
    )

    rows = []
    page = 1

    while True:
        try:
            resp = requests.get(f"{url}&page={page}", timeout=60)
            resp.raise_for_status()
            data = resp.json()

            entries = data.get("source", [{}])[0].get("data", [])
            for entry in entries:
                if entry.get("value") is None:
                    continue  # Règle transparence

                variables = {v["concept"]: v for v in entry["variable"]}
                creditor_code = variables.get("Counterpart-Area", {}).get("id")
                year_str      = variables.get("Time", {}).get("id", "")

                if not creditor_code or not year_str.startswith("YR"):
                    continue

                try:
                    year  = int(year_str[2:])
                    value = float(entry["value"])
                except (ValueError, TypeError):
                    continue

                if value <= 0:
                    continue  # ignorer les dettes nulles

                rows.append({
                    "creditor_code": creditor_code,
                    "year":          year,
                    "value":         value,
                })

            total_pages = data.get("pages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(PAUSE)

        except Exception as e:
            print(f"  ⚠️  Erreur {debtor_iso3}/{series_code} page {page} : {e}")
            break

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


def upsert_rows(conn, debtor_iso3, subcategory, rows):
    data = []
    for row in rows:
        creditor_iso3 = CREDITOR_ISO3_MAP.get(row["creditor_code"])
        if not creditor_iso3:
            continue  # créditeur non identifié → on ignore

        data.append((
            creditor_iso3,   # country_from = créditeur
            debtor_iso3,     # country_to   = débiteur
            "dette_exterieure",
            row["year"],
            row["value"],
            "USD",
            SOURCE,
            subcategory,
            None,
            None,
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
    print("ETL — Dette bilatérale (World Bank IDS)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    # Chargement des référentiels
    load_creditor_codes()

    print("\nChargement des pays débiteurs...")
    debtor_countries = load_debtor_countries()
    print(f"{len(debtor_countries)} pays débiteurs trouvés.")

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)
    total_insere = 0

    for i, debtor in enumerate(debtor_countries):
        print(f"\n→ {debtor} ({i+1}/{len(debtor_countries)})")

        for series_code, subcategory in IDS_INDICATORS.items():
            rows = fetch_ids(debtor, series_code, ANNEE_DEBUT, ANNEE_FIN)
            if not rows:
                continue
            nb = upsert_rows(conn, debtor, subcategory, rows)
            total_insere += nb
            print(f"  {subcategory} : {nb} lignes")

        time.sleep(PAUSE)

    conn.close()
    print(f"\n{'='*60}")
    print(f"IDS terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
