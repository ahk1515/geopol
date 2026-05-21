# =============================================================
# GÉOPOL — ETL Étudiants internationaux (UNESCO UIS + OCDE)
# Fusion des deux sources : OCDE prioritaire, UNESCO en complément
#
# APIs :
#   OCDE : https://data.oecd.org/api/sdmx-json-documentation/
#          Gratuite, sans clé
#   UNESCO UIS : https://api.uis.unesco.org/
#                Gratuite, sans clé
#
# Logique de fusion :
#   1. Import UNESCO → insère toutes les données
#   2. Import OCDE   → INSERT OR REPLACE (prioritaire)
#   La colonne `source` trace l'origine de chaque ligne
# =============================================================

import requests
import sqlite3
import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
PAUSE         = 0.5
INDICATOR     = "etudiants_international"
UNIT          = "personnes"

SOURCE_UNESCO = "UNESCO UIS"
SOURCE_OCDE   = "OCDE"

# API OCDE — dataset étudiants internationaux par origine
# EAG_NEAC = Education at a Glance, enrolment by origin
OCDE_API_BASE = "https://sdmx.oecd.org/public/rest/data"
OCDE_DATASET  = "OECD.EDU.IMEP,DSD_EAG_UOE_NON_FINANCE@DF_UOE_ENRL_MOBILE,1.1"

# API UNESCO UIS
UIS_API_BASE  = "https://api.uis.unesco.org/api/public/data/indicators"
UIS_INDICATOR = "FOSGPNT"  # Inbound internationally mobile students by origin

# -------------------------------------------------------------
# HELPERS COMMUNS
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


def upsert_rows(conn, rows):
    """
    rows : liste de dicts {country_from, country_to, year, value, source}
    Règle fusion : INSERT OR REPLACE → OCDE écrase UNESCO.
    """
    data = [
        (
            row["country_from"],
            row["country_to"],
            INDICATOR,
            row["year"],
            row["value"],
            UNIT,
            row["source"],
            None, None, None,
        )
        for row in rows
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO flux
            (country_from, country_to, indicator, year, value,
             unit, source, subcategory_1, subcategory_2, subcategory_3)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, data)
    conn.commit()
    return len(data)


# -------------------------------------------------------------
# SOURCE 1 — UNESCO UIS
# -------------------------------------------------------------

