# =============================================================
# GÉOPOL — ETL Banque Mondiale
# Récupère les indicateurs identite depuis l'API World Bank
# API doc : https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
# =============================================================

import requests
import sqlite3
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import (
    ANNEE_DEBUT, ANNEE_FIN, PAYS,
    INDICATORS_WB, WB_META, PATH_DB
)

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
WB_API_BASE = "https://api.worldbank.org/v2"
PER_PAGE    = 1000   # max autorisé par l'API
PAUSE       = 0.3    # secondes entre requêtes (politesse API)
SOURCE      = "Banque Mondiale"

# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def get_all_countries():
    """Retourne la liste de tous les ISO3 actifs selon la Banque Mondiale."""
    url = f"{WB_API_BASE}/country?format=json&per_page=300"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    countries = []
    for c in data[1]:
        # On exclut les agrégats régionaux (capitalCity vide = agrégat)
        if c.get("capitalCity") and c.get("id"):
            countries.append(c["id"])
    return countries


def fetch_indicator(wb_code, iso3_list, annee_debut, annee_fin):
    """
    Récupère toutes les valeurs d'un indicateur WB pour une liste de pays.
    Retourne une liste de dicts prêts pour SQLite.
    """
    # L'API WB accepte jusqu'à ~50 pays en une requête via point-virgule
    BATCH = 50
    rows = []

    for i in range(0, len(iso3_list), BATCH):
        batch = iso3_list[i:i+BATCH]
        countries_str = ";".join(batch)
        url = (
            f"{WB_API_BASE}/country/{countries_str}/indicator/{wb_code}"
            f"?format=json&per_page={PER_PAGE}"
            f"&date={annee_debut}:{annee_fin}"
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # data[0] = metadata, data[1] = valeurs
            if len(data) < 2 or data[1] is None:
                continue

            for entry in data[1]:
                if entry.get("value") is None:
                    continue  # Règle : donnée absente → on n'insère pas
                rows.append({
                    "country_iso3": entry["countryiso3code"],
                    "year":         int(entry["date"]),
                    "value":        float(entry["value"]),
                })
        except Exception as e:
            print(f"  ⚠️  Erreur {wb_code} / batch {i//BATCH + 1} : {e}")

        time.sleep(PAUSE)

    return rows


# -------------------------------------------------------------
# INSERTION EN BASE
# -------------------------------------------------------------

def upsert_rows(conn, indicator, rows, meta):
    """
    Insère ou remplace les lignes dans la table identite.
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
            None,  # subcategory — non applicable ici
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
    print("ETL — Banque Mondiale")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    # Liste des pays
    if PAYS == "tous":
        print("Récupération de la liste des pays...")
        iso3_list = get_all_countries()
        print(f"{len(iso3_list)} pays trouvés.")
    else:
        iso3_list = PAYS

    # Connexion DB
    conn = sqlite3.connect(PATH_DB)

    total_insere = 0

    for indicator, wb_code in INDICATORS_WB.items():
        print(f"\n→ {indicator} ({wb_code})")
        rows = fetch_indicator(wb_code, iso3_list, ANNEE_DEBUT, ANNEE_FIN)

        if not rows:
            print(f"  Aucune donnée reçue.")
            continue

        meta = WB_META[indicator]
        nb = upsert_rows(conn, indicator, rows, meta)
        total_insere += nb
        print(f"  ✅ {nb} lignes insérées/mises à jour")

    conn.close()
    print(f"\n{'='*60}")
    print(f"Banque Mondiale terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
