# =============================================================
# GÉOPOL — ETL Our World In Data (OWID)
# Utilise la Charts API officielle OWID
# Doc : https://docs.owid.io/projects/etl/api/chart-api/
# Format : https://ourworldindata.org/grapher/{slug}.csv
# =============================================================

import requests
import sqlite3
import csv
import time
import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import (
    ANNEE_DEBUT, ANNEE_FIN,
    INDICATORS_OWID, OWID_META, PATH_DB
)

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
OWID_BASE = "https://ourworldindata.org/grapher"
SOURCE    = "Our World In Data"
PAUSE     = 1.0  # secondes entre requêtes (serveur OWID plus sensible)

# Mapping indicateur → slug OWID + nom de colonne dans le CSV
# Format CSV OWID : Entity | Code | Year | <colonne_valeur>
OWID_SLUGS = {
    "age_median": {
        "slug":   "median-age",
        "column": "Median age - Sex: all - Age: all - Variant: estimates",
    },
    "volume_armee": {
        "slug":   "military-personnel",
        "column": "Armed forces personnel",
    },
    "violent_death": {
        "slug":   "deaths-conflict-terrorism-per-100000",
        "column": "Conflict and terrorism deaths per 100,000 people",
    },
    "idps_securitaire": {
        "slug":   "internally-displaced-persons-from-conflict",
        "column": "Internally displaced persons from conflict and violence",
    },
    "idps_climatique": {
        "slug":   "internally-displaced-persons-from-disasters",
        "column": "Internally displaced persons from disasters",
    },
}

# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def fetch_owid(slug, col_value, annee_debut, annee_fin):
    """
    Télécharge le CSV d'un chart OWID et filtre les lignes utiles.
    Retourne une liste de dicts {country_iso3, year, value}.
    Règle : valeur absente → on n'insère pas.
    """
    url = f"{OWID_BASE}/{slug}.csv"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  Erreur téléchargement {slug} : {e}")
        return [], None

    lines = resp.text.splitlines()
    if not lines:
        return [], None

    reader = csv.DictReader(lines)

    # Détection souple du nom de colonne (peut varier légèrement)
    fieldnames = reader.fieldnames or []
    matched_col = None
    for f in fieldnames:
        if col_value.lower() in f.lower():
            matched_col = f
            break

    if not matched_col:
        # Fallback : première colonne après "Year"
        after_year = [f for f in fieldnames if f not in ("Entity", "Code", "Year")]
        if after_year:
            matched_col = after_year[0]
            print(f"  ⚠️  Colonne '{col_value}' non trouvée, utilisation de '{matched_col}'")
        else:
            print(f"  ❌ Aucune colonne de valeur trouvée pour {slug}")
            return [], None

    rows = []
    for row in reader:
        iso3      = row.get("Code", "").strip()
        year_str  = row.get("Year", "").strip()
        value_str = row.get(matched_col, "").strip()

        # Exclusions
        if not iso3 or len(iso3) != 3:
            continue  # agrégats OWID (OWID_WRL, etc.)
        if not year_str or not value_str:
            continue  # donnée absente → transparence

        try:
            year  = int(year_str)
            value = float(value_str)
        except ValueError:
            continue

        # Filtre temporel
        if year < annee_debut or year > annee_fin:
            continue

        rows.append({
            "country_iso3": iso3,
            "year":         year,
            "value":        value,
        })

    return rows, matched_col


# -------------------------------------------------------------
# INSERTION EN BASE
# -------------------------------------------------------------

def upsert_rows(conn, indicator, rows, meta):
    """
    Insère ou remplace dans la table identite.
    Règle : donnée révisée → on écrase (INSERT OR REPLACE).
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS identite (
            country_iso3 TEXT,
            indicator    TEXT,
            year         INTEGER,
            value        REAL,
            unit         TEXT,
            source       TEXT,
            subcategory  TEXT,
            PRIMARY KEY (country_iso3, indicator, year)
        )
    """)

    data = [
        (
            row["country_iso3"],
            indicator,
            row["year"],
            row["value"],
            meta["unit"],
            SOURCE,
            None,
        )
        for row in rows
    ]

    cursor.executemany("""
        INSERT OR REPLACE INTO identite
            (country_iso3, indicator, year, value, unit, source, subcategory)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, data)
    conn.commit()
    return len(data)


# -------------------------------------------------------------
# POINT D'ENTRÉE
# -------------------------------------------------------------

def run():
    print("=" * 60)
    print("ETL — Our World In Data")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    conn = sqlite3.connect(PATH_DB)
    total_insere = 0

    for indicator, cfg in OWID_SLUGS.items():
        slug      = cfg["slug"]
        col_value = cfg["column"]
        print(f"\n→ {indicator} ({slug})")

        rows, matched_col = fetch_owid(slug, col_value, ANNEE_DEBUT, ANNEE_FIN)

        if not rows:
            print(f"  Aucune donnée reçue.")
            time.sleep(PAUSE)
            continue

        print(f"  Colonne utilisée : {matched_col}")
        meta = OWID_META[indicator]
        nb   = upsert_rows(conn, indicator, rows, meta)
        total_insere += nb
        print(f"  ✅ {nb} lignes insérées/mises à jour")
        time.sleep(PAUSE)

    conn.close()
    print(f"\n{'='*60}")
    print(f"OWID terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