def fetch_uis(annee_debut, annee_fin):
    """
    Récupère les étudiants internationaux entrants par pays d'origine
    depuis l'API UNESCO UIS.
    Retourne une liste de dicts.
    """
    rows = []
    params = {
        "indicatorCode": UIS_INDICATOR,
        "startYear":     annee_debut,
        "endYear":       annee_fin,
        "lang":          "en",
    }
    try:
        resp = requests.get(
            f"{UIS_API_BASE}/{UIS_INDICATOR}",
            params=params,
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()

        for entry in data.get("data", []):
            country_to   = entry.get("geoUnit", "").strip()   # pays d'accueil
            country_from = entry.get("origin", "").strip()    # pays d'origine
            year         = entry.get("year")
            value        = entry.get("value")

            if not country_to or not country_from or value is None:
                continue
            if len(country_to) != 3 or len(country_from) != 3:
                continue
            if year < annee_debut or year > annee_fin:
                continue

            rows.append({
                "country_from": country_from,
                "country_to":   country_to,
                "year":         int(year),
                "value":        float(value),
                "source":       SOURCE_UNESCO,
            })

    except Exception as e:
        print(f"  ⚠️  Erreur UNESCO UIS : {e}")

    return rows


# -------------------------------------------------------------
# SOURCE 2 — OCDE (SDMX-JSON)
# -------------------------------------------------------------

def fetch_oecd(annee_debut, annee_fin):
    """
    Récupère les étudiants internationaux par pays d'origine
    depuis l'API SDMX OCDE.
    Retourne une liste de dicts.
    """
    rows = []

    # Construction URL SDMX
    # Filtre : tous pays, tous origines, annuel, total niveaux
    period = f"{annee_debut},{annee_fin}"
    url = (
        f"{OCDE_API_BASE}/{OCDE_DATASET}"
        f"/A...TOTAL.ISCED11_5T8.VALUE"
        f"?startPeriod={annee_debut}&endPeriod={annee_fin}"
        f"&format=jsondata&dimensionAtObservation=AllDimensions"
    )

    try:
        resp = requests.get(url, timeout=120, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()

        # Parsing SDMX-JSON
        structure   = data.get("data", {}).get("structure", {})
        dimensions  = structure.get("dimensions", {}).get("observation", [])
        dataSets    = data.get("data", {}).get("dataSets", [{}])
        observations = dataSets[0].get("observations", {})

        # Index des dimensions
        dim_idx = {d["id"]: i for i, d in enumerate(dimensions)}

        # Tables de correspondance code → ISO3
        ref_area_dim  = dimensions[dim_idx.get("REF_AREA", 0)]
        origin_dim    = dimensions[dim_idx.get("COUNTERPART_AREA", 1)]
        time_dim      = dimensions[dim_idx.get("TIME_PERIOD", -1)]

        ref_area_vals  = {str(i): v["id"] for i, v in enumerate(ref_area_dim.get("values", []))}
        origin_vals    = {str(i): v["id"] for i, v in enumerate(origin_dim.get("values", []))}
        time_vals      = {str(i): v["id"] for i, v in enumerate(time_dim.get("values", []))}

        for key, obs in observations.items():
            parts = key.split(":")
            if len(parts) < max(dim_idx.values()) + 1:
                continue

            country_to   = ref_area_vals.get(parts[dim_idx.get("REF_AREA", 0)], "")
            country_from = origin_vals.get(parts[dim_idx.get("COUNTERPART_AREA", 1)], "")
            year_str     = time_vals.get(parts[dim_idx.get("TIME_PERIOD", len(parts)-1)], "")
            value        = obs[0] if obs else None

            if not country_to or not country_from or value is None:
                continue
            if len(country_to) != 3 or len(country_from) != 3:
                continue

            try:
                year = int(year_str)
            except ValueError:
                continue

            if year < annee_debut or year > annee_fin:
                continue

            rows.append({
                "country_from": country_from,
                "country_to":   country_to,
                "year":         year,
                "value":        float(value),
                "source":       SOURCE_OCDE,
            })

    except Exception as e:
        print(f"  ⚠️  Erreur OCDE : {e}")

    return rows


# -------------------------------------------------------------
# POINT D'ENTRÉE
# -------------------------------------------------------------

def run():
    print("=" * 60)
    print("ETL — Étudiants internationaux (UNESCO UIS + OCDE)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)
    total_insere = 0

    # Étape 1 — UNESCO (base large, couverture pays en développement)
    print("\n→ Étape 1 : UNESCO UIS")
    rows_uis = fetch_uis(ANNEE_DEBUT, ANNEE_FIN)
    if rows_uis:
        nb = upsert_rows(conn, rows_uis)
        total_insere += nb
        print(f"  ✅ {nb} lignes UNESCO insérées")
    else:
        print("  Aucune donnée UNESCO.")

    time.sleep(PAUSE)

    # Étape 2 — OCDE (prioritaire, écrase UNESCO)
    print("\n→ Étape 2 : OCDE (prioritaire sur UNESCO)")
    rows_oecd = fetch_oecd(ANNEE_DEBUT, ANNEE_FIN)
    if rows_oecd:
        nb = upsert_rows(conn, rows_oecd)
        total_insere += nb
        print(f"  ✅ {nb} lignes OCDE insérées/remplacées")
    else:
        print("  Aucune donnée OCDE.")

    conn.close()
    print(f"\n{'='*60}")
    print(f"Étudiants internationaux terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
