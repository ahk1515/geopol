# =============================================================
# GÉOPOL — Parser UNESCO OPRI (étudiants internationaux)
# Source : UNESCO Institute for Statistics — OPRI dataset
# https://apiportal.uis.unesco.org/
#
# Schéma flux :
#   country_from  = pays d'origine de l'étudiant (ISO3)
#   country_to    = pays d'accueil (ISO3)
#   indicator     = etudiants_international
#   year          = année
#   value         = nombre d'étudiants
#   unit          = personnes
#   source        = UNESCO OPRI
#   subcategory_1 = None
#
# Mode : semi-automatique
#   → déposer OPRI_DATA_NATIONAL.csv dans etl/sources/uploads/
#   → OPRI_LABEL.csv doit être présent dans le même dossier
#
# Note : seuls les flux bilatéraux "both sexes" sont importés.
#        Les agrégats régionaux et les "unknown countries" sont ignorés.
# =============================================================

import sqlite3
import csv
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import ANNEE_DEBUT, ANNEE_FIN, PATH_DB

SOURCE = "UNESCO OPRI"
UNIT   = "personnes"

# -------------------------------------------------------------
# CORRESPONDANCE NOM OPRI → ISO3
# -------------------------------------------------------------
OPRI_TO_ISO3 = {
    "Anguilla": "AIA",
    "Côte d'Ivoire": "CIV",
    "the British Virgin Islands": "VGB",
    "the Cayman Islands": "CYM",
    "the Cook Islands": "COK",
    "the Marshall Islands": "MHL",
    "the Netherlands": "NLD",
    "the Netherlands Antilles": "ANT",
    "the Philippines": "PHL",
    "the Federated States of Micronesia": "FSM",
    "Afghanistan": "AFG", "Albania": "ALB", "Algeria": "DZA",
    "Angola": "AGO", "Andorra": "AND", "Antigua and Barbuda": "ATG",
    "Argentina": "ARG", "Armenia": "ARM", "Aruba": "ABW",
    "Australia": "AUS", "Austria": "AUT", "Azerbaijan": "AZE",
    "Bahamas": "BHS", "Bahrain": "BHR", "Bangladesh": "BGD",
    "Barbados": "BRB", "Belarus": "BLR", "Belgium": "BEL",
    "Belize": "BLZ", "Benin": "BEN", "Bermuda": "BMU",
    "Bhutan": "BTN", "Bolivia": "BOL", "Bosnia and Herzegovina": "BIH",
    "Botswana": "BWA", "Brazil": "BRA", "British Virgin Islands": "VGB",
    "Brunei Darussalam": "BRN", "Bulgaria": "BGR", "Burkina Faso": "BFA",
    "Burundi": "BDI", "Cambodia": "KHM", "Cameroon": "CMR",
    "Canada": "CAN", "Cape Verde": "CPV", "Cabo Verde": "CPV",
    "Cayman Islands": "CYM", "Central African Republic": "CAF",
    "the Central African Republic": "CAF", "Chad": "TCD",
    "Chile": "CHL", "China": "CHN", "Colombia": "COL",
    "Comoros": "COM", "Congo": "COG", "the Congo": "COG",
    "Cook Islands": "COK", "Costa Rica": "CRI", "Croatia": "HRV",
    "Cuba": "CUB", "Cyprus": "CYP", "Czechia": "CZE",
    "the Czechia": "CZE", "Czech Republic": "CZE",
    "Democratic Republic of the Congo": "COD",
    "the Democratic Republic of the Congo": "COD",
    "Democratic People's Republic of Korea": "PRK",
    "the Democratic People's Republic of Korea": "PRK",
    "Denmark": "DNK", "Djibouti": "DJI", "Dominica": "DMA",
    "Dominican Republic": "DOM", "Ecuador": "ECU", "Egypt": "EGY",
    "El Salvador": "SLV", "Equatorial Guinea": "GNQ",
    "Eritrea": "ERI", "Estonia": "EST", "Eswatini": "SWZ",
    "Ethiopia": "ETH", "Federated States of Micronesia": "FSM", "the Federated States of Micronesia": "FSM",
    "Fiji": "FJI", "Finland": "FIN", "France": "FRA",
    "Gabon": "GAB", "Gambia": "GMB", "the Gambia": "GMB",
    "Georgia": "GEO", "Germany": "DEU", "Ghana": "GHA",
    "Gibraltar": "GIB", "Greece": "GRC", "Grenada": "GRD",
    "Guatemala": "GTM", "Guinea": "GIN", "Guinea-Bissau": "GNB",
    "Guyana": "GUY", "Haiti": "HTI", "Holy See": "VAT",
    "the Holy See": "VAT",
    "Honduras": "HND",
    "Hong Kong, Special Administrative Region of China": "HKG",
    "Hungary": "HUN", "Iceland": "ISL", "India": "IND",
    "Indonesia": "IDN", "Iran": "IRN",
    "Islamic Republic of Iran": "IRN",
    "the Islamic Republic of Iran": "IRN",
    "Iraq": "IRQ", "Ireland": "IRL", "Israel": "ISR",
    "Italy": "ITA", "Jamaica": "JAM", "Japan": "JPN",
    "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN",
    "Kiribati": "KIR", "Korea": "KOR",
    "Republic of Korea": "KOR", "the Republic of Korea": "KOR",
    "Kuwait": "KWT", "Kyrgyzstan": "KGZ",
    "Lao People's Democratic Republic": "LAO",
    "Latvia": "LVA", "Lebanon": "LBN", "Lesotho": "LSO",
    "Liberia": "LBR", "Libya": "LBY", "Liechtenstein": "LIE",
    "Lithuania": "LTU", "Luxembourg": "LUX",
    "Macao, Special Administrative Region of China": "MAC",
    "Madagascar": "MDG", "Malawi": "MWI", "Malaysia": "MYS",
    "Maldives": "MDV", "Mali": "MLI", "Malta": "MLT",
    "Marshall Islands": "MHL", "Mauritania": "MRT",
    "Mauritius": "MUS", "Mexico": "MEX", "Moldova": "MDA",
    "Republic of Moldova": "MDA", "the Republic of Moldova": "MDA",
    "Monaco": "MCO", "Mongolia": "MNG", "Montenegro": "MNE",
    "Montserrat": "MSR", "Morocco": "MAR", "Mozambique": "MOZ",
    "Myanmar": "MMR", "Namibia": "NAM", "Nauru": "NRU",
    "Nepal": "NPL", "Netherlands": "NLD",
    "Netherlands Antilles": "ANT", "New Zealand": "NZL",
    "Nicaragua": "NIC", "Niger": "NER", "Nigeria": "NGA",
    "Niue": "NIU", "North Macedonia": "MKD", "Norway": "NOR",
    "Oman": "OMN", "Pakistan": "PAK", "Palau": "PLW",
    "Palestine": "PSE", "Panama": "PAN",
    "Papua New Guinea": "PNG", "Paraguay": "PRY", "Peru": "PER",
    "Philippines": "PHL", "Plurinational State of Bolivia": "BOL",
    "the Plurinational State of Bolivia": "BOL",
    "Poland": "POL", "Portugal": "PRT", "Qatar": "QAT",
    "Romania": "ROU", "Russian Federation": "RUS",
    "the Russian Federation": "RUS",
    "Rwanda": "RWA", "Saint Kitts and Nevis": "KNA",
    "Saint Lucia": "LCA", "Saint Vincent and the Grenadines": "VCT",
    "Samoa": "WSM", "San Marino": "SMR",
    "Sao Tome and Principe": "STP", "Saudi Arabia": "SAU",
    "Senegal": "SEN", "Serbia": "SRB", "Seychelles": "SYC",
    "Sierra Leone": "SLE", "Singapore": "SGP", "Slovakia": "SVK",
    "Slovenia": "SVN", "Solomon Islands": "SLB", "Somalia": "SOM",
    "South Africa": "ZAF", "South Sudan": "SSD", "Spain": "ESP",
    "Sri Lanka": "LKA", "Sudan": "SDN",
    "Sudan (pre-secession)": "SDN",
    "Suriname": "SUR", "Sweden": "SWE", "Switzerland": "CHE",
    "Syrian Arab Republic": "SYR",
    "the Syrian Arab Republic": "SYR",
    "Tajikistan": "TJK", "Tanzania": "TZA",
    "United Republic of Tanzania": "TZA",
    "the United Republic of Tanzania": "TZA",
    "Thailand": "THA", "Timor-Leste": "TLS", "Togo": "TGO",
    "Tokelau": "TKL", "Tonga": "TON",
    "Trinidad and Tobago": "TTO",
    "Tunisia": "TUN", "Turkey": "TUR", "Turkmenistan": "TKM",
    "Turks and Caicos Islands": "TCA", "Tuvalu": "TUV",
    "Uganda": "UGA", "Ukraine": "UKR",
    "the Ukraine": "UKR",
    "United Arab Emirates": "ARE",
    "United Kingdom": "GBR", "the United Kingdom": "GBR",
    "United States": "USA", "the United States": "USA",
    "Uruguay": "URY", "Uzbekistan": "UZB", "Vanuatu": "VUT",
    "Venezuela": "VEN",
    "Bolivarian Republic of Venezuela": "VEN",
    "the Bolivarian Republic of Venezuela": "VEN",
    "Viet Nam": "VNM", "Yemen": "YEM", "the Yemen": "YEM",
    "Zambia": "ZMB", "Zimbabwe": "ZWE",
}

