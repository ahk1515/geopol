# =============================================================
# GÉOPOL — Parser IMF World Economic Outlook (WEO)
# Source : FMI — World Economic Outlook Database
# https://www.imf.org/en/Publications/WEO
#
# Schéma identite :
#   indicator    = voir WEO_INDICATORS ci-dessous
#   subcategory  = None (historique) | 'projection' (années > Estimates Start After)
#
# Mode : semi-automatique
#   → télécharger "WEO by Countries — All" depuis le site FMI
#   → déposer le fichier .xls dans etl/sources/uploads/
#   → nom attendu : weo*.xls (ou similaire)
#
# Particularités :
#   - Fichier TSV encodé UTF-16-LE avec extension .xls (trompeuse)
#   - Projections 2025-2030 taguées subcategory='projection'
#   - Pour pib_usd et population : on n'importe que les projections (2025+)
#     car les données historiques viennent déjà de la Banque Mondiale
# =============================================================

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB

SOURCE = "FMI WEO"

# -------------------------------------------------------------
# INDICATEURS À IMPORTER
# (code_weo, indicator_géopol, projections_only)
# projections_only=True → on n'importe que les années > est_after
# projections_only=False → on importe tout (dans les bornes ANNEE_DEBUT-ANNEE_FIN)
# -------------------------------------------------------------
WEO_INDICATORS = {
    "LUR":          ("taux_chomage",        "%",    False),
    "PCPIPCH":      ("inflation",           "%",    False),
    "GGXWDG_NGDP":  ("dette_publique_pib",  "%",    False),
    "BCA_NGDPD":    ("balance_courante_pib","%",    False),
    "NGDP_RPCH":    ("croissance_pib",      "%",    False),
    "NGDPD":        ("pib_usd",             "USD",  True),   # projections seulement
    "LP":           ("population",          "M",    True),   # projections seulement
}

# Codes ISO3 non standard dans WEO → ISO3 GÉOPOL
WEO_ISO3_MAP = {
    "UVK": "XKX",  # Kosovo
    "WBG": "PSE",  # Palestine (West Bank & Gaza)
}


# -------------------------------------------------------------
# PARSING
# -------------------------------------------------------------

def parse_value(s):
    """Parse une valeur WEO — retourne None si absente."""
    if not s or not s.strip() or s.strip() in ('n/a', '--', 'NA', ''):
        return None
    s = s.strip().replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def run(filepath=None):
    if not filepath:
        uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
        candidates = []
        if os.path.isdir(uploads_dir):
            for f in os.listdir(uploads_dir):
                if f.lower().startswith('weo') and f.lower().endswith('.xls'):
                    candidates.insert(0, os.path.join(uploads_dir, f))
        candidates += [
            os.path.join(uploads_dir, "weoapr2025all.xls"),
            "weoapr2025all.xls",
        ]
        for c in candidates:
            if os.path.exists(c):
                filepath = c
                break

    if not filepath or not os.path.exists(filepath):
        print("⏭️  Fichier WEO non trouvé — import ignoré.")
        print("   Dépose weo*.xls dans etl/sources/uploads/")
        return 0

    print("=" * 60)
    print("ETL — FMI World Economic Outlook")
    print(f"Fichier : {filepath}")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    # Lecture UTF-16-LE (format réel malgré l'extension .xls)
    with open(filepath, encoding='utf-16-le') as f:
        lines = f.readlines()

    if not lines:
        print("❌ Fichier vide")
        return 0

    # En-tête
    headers = lines[0].strip().split('\t')
    try:
        col_iso3    = headers.index('ISO')
        col_code    = headers.index('WEO Subject Code')
        col_unit    = headers.index('Units')
        col_scale   = headers.index('Scale')
        col_est     = headers.index('Estimates Start After')
    except ValueError as e:
        print(f"❌ Colonne manquante : {e}")
        return 0

    # Index des colonnes années
    year_cols = {}
    for i, h in enumerate(headers):
        if h.isdigit():
            yr = int(h)
            if ANNEE_DEBUT <= yr <= ANNEE_FIN:
                year_cols[i] = yr

    # Connexion DB
    conn = sqlite3.connect(PATH_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS identite (
            country_iso3 TEXT,
            indicator    TEXT,
            year         INTEGER,
            value        REAL,
            unit         TEXT,
            source       TEXT,
            subcategory  TEXT,
            PRIMARY KEY (country_iso3, indicator, year, subcategory)
        )
    """)
    conn.commit()

    total   = 0
    counts  = {ind: 0 for _, (ind, _, _) in WEO_INDICATORS.items()}

    for line in lines[1:]:
        parts = line.strip().split('\t')
        if len(parts) < col_est + 1:
            continue

        weo_code = parts[col_code].strip() if col_code < len(parts) else ""
        if weo_code not in WEO_INDICATORS:
            continue

        indicator, unit, proj_only = WEO_INDICATORS[weo_code]

        iso3 = parts[col_iso3].strip() if col_iso3 < len(parts) else ""
        iso3 = WEO_ISO3_MAP.get(iso3, iso3)
        if not iso3 or len(iso3) != 3:
            continue

        # Année à partir de laquelle les données sont des projections
        est_after_str = parts[col_est].strip() if col_est < len(parts) else ""
        try:
            est_after = int(est_after_str)
        except ValueError:
            est_after = 2024  # fallback

        rows = []
        for col_idx, year in year_cols.items():
            if col_idx >= len(parts):
                continue

            # Pour projections_only : ignorer les années historiques
            is_projection = year > est_after
            if proj_only and not is_projection:
                continue

            val = parse_value(parts[col_idx])
            if val is None:
                continue

            subcat = "projection" if is_projection else None
            rows.append((iso3, indicator, year, val, unit, SOURCE, subcat))

        if rows:
            conn.executemany("""
                INSERT OR REPLACE INTO identite
                    (country_iso3, indicator, year, value, unit, source, subcategory)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, rows)
            counts[indicator] += len(rows)
            total += len(rows)

    conn.commit()
    conn.close()

    print()
    for ind, nb in counts.items():
        print(f"  {'✅' if nb > 0 else '⏭️ '} {ind:<30} {nb:>6} lignes")

    print(f"\n{'='*60}")
    print(f"WEO terminé — {total} lignes au total")
    print(f"{'='*60}")
    return total


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    run(filepath)
