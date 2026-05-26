# =============================================================
# GÉOPOL — Parser SIPRI Trade Register
# Source : SIPRI Arms Transfers Database
# https://www.sipri.org/databases/armstransfers
#
# Schéma flux :
#   country_from  = Supplier (ISO3)
#   country_to    = Recipient (ISO3)
#   indicator     = export_armement
#   year          = dernière année de livraison
#   value         = SIPRI TIV of delivered weapons
#   unit          = SIPRI_TIV_M
#   source        = SIPRI
#   subcategory_1 = type d'armement (weapon description normalisé)
#   subcategory_2 = désignation exacte (weapon designation)
#   subcategory_3 = statut (New / Second hand / Second hand but modernized)
# =============================================================

import sqlite3
import csv
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import PATH_DB

SOURCE   = "SIPRI"
UNIT     = "SIPRI_TIV_M"
HEADER_LINE = 11  # index 0-based de la ligne d'en-tête (ligne 12 du fichier)

# -------------------------------------------------------------
# TABLE DE CORRESPONDANCE NOM SIPRI → ISO3
# SIPRI utilise des noms anglais parfois non standard
# -------------------------------------------------------------
SIPRI_TO_ISO3 = {
    "Afghanistan": "AFG", "Albania": "ALB", "Algeria": "DZA",
    "Angola": "AGO", "Argentina": "ARG", "Armenia": "ARM",
    "Australia": "AUS", "Austria": "AUT", "Azerbaijan": "AZE",
    "Bahrain": "BHR", "Bangladesh": "BGD", "Belarus": "BLR",
    "Belgium": "BEL", "Bolivia": "BOL", "Bosnia-Herzegovina": "BIH",
    "Brazil": "BRA", "Brunei": "BRN", "Bulgaria": "BGR",
    "Burkina Faso": "BFA", "Cameroon": "CMR", "Canada": "CAN",
    "Chile": "CHL", "China": "CHN", "Colombia": "COL",
    "Congo, DR": "COD", "Croatia": "HRV", "Cuba": "CUB",
    "Cyprus": "CYP", "Czechia": "CZE", "Czech Republic": "CZE",
    "Czech Rep.": "CZE", "Czechoslovakia": "CSK", "Denmark": "DNK",
    "Ecuador": "ECU", "Egypt": "EGY", "El Salvador": "SLV",
    "Eritrea": "ERI", "Estonia": "EST", "Ethiopia": "ETH",
    "Finland": "FIN", "France": "FRA", "Georgia": "GEO",
    "Germany": "DEU", "Germany, East": "DDR", "East Germany (GDR)": "DDR",
    "Ghana": "GHA", "Greece": "GRC", "Guatemala": "GTM",
    "Guinea-Bissau": "GNB", "Honduras": "HND", "Hungary": "HUN",
    "India": "IND", "Indonesia": "IDN", "Iran": "IRN",
    "Iraq": "IRQ", "Ireland": "IRL", "Israel": "ISR",
    "Italy": "ITA", "Japan": "JPN", "Jordan": "JOR",
    "Kazakhstan": "KAZ", "Kenya": "KEN", "Kuwait": "KWT",
    "Kyrgyzstan": "KGZ", "Latvia": "LVA", "Lebanon": "LBN",
    "Libya": "LBY", "Lithuania": "LTU", "Malaysia": "MYS",
    "Mali": "MLI", "Mexico": "MEX", "Moldova": "MDA",
    "Morocco": "MAR", "Mozambique": "MOZ", "Myanmar": "MMR",
    "Netherlands": "NLD", "New Zealand": "NZL", "Niger": "NER",
    "Nigeria": "NGA", "North Korea": "PRK", "Norway": "NOR",
    "Oman": "OMN", "Pakistan": "PAK", "Panama": "PAN",
    "Paraguay": "PRY", "Peru": "PER", "Philippines": "PHL",
    "Poland": "POL", "Portugal": "PRT", "Qatar": "QAT",
    "Romania": "ROU", "Russia": "RUS", "Rwanda": "RWA",
    "Saudi Arabia": "SAU", "Senegal": "SEN", "Serbia": "SRB",
    "Seychelles": "SYC", "Singapore": "SGP", "Slovakia": "SVK",
    "Slovenia": "SVN", "Somalia": "SOM", "South Africa": "ZAF",
    "South Korea": "KOR", "Soviet Union": "SUN", "Spain": "ESP",
    "Sri Lanka": "LKA", "Sudan": "SDN", "Suriname": "SUR",
    "Sweden": "SWE", "Switzerland": "CHE", "Syria": "SYR",
    "Taiwan": "TWN", "Taiwan (China)": "TWN", "Tajikistan": "TJK",
    "Tanzania": "TZA", "Thailand": "THA", "Tunisia": "TUN",
    "Turkey": "TUR", "Turkiye": "TUR", "Turkmenistan": "TKM",
    "UAE": "ARE", "United Arab Emirates": "ARE",
    "Uganda": "UGA", "Ukraine": "UKR", "United Kingdom": "GBR",
    "United States": "USA", "Uruguay": "URY", "USA": "USA",
    "Uzbekistan": "UZB", "Venezuela": "VEN",
    "Viet Nam": "VNM", "Vietnam": "VNM",
    "Yemen": "YEM", "Yugoslavia": "YUG", "Zambia": "ZMB",
    "Zimbabwe": "ZWE", "Kosovo": "XKX", "Palestine": "PSE",
    "Antigua and Barbuda": "ATG", "Bahamas": "BHS", "Barbados": "BRB",
    "Belize": "BLZ", "Benin": "BEN", "Bhutan": "BTN", "Botswana": "BWA",
    "Burundi": "BDI", "Cabo Verde": "CPV", "Cambodia": "KHM",
    "Central African Republic": "CAF", "Chad": "TCD", "Comoros": "COM",
    "Congo": "COG", "Costa Rica": "CRI", "Cote d'Ivoire": "CIV",
    "DR Congo": "COD", "Djibouti": "DJI", "Dominican Republic": "DOM",
    "Equatorial Guinea": "GNQ", "eSwatini": "SWZ", "Fiji": "FJI",
    "Gabon": "GAB", "Gambia": "GMB", "Guinea": "GIN", "Guyana": "GUY",
    "Haiti": "HTI", "Iceland": "ISL", "Ivory Coast": "CIV",
    "Jamaica": "JAM", "Laos": "LAO", "Lesotho": "LSO", "Liberia": "LBR",
    "Luxembourg": "LUX", "Madagascar": "MDG", "Malawi": "MWI",
    "Maldives": "MDV", "Malta": "MLT", "Mauritania": "MRT",
    "Mauritius": "MUS", "Mongolia": "MNG", "Montenegro": "MNE",
    "Namibia": "NAM", "Nepal": "NPL", "Nicaragua": "NIC",
    "North Macedonia": "MKD", "Papua New Guinea": "PNG",
    "Sierra Leone": "SLE", "Solomon Islands": "SLB", "South Sudan": "SSD",
    "Timor-Leste": "TLS", "Togo": "TGO", "Tonga": "TON",
    "Trinidad and Tobago": "TTO", "Western Sahara": "ESH",
}

