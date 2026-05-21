# =============================================================
# GÉOPOL — ETL UNHCR (Réfugiés bilatéraux)
# API gratuite, sans clé
# Doc : https://api.unhcr.org/docs/refugee-statistics.html
# Endpoint : https://api.unhcr.org/population/v1/refugees/
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
API_BASE  = "https://api.unhcr.org/population/v1"
SOURCE    = "UNHCR"
PAUSE     = 0.5
PER_PAGE  = 10000  # max par page

# -------------------------------------------------------------
# FETCH
# -------------------------------------------------------------

def fetch_refugees(year):
    """
    Récupère tous les flux bilatéraux de réfugiés pour une année.
    Retourne une liste de dicts {country_from, country_to, value}.
    country_from = pays d'origine (coo)
    country_to   = pays d'asile (coa)
    """
    url    = f"{API_BASE}/refugees/"
    params = {
        "limit":   PER_PAGE,
        "page":    1,
        "year":    year,
        "coo_all": "true",
        "coa_all": "true",
    }

    rows = []
    while True:
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  Erreur {year} page {params['page']} : {e}")
            break

        items = data.get("items", [])
        for item in items:
            coo   = item.get("coo_iso", "").strip()   # pays d'origine ISO3
            coa   = item.get("coa_iso", "").strip()   # pays d'asile ISO3
            value = item.get("refugees")

            # Règle transparence : valeur absente → on ignore
            if not coo or not coa or value is None:
                continue
            if len(coo) != 3 or len(coa) != 3:
                continue  # exclure agrégats

            rows.append({
                "country_from": coo,
                "country_to":   coa,
                "value":        float(value),
            })

        # Pagination
        total   = data.get("total", 0)
        fetched = (params["page"] - 1) * PER_PAGE + len(items)
        if fetched >= total or not items:
            break
        params["page"] += 1
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


def upsert_rows(conn, year, rows):
    data = [
        (
            row["country_from"],
            row["country_to"],
            "refugies",
            year,
            row["value"],
            "personnes",
            SOURCE,
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
# POINT D'ENTRÉE
# -------------------------------------------------------------

def run():
    print("=" * 60)
    print("ETL — UNHCR (Réfugiés bilatéraux)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)
    total_insere = 0

    for year in range(ANNEE_DEBUT, ANNEE_FIN + 1):
        print(f"\n→ {year}")
        rows = fetch_refugees(year)

        if not rows:
            print(f"  Aucune donnée.")
            continue

        nb = upsert_rows(conn, year, rows)
        total_insere += nb
        print(f"  ✅ {nb} flux insérés")
        time.sleep(PAUSE)

    conn.close()
    print(f"\n{'='*60}")
    print(f"UNHCR terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
