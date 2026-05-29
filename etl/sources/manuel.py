# =============================================================
# GÉOPOL — Parser générique des CSV manuels assistés IA
#
# Lit tous les fichiers CSV présents dans uploads/manuel/ du repo
# et les insère dans la DB selon le format attendu.
#
# FORMAT identite (7 colonnes) :
#   country_iso3,indicator,year,value,unit,source,subcategory
#
# FORMAT flux (10 colonnes) :
#   country_from,country_to,indicator,year,value,unit,source,
#   subcategory_1,subcategory_2,subcategory_3
#
# Le format est détecté automatiquement via le header.
# Voir prompts_transformation_csv.md pour les détails.
# =============================================================

import csv
import gzip
import sqlite3
import sys
import os
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB, DIR_ROOT

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
UPLOADS_DIR = os.path.join(DIR_ROOT, "uploads", "manuel")

HEADER_IDENTITE = ["country_iso3", "indicator", "year", "value", "unit", "source", "subcategory"]
HEADER_FLUX     = ["country_from", "country_to", "indicator", "year", "value", "unit", "source",
                   "subcategory_1", "subcategory_2", "subcategory_3"]

# Sentinelles autorisées pour les colonnes country_from/country_to
SENTINELS = {"__multilateral__", "__private__", "__intra__"}

# -------------------------------------------------------------
# DÉTECTION DU FORMAT
# -------------------------------------------------------------

def detect_format(header):
    """Retourne 'identite', 'flux' ou None."""
    h = [c.strip().lower() for c in header]
    if h == HEADER_IDENTITE:
        return "identite"
    if h == HEADER_FLUX:
        return "flux"
    return None


# -------------------------------------------------------------
# VALIDATION D'UNE LIGNE
# -------------------------------------------------------------

def valid_iso3(code, allow_sentinel=False):
    """Retourne True si code est un ISO3 valide ou une sentinelle."""
    if not code:
        return False
    code = code.strip()
    if allow_sentinel and code in SENTINELS:
        return True
    return len(code) == 3 and code.isupper() and code.isalpha()


def parse_row_identite(row, line_no):
    """
    Retourne (data_tuple, error_msg).
    data_tuple = (country_iso3, indicator, year, value, unit, source, subcategory)
    """
    try:
        iso3   = row["country_iso3"].strip()
        ind    = row["indicator"].strip()
        year   = int(row["year"].strip())
        val    = float(row["value"].strip())
        unit   = row["unit"].strip() or None
        source = row["source"].strip() or "Manuel IA"
        subcat = row.get("subcategory", "").strip() or None

        if not valid_iso3(iso3):
            return None, f"ligne {line_no} : ISO3 invalide '{iso3}'"
        if not ind:
            return None, f"ligne {line_no} : indicator vide"
        if year < ANNEE_DEBUT or year > 2050:
            return None, f"ligne {line_no} : année hors plage ({year})"

        return (iso3, ind, year, val, unit, source, subcat), None
    except (ValueError, KeyError) as e:
        return None, f"ligne {line_no} : {e}"


def parse_row_flux(row, line_no):
    """Retourne (data_tuple, error_msg) pour table flux."""
    try:
        cf = row["country_from"].strip()
        ct = row["country_to"].strip()
        ind    = row["indicator"].strip()
        year   = int(row["year"].strip())
        val    = float(row["value"].strip())
        unit   = row["unit"].strip() or None
        source = row["source"].strip() or "Manuel IA"
        sc1 = row.get("subcategory_1", "").strip() or None
        sc2 = row.get("subcategory_2", "").strip() or None
        sc3 = row.get("subcategory_3", "").strip() or None

        if not valid_iso3(cf, allow_sentinel=True):
            return None, f"ligne {line_no} : country_from invalide '{cf}'"
        if not valid_iso3(ct, allow_sentinel=True):
            return None, f"ligne {line_no} : country_to invalide '{ct}'"
        if not ind:
            return None, f"ligne {line_no} : indicator vide"
        if year < ANNEE_DEBUT or year > 2050:
            return None, f"ligne {line_no} : année hors plage ({year})"

        return (cf, ct, ind, year, val, unit, source, sc1, sc2, sc3), None
    except (ValueError, KeyError) as e:
        return None, f"ligne {line_no} : {e}"