# Acteurs non-étatiques SIPRI → (sentinelle, nom normalisé)
# Les acteurs sans pays hôte identifiable → ("__non_etatique__", nom)
# ⚠️ Si SIPRI ajoute de nouveaux acteurs, compléter ici
NON_ETATIQUE_MAP = {
    "Hezbollah (Lebanon)*":              ("__non_etatique__", "Hezbollah"),
    "House of Representatives (Libya)*": ("__non_etatique__", "House of Representatives (Libya)"),
    "Northern Alliance (Afghanistan)*":  ("__non_etatique__", "Northern Alliance (Afghanistan)"),
    "Houthi rebels (Yemen)*":            ("__non_etatique__", "Houthi rebels"),
    "Syria rebels*":                     ("__non_etatique__", "Syria rebels"),
    "LTTE (Sri Lanka)*":                 ("__non_etatique__", "LTTE"),
    "Southern rebels (Yemen)*":          ("__non_etatique__", "Southern rebels (Yemen)"),
    "FMLN (El Salvador)*":               ("__non_etatique__", "FMLN"),
    "Hamas (Palestine)*":                ("__non_etatique__", "Hamas"),
    "Ukraine Rebels*":                   ("__non_etatique__", "Ukraine Rebels"),
    "Darfur rebels (Sudan)*":            ("__non_etatique__", "Darfur rebels"),
    "RSF (Sudan)*":                      ("__non_etatique__", "RSF"),
    "NTC (Libya)*":                      ("__non_etatique__", "NTC (Libya)"),
    "PKK (Turkiye)*":                    ("__non_etatique__", "PKK"),
    "RUF (Sierra Leone)*":               ("__non_etatique__", "RUF"),
    "United Wa State (Myanmar)*":        ("__non_etatique__", "United Wa State"),
    "Khmer Rouge (Cambodia)*":           ("__non_etatique__", "Khmer Rouge"),
    "Kurdistan Regional Government (Iraq)*": ("__non_etatique__", "Kurdistan Regional Government"),
    "LF (Lebanon)*":                     ("__non_etatique__", "Lebanese Forces"),
    "LRA (Uganda)*":                     ("__non_etatique__", "LRA"),
}

# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def normalize_weapon_desc(desc):
    """Normalise weapon description en snake_case."""
    desc = desc.strip().lower()
    desc = re.sub(r'[^a-z0-9]+', '_', desc)
    desc = desc.strip('_')
    return desc[:60]  # limite raisonnable


def normalize_status(status):
    """
    Encode le statut en suffixe court pour subcategory_2.
    New → rien (cas par défaut)
    Second hand → [SH]
    Second hand but modernized → [SHM]
    """
    s = status.strip().lower()
    if "modernized" in s:
        return "[SHM]"
    if "second hand" in s:
        return "[SH]"
    return ""


def extract_last_year(years_str):
    """
    Extrait la dernière année depuis un champ comme '2009; 2010; 2011'.
    Retourne None si aucune année valide trouvée.
    """
    years = re.findall(r'\b(19\d{2}|20\d{2})\b', years_str)
    if not years:
        return None
    return max(int(y) for y in years)


def parse_tiv(value_str):
    """Parse une valeur TIV — retourne None si absente ou non numérique."""
    value_str = value_str.strip().replace('?', '').strip()
    if not value_str:
        return None
    try:
        v = float(value_str)
        return v if v > 0 else None
    except ValueError:
        return None


# -------------------------------------------------------------
# PARSING DU FICHIER SIPRI
# -------------------------------------------------------------

