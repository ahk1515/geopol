# =============================================================
# GÉOPOL — Migrations de schéma de la base
# Tourne EN PREMIER dans le pipeline (avant tous les parsers),
# sur la base téléchargée depuis R2.
#
# Migrations idempotentes : rejouables sans danger à chaque run.
# Une migration déjà appliquée se détecte et ne fait rien.
# =============================================================

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import PATH_DB


def _table_exists(conn, table):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _pk_columns(conn, table):
    """Liste ordonnée des colonnes de la clé primaire d'une table."""
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA renvoie (cid, name, type, notnull, dflt_value, pk)
    # pk > 0 = position dans la clé primaire
    return [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5] > 0]


def migrate_identite_subcategory(conn):
    """
    Migration : la clé primaire de `identite` doit inclure `subcategory`.

    Avant : PRIMARY KEY (country_iso3, indicator, year)
      → tous les indicateurs à subcategory (minéraux, énergie…) s'écrasent,
        il ne reste qu'une valeur par (pays, indicateur, année).
    Après : PRIMARY KEY (country_iso3, indicator, year, subcategory)
      → chaque subcategory coexiste.

    Convertit aussi les subcategory NULL existantes en chaîne vide '' :
    dans une clé primaire SQLite, deux NULL sont DISTINCTS, donc un
    INSERT OR REPLACE ne dédupliquerait plus les indicateurs sans
    subcategory. La chaîne vide '' se déduplique correctement.

    Idempotente : si la clé contient déjà subcategory, ne fait rien.
    """
    if not _table_exists(conn, "identite"):
        print("  identite absente — rien à migrer (sera créée correctement).")
        return False

    pk = _pk_columns(conn, "identite")
    if "subcategory" in pk:
        print(f"  identite : clé déjà correcte {pk} — aucune migration.")
        return False

    print(f"  identite : ancienne clé {pk} — migration vers (+subcategory)...")
    n_avant = conn.execute("SELECT COUNT(*) FROM identite").fetchone()[0]

    # Reconstruction de la table avec la bonne clé + NULL → ''
    conn.executescript("""
        BEGIN;
        CREATE TABLE identite_new (
            country_iso3 TEXT,
            indicator    TEXT,
            year         INTEGER,
            value        REAL,
            unit         TEXT,
            source       TEXT,
            subcategory  TEXT DEFAULT '',
            PRIMARY KEY (country_iso3, indicator, year, subcategory)
        );
        INSERT OR IGNORE INTO identite_new
            (country_iso3, indicator, year, value, unit, source, subcategory)
        SELECT country_iso3, indicator, year, value, unit, source,
               COALESCE(subcategory, '')
        FROM identite;
        DROP TABLE identite;
        ALTER TABLE identite_new RENAME TO identite;
        COMMIT;
    """)

    n_apres = conn.execute("SELECT COUNT(*) FROM identite").fetchone()[0]
    pk_apres = _pk_columns(conn, "identite")
    print(f"  ✅ Migration identite : {n_avant:,} → {n_apres:,} lignes, "
          f"nouvelle clé {pk_apres}")
    if n_apres < n_avant:
        # Des lignes ont fusionné (mêmes pays/indic/année/'' après COALESCE).
        # Normal si des doublons NULL existaient déjà. On le signale.
        print(f"     ({n_avant - n_apres} ligne(s) fusionnée(s) : "
              f"doublons NULL préexistants regroupés sous '')")
    return True


def run():
    """Applique toutes les migrations de schéma. Appelé en tête de pipeline."""
    print("=" * 60)
    print("MIGRATIONS — Vérification / mise à jour du schéma")
    print("=" * 60)

    if not os.path.exists(PATH_DB):
        print("  Base absente (premier run) — rien à migrer.")
        print("  Les tables seront créées par les parsers.")
        return 0

    conn = sqlite3.connect(PATH_DB)
    try:
        migrate_identite_subcategory(conn)
    finally:
        conn.close()

    print("=" * 60)
    print("Migrations terminées.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    run()