# -------------------------------------------------------------
# PARSING D'UN FICHIER
# -------------------------------------------------------------

def _open_text(filepath):
    """
    Ouvre un fichier en mode texte UTF-8 (avec BOM possible).
    Détecte automatiquement les fichiers compressés .gz et les décompresse à la volée.
    """
    if filepath.lower().endswith(".gz"):
        return gzip.open(filepath, mode="rt", encoding="utf-8-sig")
    return open(filepath, encoding="utf-8-sig")


def parse_file(filepath):
    """
    Parse un fichier CSV (ou CSV gzippé) et retourne (format, rows_valides, errors).
    Le format est détecté via le header, l'extension .gz est gérée de manière transparente.
    """
    with _open_text(filepath) as f:
        reader = csv.DictReader(f)
        fmt = detect_format(reader.fieldnames or [])

        if not fmt:
            return None, [], [
                f"En-tête non reconnue : {reader.fieldnames}. "
                f"Attendu (identite) : {HEADER_IDENTITE} OU (flux) : {HEADER_FLUX}"
            ]

        rows   = []
        errors = []
        parse_fn = parse_row_identite if fmt == "identite" else parse_row_flux

        for i, row in enumerate(reader, start=2):  # ligne 2 = première ligne de données
            data, err = parse_fn(row, i)
            if data:
                rows.append(data)
            elif err:
                errors.append(err)

    return fmt, rows, errors


# -------------------------------------------------------------
# INSERTION EN BASE
# -------------------------------------------------------------

def ensure_tables(conn):
    """Crée les tables identite et flux si absentes."""
    conn.execute("""
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


def insert_identite(conn, rows):
    conn.executemany("""
        INSERT OR REPLACE INTO identite
            (country_iso3, indicator, year, value, unit, source, subcategory)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def insert_flux(conn, rows):
    conn.executemany("""
        INSERT OR REPLACE INTO flux
            (country_from, country_to, indicator, year, value,
             unit, source, subcategory_1, subcategory_2, subcategory_3)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


# -------------------------------------------------------------
# POINT D'ENTRÉE
# -------------------------------------------------------------

def run():
    print("=" * 60)
    print("ETL — Imports manuels assistés IA")
    print(f"Dossier : {UPLOADS_DIR}")
    print("=" * 60)

    if not os.path.exists(UPLOADS_DIR):
        print(f"  ⏭️  Dossier {UPLOADS_DIR} absent — rien à traiter.")
        return 0

    # Ramasse les CSV (texte brut) ET les CSV gzippés (.csv.gz)
    files = sorted(
        glob.glob(os.path.join(UPLOADS_DIR, "*.csv"))
        + glob.glob(os.path.join(UPLOADS_DIR, "*.csv.gz"))
    )
    if not files:
        print("  ⏭️  Aucun fichier CSV (ou CSV.gz) dans uploads/manuel/")
        return 0

    print(f"  {len(files)} fichier(s) trouvé(s).")
    conn = sqlite3.connect(PATH_DB)
    ensure_tables(conn)

    total_inserted = 0

    for filepath in files:
        fname = os.path.basename(filepath)
        print(f"\n→ {fname}")

        try:
            fmt, rows, errors = parse_file(filepath)
        except Exception as e:
            print(f"  ❌ Lecture impossible : {e}")
            continue

        if not fmt:
            for err in errors[:5]:
                print(f"  ❌ {err}")
            continue

        if errors:
            print(f"  ⚠️  {len(errors)} ligne(s) ignorée(s) :")
            for err in errors[:5]:
                print(f"     {err}")
            if len(errors) > 5:
                print(f"     ... et {len(errors)-5} autres")

        if not rows:
            print(f"  ○ Aucune ligne valide à importer")
            continue

        try:
            if fmt == "identite":
                nb = insert_identite(conn, rows)
            else:
                nb = insert_flux(conn, rows)
            total_inserted += nb
            print(f"  ✅ {nb} lignes insérées (table {fmt})")
        except Exception as e:
            print(f"  ❌ Erreur insertion : {e}")

    conn.close()
    print(f"\n{'='*60}")
    print(f"Manuel terminé — {total_inserted} lignes au total")
    print(f"{'='*60}")
    return total_inserted


if __name__ == "__main__":
    run()