def parse_sipri(filepath, annee_debut=2000, annee_fin=2024):
    """
    Parse le fichier trade-register.csv SIPRI.
    Retourne une liste de dicts prêts pour SQLite.
    """
    rows = []
    skipped = 0

    with open(filepath, encoding='latin-1') as f:
        lines = f.readlines()

    # Trouver la ligne d'en-tête (contient 'Recipient')
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith('Recipient,'):
            header_idx = i
            break

    if header_idx is None:
        print("❌ Ligne d'en-tête non trouvée")
        return []

    reader = csv.reader(lines[header_idx:])
    headers = next(reader)

    # Index des colonnes
    col = {h.strip(): i for i, h in enumerate(headers)}

    for row in reader:
        if len(row) < 16:
            skipped += 1
            continue

        recipient      = row[col.get('Recipient', 0)].strip()
        supplier       = row[col.get('Supplier', 1)].strip()
        years_str      = row[col.get('Year(s) of delivery', 10)].strip()
        weapon_desc    = row[col.get('Weapon description', 7)].strip()
        weapon_design  = row[col.get('Weapon designation', 6)].strip()
        status         = row[col.get('status', 11)].strip()
        tiv_str        = row[col.get('SIPRI TIV of delivered weapons', 15)].strip()

        # Résolution ISO3 fournisseur (jamais non-étatique côté supplier)
        supplier_iso3 = SIPRI_TO_ISO3.get(supplier)
        if not supplier_iso3:
            skipped += 1
            continue

        # Résolution destinataire : étatique ou non-étatique
        recipient_iso3   = SIPRI_TO_ISO3.get(recipient)
        non_etatique     = NON_ETATIQUE_MAP.get(recipient)

        if not recipient_iso3 and not non_etatique:
            # Inconnu (unknown recipient, organisations inter-étatiques, etc.)
            skipped += 1
            continue

        if non_etatique:
            country_to = non_etatique[0]   # "__non_etatique__"
            subcat3    = non_etatique[1]    # nom de l'acteur
        else:
            country_to = recipient_iso3
            subcat3    = recipient_iso3     # ISO3 répété pour homogénéité

        # Année de livraison
        year = extract_last_year(years_str)
        if not year or year < annee_debut or year > annee_fin:
            skipped += 1
            continue

        # Valeur TIV
        tiv = parse_tiv(tiv_str)
        if tiv is None:
            skipped += 1
            continue

        # Désignation + statut encodé en suffixe
        status_suffix = normalize_status(status)
        designation   = weapon_design[:58] if weapon_design else ""
        subcat2       = (f"{designation} {status_suffix}".strip())[:60] or None

        rows.append({
            "country_from":  supplier_iso3,
            "country_to":    country_to,
            "year":          year,
            "value":         tiv,
            "subcategory_1": normalize_weapon_desc(weapon_desc),
            "subcategory_2": subcat2,
            "subcategory_3": subcat3,
        })

    print(f"  {len(rows)} lignes parsées, {skipped} ignorées")
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
            PRIMARY KEY (country_from, country_to, indicator, year, subcategory_1, subcategory_2)
        )
    """)
    conn.commit()


def upsert_rows(conn, rows):
    data = [
        (
            row["country_from"],
            row["country_to"],
            "transferts_armement",
            row["year"],
            row["value"],
            UNIT,
            SOURCE,
            row["subcategory_1"],
            row["subcategory_2"],
            row["subcategory_3"],
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

def run(filepath=None, annee_debut=2000, annee_fin=2024):
    """
    filepath : chemin vers le fichier trade-register.csv
    Si non fourni, cherche dans le dossier courant.
    """
    if not filepath:
        # Cherche le fichier dans le dossier uploads ou courant
        candidates = [
            os.path.join(os.path.dirname(__file__), "uploads", "trade-register.csv"),
            os.path.join(os.path.dirname(__file__), "trade-register.csv"),
            "trade-register.csv",
        ]
        for c in candidates:
            if os.path.exists(c):
                filepath = c
                break

    if not filepath or not os.path.exists(filepath):
        print("⏭️  Fichier SIPRI non trouvé — import ignoré.")
        print("   Dépose trade-register.csv dans le dossier etl/sources/uploads/")
        return 0

    print("=" * 60)
    print("ETL — SIPRI Arms Transfers")
    print(f"Fichier : {filepath}")
    print(f"Période : {annee_debut} → {annee_fin}")
    print("=" * 60)

    rows = parse_sipri(filepath, annee_debut, annee_fin)
    if not rows:
        print("Aucune ligne à insérer.")
        return 0

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)
    nb = upsert_rows(conn, rows)
    conn.close()

    print(f"✅ {nb} lignes insérées/mises à jour")
    return nb


if __name__ == "__main__":
    # Permet de lancer directement : python sipri.py [chemin_fichier]
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    run(filepath)
