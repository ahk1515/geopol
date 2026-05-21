# =============================================================
# GÉOPOL — Calcul des indicateurs construits
# Tourne APRÈS tous les imports (automatiques + manuels)
# Règle : si une composante manque → on ne calcule pas (transparence)
# =============================================================

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, INDICATORS_CONSTRUITS, PATH_DB

SOURCE = "GÉOPOL (calculé)"

# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def get_identite(conn, indicator):
    """
    Retourne un dict {(iso3, year): value} pour un indicateur identite.
    """
    rows = conn.execute("""
        SELECT country_iso3, year, value
        FROM identite
        WHERE indicator = ?
    """, (indicator,)).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def get_flux_total(conn, indicator, direction="from"):
    """
    Retourne un dict {(iso3, year): value_totale} en agrégeant
    tous les partenaires pour un indicateur flux.
    direction='from' → agrège sur country_from (exports)
    direction='to'   → agrège sur country_to (imports)
    """
    col = "country_from" if direction == "from" else "country_to"
    rows = conn.execute(f"""
        SELECT {col}, year, SUM(value)
        FROM flux
        WHERE indicator = ?
        GROUP BY {col}, year
    """, (indicator,)).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def upsert_identite(conn, indicator, unit, unit_display, rows):
    """Insère ou remplace dans identite."""
    conn.executemany("""
        INSERT OR REPLACE INTO identite
            (country_iso3, indicator, year, value, unit, source, subcategory)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        (iso3, indicator, year, value, unit, SOURCE, None)
        for (iso3, year, value) in rows
    ])
    conn.commit()


def upsert_flux(conn, indicator, unit, rows):
    """Insère ou remplace dans flux."""
    conn.executemany("""
        INSERT OR REPLACE INTO flux
            (country_from, country_to, indicator, year, value,
             unit, source, subcategory_1, subcategory_2, subcategory_3)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (cf, ct, indicator, year, value, unit, SOURCE, None, None, None)
        for (cf, ct, year, value) in rows
    ])
    conn.commit()


# -------------------------------------------------------------
# CALCULS
# -------------------------------------------------------------

def calc_densite(conn):
    """
    Densité = Population / Land area (hab/km²)
    Table : identite
    """
    pop      = get_identite(conn, "population")
    land     = get_identite(conn, "land_area")
    all_keys = set(pop.keys()) & set(land.keys())

    rows = []
    for (iso3, year) in all_keys:
        p = pop[(iso3, year)]
        l = land[(iso3, year)]
        if p is None or l is None or l == 0:
            continue  # transparence : on ne calcule pas
        rows.append((iso3, year, round(p / l, 2)))

    upsert_identite(conn, "densite", "hab/km²", "hab/km²", rows)
    return len(rows)


def calc_dette_pct_pib(conn):
    """
    Dette % PIB = dette_exterieure / pib_usd * 100
    Table : identite
    dette_exterieure est agrégée depuis flux si elle y est stockée
    """
    # Dette extérieure peut être dans identite ou agrégée depuis flux
    dette = get_identite(conn, "dette_exterieure")
    if not dette:
        # Fallback : agrégation depuis flux
        dette = get_flux_total(conn, "dette_exterieure", direction="to")

    pib   = get_identite(conn, "pib_usd")
    all_keys = set(dette.keys()) & set(pib.keys())

    rows = []
    for (iso3, year) in all_keys:
        d = dette[(iso3, year)]
        p = pib[(iso3, year)]
        if d is None or p is None or p == 0:
            continue
        rows.append((iso3, year, round(d / p * 100, 4)))

    upsert_identite(conn, "dette_pct_pib", "%", "%", rows)
    return len(rows)


def calc_balance_commerciale(conn):
    """
    Balance = total exports - total imports (par pays, par année)
    Table : identite (résultat agrégé par pays)
    """
    exports = get_flux_total(conn, "export_commercial", direction="from")
    imports = get_flux_total(conn, "import_commercial", direction="to")
    all_keys = set(exports.keys()) | set(imports.keys())

    rows = []
    for (iso3, year) in all_keys:
        e = exports.get((iso3, year))
        i = imports.get((iso3, year))
        if e is None or i is None:
            continue  # transparence : les deux composantes requises
        rows.append((iso3, year, round(e - i, 2)))

    upsert_identite(conn, "balance_commerciale", "USD", "Mrd USD", rows)
    return len(rows)