# Pattern pour extraire le pays d'origine depuis le label
BILATERAL_PATTERN = re.compile(
    r"Inbound internationally mobile students from .+?: Students from (.+?), both sexes",
    re.IGNORECASE
)


# -------------------------------------------------------------
# CHARGEMENT DU MAPPING INDICATEUR → PAYS ORIGINE
# -------------------------------------------------------------

def load_bilateral_map(label_path):
    """
    Charge OPRI_LABEL.csv et retourne un dict {indicator_id: iso3_origin}.
    Ignore les agrégats régionaux et les "unknown countries".
    """
    bilateral = {}
    missing   = []

    with open(label_path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            ind_id = row['INDICATOR_ID']
            label  = row['INDICATOR_LABEL_EN']
            m = BILATERAL_PATTERN.search(label)
            if not m:
                continue

            country_name = m.group(1).strip()

            # Ignorer les "unknown countries"
            if 'unknown' in country_name.lower():
                continue

            iso3 = OPRI_TO_ISO3.get(country_name)
            if iso3:
                bilateral[ind_id] = iso3
            else:
                missing.append(country_name)

    if missing:
        unique_missing = sorted(set(missing))
        print(f"  ⚠️  {len(unique_missing)} noms non résolus en ISO3 : {unique_missing[:10]}")

    print(f"  {len(bilateral)} indicateurs bilatéraux chargés")
    return bilateral


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


def upsert_rows(conn, rows):
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

def run(filepath=None):
    """
    filepath : chemin vers OPRI_DATA_NATIONAL.csv
    OPRI_LABEL.csv doit être dans le même dossier.
    """
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")

    if not filepath:
        candidates = [
            os.path.join(uploads_dir, "OPRI_DATA_NATIONAL.csv"),
            os.path.join(os.path.dirname(__file__), "OPRI_DATA_NATIONAL.csv"),
            "OPRI_DATA_NATIONAL.csv",
        ]
        for c in candidates:
            if os.path.exists(c):
                filepath = c
                break

    if not filepath or not os.path.exists(filepath):
        print("⏭️  Fichier OPRI_DATA_NATIONAL.csv non trouvé — import ignoré.")
        print("   Dépose OPRI_DATA_NATIONAL.csv dans etl/sources/uploads/")
        return 0

    # Chercher OPRI_LABEL.csv dans le même dossier
    label_path = os.path.join(os.path.dirname(filepath), "OPRI_LABEL.csv")
    if not os.path.exists(label_path):
        label_path = os.path.join(uploads_dir, "OPRI_LABEL.csv")
    if not os.path.exists(label_path):
        print("❌ OPRI_LABEL.csv introuvable — nécessaire pour résoudre les pays d'origine.")
        print("   Dépose OPRI_LABEL.csv dans le même dossier que OPRI_DATA_NATIONAL.csv")
        return 0

    print("=" * 60)
    print("ETL — UNESCO OPRI (étudiants internationaux)")
    print(f"Données : {filepath}")
    print(f"Labels  : {label_path}")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    # Charger le mapping indicateur → ISO3 origine
    print("\n→ Chargement du mapping indicateurs...")
    bilateral_map = load_bilateral_map(label_path)
    if not bilateral_map:
        print("❌ Aucun indicateur bilatéral chargé.")
        return 0

    # Filtrer uniquement les indicator_id qui nous intéressent
    valid_ids = set(bilateral_map.keys())

    print(f"\n→ Parsing de {filepath}...")
    rows    = []
    skipped = 0
    batch_size = 10000

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)
    total = 0

    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for line in reader:
            ind_id     = line['INDICATOR_ID']
            country_to = line['COUNTRY_ID'].strip()
            year_str   = line['YEAR'].strip()
            value_str  = line['VALUE'].strip()
            magnitude  = line.get('MAGNITUDE', '').strip()

            # Filtrer indicateurs non bilatéraux
            if ind_id not in valid_ids:
                continue

            # Filtrer années hors bornes
            try:
                year = int(year_str)
            except ValueError:
                continue
            if year < ANNEE_DEBUT or year > ANNEE_FIN:
                continue

            # Filtrer valeurs absentes ou non numériques
            if not value_str or magnitude in ('na', 'nil'):
                skipped += 1
                continue
            try:
                value = float(value_str)
            except ValueError:
                skipped += 1
                continue
            if value <= 0:
                skipped += 1
                continue

            # Résoudre pays d'origine
            country_from = bilateral_map[ind_id]

            # Ignorer flux vers soi-même
            if country_from == country_to:
                skipped += 1
                continue

            rows.append((
                country_from,
                country_to,
                "etudiants_international",
                year,
                value,
                UNIT,
                SOURCE,
                None,  # subcategory_1
                None,  # subcategory_2
                None,  # subcategory_3
            ))

            # Insérer par batch pour économiser la mémoire
            if len(rows) >= batch_size:
                total += upsert_rows(conn, rows)
                rows = []
                print(f"  ... {total} lignes insérées", end='\r')

    # Insérer le dernier batch
    if rows:
        total += upsert_rows(conn, rows)

    conn.close()

    print(f"\n{'='*60}")
    print(f"UNESCO OPRI terminé — {total} lignes insérées")
    print(f"  {skipped} lignes ignorées (valeurs absentes/nulles)")
    print(f"{'='*60}")
    return total


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    run(filepath)