def calc_export_pct_pib(conn):
    """
    Export % PIB = total exports pays / PIB * 100
    Table : identite
    """
    exports = get_flux_total(conn, "export_commercial", direction="from")
    pib     = get_identite(conn, "pib_usd")
    all_keys = set(exports.keys()) & set(pib.keys())

    rows = []
    for (iso3, year) in all_keys:
        e = exports[(iso3, year)]
        p = pib[(iso3, year)]
        if e is None or p is None or p == 0:
            continue
        rows.append((iso3, year, round(e / p * 100, 4)))

    upsert_identite(conn, "export_pct_pib", "%", "%", rows)
    return len(rows)


def calc_import_pct_pib(conn):
    """
    Import % PIB = total imports pays / PIB * 100
    Table : identite
    """
    imports = get_flux_total(conn, "import_commercial", direction="to")
    pib     = get_identite(conn, "pib_usd")
    all_keys = set(imports.keys()) & set(pib.keys())

    rows = []
    for (iso3, year) in all_keys:
        i = imports[(iso3, year)]
        p = pib[(iso3, year)]
        if i is None or p is None or p == 0:
            continue
        rows.append((iso3, year, round(i / p * 100, 4)))

    upsert_identite(conn, "import_pct_pib", "%", "%", rows)
    return len(rows)


def calc_export_armement_pct_pib(conn):
    """
    Export armement % PIB — dépend de SIPRI (manuel)
    Si SIPRI non importé → aucune ligne calculée (transparence)
    """
    exports = get_flux_total(conn, "export_armement", direction="from")
    if not exports:
        print("  ⏭️  export_armement_pct_pib ignoré (SIPRI non importé)")
        return 0

    pib = get_identite(conn, "pib_usd")
    all_keys = set(exports.keys()) & set(pib.keys())

    rows = []
    for (iso3, year) in all_keys:
        e = exports[(iso3, year)]
        p = pib[(iso3, year)]
        if e is None or p is None or p == 0:
            continue
        rows.append((iso3, year, round(e / p * 100, 6)))

    upsert_identite(conn, "export_armement_pct_pib", "%", "%", rows)
    return len(rows)


def calc_import_ressource_pct_pib(conn):
    """
    Import ressource naturelle % PIB
    Dépend de Comtrade sections HS ressources (manuels ou auto)
    Sections HS ressources : 01-27 (prod. primaires + énergie)
    """
    # Agrégation des sections HS ressources depuis flux commerce
    rows_db = conn.execute("""
        SELECT country_to, year, SUM(value)
        FROM flux
        WHERE indicator = 'import_commercial'
          AND CAST(subcategory_1 AS INTEGER) BETWEEN 1 AND 27
        GROUP BY country_to, year
    """).fetchall()

    if not rows_db:
        print("  ⏭️  import_ressource_pct_pib ignoré (données Comtrade manquantes)")
        return 0

    imports_res = {(r[0], r[1]): r[2] for r in rows_db}
    pib = get_identite(conn, "pib_usd")
    all_keys = set(imports_res.keys()) & set(pib.keys())

    rows = []
    for (iso3, year) in all_keys:
        i = imports_res[(iso3, year)]
        p = pib[(iso3, year)]
        if i is None or p is None or p == 0:
            continue
        rows.append((iso3, year, round(i / p * 100, 4)))

    upsert_identite(conn, "import_ressource_pct_pib", "%", "%", rows)
    return len(rows)


# -------------------------------------------------------------
# POINT D'ENTRÉE
# -------------------------------------------------------------

CALCULS = [
    ("densite",                   calc_densite),
    ("dette_pct_pib",             calc_dette_pct_pib),
    ("balance_commerciale",       calc_balance_commerciale),
    ("export_pct_pib",            calc_export_pct_pib),
    ("import_pct_pib",            calc_import_pct_pib),
    ("export_armement_pct_pib",   calc_export_armement_pct_pib),
    ("import_ressource_pct_pib",  calc_import_ressource_pct_pib),
]


def run():
    print("=" * 60)
    print("ETL — Indicateurs construits")
    print("=" * 60)

    conn = sqlite3.connect(PATH_DB)
    total = 0

    for label, fn in CALCULS:
        print(f"\n→ {label}")
        try:
            nb = fn(conn)
            total += nb
            if nb > 0:
                print(f"  ✅ {nb} lignes calculées")
            elif nb == 0:
                print(f"  ○  Aucune ligne (composantes manquantes)")
        except Exception as e:
            print(f"  ❌ Erreur : {e}")

    conn.close()
    print(f"\n{'='*60}")
    print(f"Construits terminés — {total} lignes au total")
    print(f"{'='*60}")
    return total


if __name__ == "__main__":
    run()
