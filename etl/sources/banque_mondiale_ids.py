# =============================================================
# GÉOPOL — ETL Dette bilatérale (World Bank IDS)
# Source : International Debt Statistics (IDS) — source ID 6
# Doc : https://worldbank.github.io/debt-data/api-guide/
#
# Indicateurs importés :
#   DT.DOD.BLAT.CD → bilaterale
#   DT.DOD.MLAT.CD → multilaterale
#   DT.DOD.PBND.CD → obligations_privees
#   DT.DOD.PROP.CD → crediteurs_prives
#
# Schéma flux :
#   country_from  = ISO3 du pays créditeur OU __multilateral__ OU __private__
#   country_to    = ISO3 du pays débiteur
#   indicator     = dette_exterieure
#   subcategory_1 = type homogène : bilaterale | multilaterale |
#                   obligations_privees | crediteurs_prives
#   subcategory_2 = détail créditeur : ISO3 (bilatéral) ou nom institution
#                   (multilatéral) ou None (privé)
#
# Limite : couvre uniquement les pays débiteurs
# à revenus faibles/intermédiaires (DRS)
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
IDS_API_BASE = "https://api.worldbank.org/v2/sources/6"
SOURCE       = "Banque Mondiale IDS"
PAUSE        = 0.5
PER_PAGE     = 32000

# Indicateurs IDS à importer
IDS_INDICATORS = {
    "DT.DOD.BLAT.CD": "bilaterale",
    "DT.DOD.MLAT.CD": "multilaterale",
    "DT.DOD.PBND.CD": "obligations_privees",
    "DT.DOD.PROP.CD": "crediteurs_prives",
}

# Noms des créditeurs chargés dynamiquement depuis l'API
CREDITOR_NAMES = {}  # code_num → nom complet

# Correspondance codes numériques IDS → ISO3
# Construite à partir du référentiel IDS (counterpart-area) croisé avec referentiel.json
# 3 cas non matchés résolus manuellement : Somalie (SOM), Israël (ISR), Brunei (BRN)
CREDITOR_ISO3_MAP = {
    "001": "AUT",  # Austria
    "002": "BEL",  # Belgium
    "003": "DNK",  # Denmark
    "004": "FRA",  # France
    "005": "DEU",  # Germany, Fed. Rep. of
    "006": "ITA",  # Italy
    "007": "NLD",  # Netherlands
    "008": "NOR",  # Norway
    "009": "PRT",  # Portugal
    "010": "SWE",  # Sweden
    "011": "CHE",  # Switzerland
    "012": "GBR",  # United Kingdom
    "018": "FIN",  # Finland
    "020": "ISL",  # Iceland
    "021": "IRL",  # Ireland
    "022": "LUX",  # Luxembourg
    "040": "GRC",  # Greece
    "050": "ESP",  # Spain
    "055": "TUR",  # Turkiye
    "060": "SRB",  # Serbia
    "061": "SVN",  # Slovenia
    "062": "HRV",  # Croatia
    "064": "BIH",  # Bosnia-Herzegovina
    "065": "MNE",  # Montenegro
    "066": "MKD",  # North Macedonia
    "068": "CZE",  # Czechia
    "069": "SVK",  # Slovak Republic
    "071": "ALB",  # Albania
    "072": "BGR",  # Bulgaria
    "075": "HUN",  # Hungary
    "076": "POL",  # Poland
    "077": "ROU",  # Romania
    "082": "EST",  # Estonia
    "083": "LVA",  # Latvia
    "084": "LTU",  # Lithuania
    "085": "UKR",  # Ukraine
    "086": "BLR",  # Belarus
    "087": "RUS",  # Russian Federation
    "091": "ARM",  # Armenia
    "093": "MDA",  # Moldova
    "095": "GEO",  # Georgia
    "130": "DZA",  # Algeria
    "133": "LBY",  # Libya
    "136": "MAR",  # Morocco
    "139": "TUN",  # Tunisia
    "142": "EGY",  # Egypt
    "216": "ZAF",  # South Africa
    "225": "AGO",  # Angola
    "227": "BWA",  # Botswana
    "228": "BDI",  # Burundi
    "229": "CMR",  # Cameroon
    "230": "CPV",  # Cabo Verde
    "231": "CAF",  # Central African Republic
    "232": "TCD",  # Chad
    "233": "COM",  # Comoros
    "234": "COG",  # Congo, Rep.
    "235": "COD",  # Congo, Dem. Rep.
    "236": "BEN",  # Benin
    "238": "ETH",  # Ethiopia
    "239": "GAB",  # Gabon
    "240": "GMB",  # Gambia, The
    "241": "GHA",  # Ghana
    "243": "GIN",  # Guinea
    "244": "GNB",  # Guinea-Bissau
    "245": "GNQ",  # Equatorial Guinea
    "247": "CIV",  # Cote D'Ivoire
    "248": "KEN",  # Kenya
    "249": "LSO",  # Lesotho
    "251": "LBR",  # Liberia
    "252": "MDG",  # Madagascar
    "253": "MWI",  # Malawi
    "255": "MLI",  # Mali
    "256": "MRT",  # Mauritania
    "257": "MUS",  # Mauritius
    "259": "MOZ",  # Mozambique
    "260": "NER",  # Niger
    "261": "NGA",  # Nigeria
    "265": "ZWE",  # Zimbabwe
    "266": "RWA",  # Rwanda
    "268": "STP",  # Sao Tome & Principe
    "269": "SEN",  # Senegal
    "270": "SYC",  # Seychelles
    "271": "ERI",  # Eritrea
    "272": "SLE",  # Sierra Leone
    "273": "SOM",  # Somalia (manuel)
    "274": "DJI",  # Djibouti
    "275": "NAM",  # Namibia
    "278": "SDN",  # Sudan
    "280": "SWZ",  # Eswatini
    "282": "TZA",  # Tanzania
    "283": "TGO",  # Togo
    "285": "UGA",  # Uganda
    "287": "BFA",  # Burkina Faso
    "288": "ZMB",  # Zambia
    "301": "CAN",  # Canada
    "302": "USA",  # United States
    "328": "BHS",  # Bahamas
    "329": "BRB",  # Barbados
    "336": "CRI",  # Costa Rica
    "338": "CUB",  # Cuba
    "340": "DOM",  # Dominican Republic
    "342": "SLV",  # El Salvador
    "347": "GTM",  # Guatemala
    "349": "HTI",  # Haiti
    "351": "HND",  # Honduras
    "352": "BLZ",  # Belize
    "354": "JAM",  # Jamaica
    "358": "MEX",  # Mexico
    "364": "NIC",  # Nicaragua
    "366": "PAN",  # Panama
    "375": "TTO",  # Trinidad & Tobago
    "425": "ARG",  # Argentina
    "428": "BOL",  # Bolivia
    "431": "BRA",  # Brazil
    "434": "CHL",  # Chile
    "437": "COL",  # Colombia
    "440": "ECU",  # Ecuador
    "446": "GUY",  # Guyana
    "451": "PRY",  # Paraguay
    "454": "PER",  # Peru
    "457": "SUR",  # Suriname
    "460": "URY",  # Uruguay
    "463": "VEN",  # Venezuela
    "520": "AZE",  # Azerbaijan
    "521": "KAZ",  # Kazakhstan
    "522": "KGZ",  # Kyrgyz Republic
    "523": "UZB",  # Uzbekistan
    "524": "TJK",  # Tajikistan
    "525": "TKM",  # Turkmenistan
    "530": "BHR",  # Bahrain
    "540": "IRN",  # Iran
    "543": "IRQ",  # Iraq
    "546": "ISR",  # Israel (manuel)
    "549": "JOR",  # Jordan
    "552": "KWT",  # Kuwait
    "555": "LBN",  # Lebanon
    "558": "OMN",  # Oman
    "561": "QAT",  # Qatar
    "566": "SAU",  # Saudi Arabia
    "573": "SYR",  # Syrian Arab Republic
    "576": "ARE",  # United Arab Emirates
    "580": "YEM",  # Yemen
    "625": "AFG",  # Afghanistan
    "630": "BTN",  # Bhutan
    "635": "MMR",  # Myanmar
    "640": "LKA",  # Sri Lanka
    "646": "IND",  # India
    "655": "MDV",  # Maldives
    "660": "NPL",  # Nepal
    "665": "PAK",  # Pakistan
    "666": "BGD",  # Bangladesh
    "701": "JPN",  # Japan
    "725": "BRN",  # Brunei (manuel)
    "728": "KHM",  # Cambodia
    "730": "CHN",  # China
    "738": "IDN",  # Indonesia
    "740": "PRK",  # Korea, D.P.R. of
    "742": "KOR",  # Korea, Republic of
    "745": "LAO",  # Lao PDR
    "751": "MYS",  # Malaysia
    "753": "MNG",  # Mongolia
    "755": "PHL",  # Philippines
    "761": "SGP",  # Singapore
    "764": "THA",  # Thailand
    "765": "TLS",  # Timor-Leste
    "769": "VNM",  # Viet Nam
    "801": "AUS",  # Australia
    "820": "NZL",  # New Zealand
    "832": "FJI",  # Fiji
    "862": "PNG",  # Papua New Guinea
    "866": "SLB",  # Solomon Islands
    "880": "WSM",  # Samoa
}

# Institutions multilatérales connues (code IDS → nom court)
MULTILATERAL_NAMES = {
    "887": "NDB",
    "899": "AIIB",
    "901": "IBRD",
    "905": "IDA",
    "907": "IMF",
    "909": "IADB",
    "910": "BCIE",
    "913": "AfDB",
    "915": "ADB",
    "917": "EEC",
    "918": "EDF",
    "919": "EIB",
    "920": "CAF",
    "921": "AFESD",
    "926": "CoE",
    "950": "NDF",
    "951": "OPEC Fund",
    "953": "BADEA",
    "957": "BOAD",
    "969": "NIB",
    "975": "EU",
    "976": "IsDB",
    "977": "EDB",
    "988": "IFAD",
    "990": "EBRD",
    "994": "Multiple Lenders",
}

# Sentinelles
SENTINEL_MULTILATERAL = "__multilateral__"
SENTINEL_PRIVATE      = "__private__"


# -------------------------------------------------------------
# CHARGEMENT TABLE DE CORRESPONDANCE CRÉDITEURS
# -------------------------------------------------------------

def load_creditor_codes():
    """
    Charge les noms des créditeurs IDS depuis l'API (pour logs et fallback).
    La CREDITOR_ISO3_MAP statique reste la référence principale.
    """
    print("  Chargement des noms créditeurs IDS...")
    page = 1
    while True:
        url = f"{IDS_API_BASE}/counterpart-area?per_page=300&format=json&page={page}"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            variables = data["source"][0]["concept"][0]["variable"]
            for v in variables:
                CREDITOR_NAMES[v["id"]] = v["value"]
            if page >= data["pages"]:
                break
            page += 1
            time.sleep(PAUSE)
        except Exception as e:
            print(f"  ⚠️  Erreur chargement créditeurs page {page} : {e}")
            break
    print(f"  {len(CREDITOR_NAMES)} noms créditeurs chargés.")


# -------------------------------------------------------------
# CHARGEMENT LISTE DES PAYS DÉBITEURS
# -------------------------------------------------------------

def load_debtor_countries():
    """
    Charge la liste des pays débiteurs IDS (pays DRS).
    """
    url = f"{IDS_API_BASE}/country?per_page=300&format=json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        countries = data["source"][0]["concept"][0]["variable"]
        return [c["id"] for c in countries if len(c["id"]) == 3]
    except Exception as e:
        print(f"  ⚠️  Erreur chargement pays débiteurs : {e}")
        return []


# -------------------------------------------------------------
# FETCH DONNÉES IDS
# -------------------------------------------------------------

def fetch_ids(debtor_iso3, series_code):
    """
    Récupère les données IDS pour un pays débiteur et un indicateur.
    Retourne une liste de dicts {creditor_code, year, value}.
    """
    url = (
        f"{IDS_API_BASE}/country/{debtor_iso3}"
        f"/series/{series_code}"
        f"/counterpart-area/all"
        f"/time/all"
        f"?format=json&per_page={PER_PAGE}"
    )

    rows = []
    page = 1

    while True:
        try:
            resp = requests.get(f"{url}&page={page}", timeout=60)
            resp.raise_for_status()
            data = resp.json()

            source_data = data.get("source", {})
            if isinstance(source_data, list):
                source_data = source_data[0] if source_data else {}
            entries = source_data.get("data", [])

            for entry in entries:
                if entry.get("value") is None:
                    continue  # Règle transparence

                variables = {v["concept"]: v for v in entry["variable"]}
                creditor_code = variables.get("Counterpart-Area", {}).get("id")
                year_str      = variables.get("Time", {}).get("id", "")

                if not creditor_code or not year_str.startswith("YR"):
                    continue

                try:
                    year  = int(year_str[2:])
                    value = float(entry["value"])
                except (ValueError, TypeError):
                    continue

                if value <= 0:
                    continue

                rows.append({
                    "creditor_code": creditor_code,
                    "year":          year,
                    "value":         value,
                })

            if page >= data.get("pages", 1):
                break
            page += 1
            time.sleep(PAUSE)

        except Exception as e:
            print(f"  ⚠️  Erreur {debtor_iso3}/{series_code} page {page} : {e}")
            break

    return rows


# -------------------------------------------------------------
# RÉSOLUTION CRÉDITEUR → (country_from, subcategory_1, subcategory_2)
# -------------------------------------------------------------

def resolve_creditor(creditor_code, subcategory):
    """
    Retourne (country_from, subcategory_1, subcategory_2).

    Bilatéral (pays identifiable) :
      country_from  = ISO3 du pays créditeur
      subcategory_1 = type IDS (bilaterale, multilaterale, ...)
      subcategory_2 = ISO3 du pays créditeur (pour drill-down homogène)

    Multilatéral (institution connue) :
      country_from  = __multilateral__
      subcategory_1 = type IDS
      subcategory_2 = nom court de l'institution (IMF, IDA, ADB...)

    Privé :
      country_from  = __private__
      subcategory_1 = type IDS
      subcategory_2 = None

    Inconnu :
      country_from  = __multilateral__ (par défaut, rien ne se perd)
      subcategory_1 = type IDS
      subcategory_2 = nom complet depuis l'API ou code brut
    """
    iso3 = CREDITOR_ISO3_MAP.get(creditor_code)
    if iso3:
        return iso3, subcategory, iso3

    if creditor_code in MULTILATERAL_NAMES:
        return SENTINEL_MULTILATERAL, subcategory, MULTILATERAL_NAMES[creditor_code]

    if subcategory in ("obligations_privees", "crediteurs_prives"):
        return SENTINEL_PRIVATE, subcategory, None

    # Fallback : nom complet API ou code brut
    name = CREDITOR_NAMES.get(creditor_code, f"creditor_{creditor_code}")
    return SENTINEL_MULTILATERAL, subcategory, name


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


def upsert_rows(conn, debtor_iso3, subcategory, rows):
    data = []
    for row in rows:
        country_from, subcat1, subcat2 = resolve_creditor(
            row["creditor_code"], subcategory
        )
        data.append((
            country_from,
            debtor_iso3,
            "dette_exterieure",
            row["year"],
            row["value"],
            "USD",
            SOURCE,
            subcat1,
            subcat2,
            None,
        ))

    if not data:
        return 0

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
    print("ETL — Dette bilatérale (World Bank IDS)")
    print(f"Période : {ANNEE_DEBUT} → {ANNEE_FIN}")
    print("=" * 60)

    load_creditor_codes()

    print("\nChargement des pays débiteurs...")
    debtor_countries = load_debtor_countries()
    print(f"{len(debtor_countries)} pays débiteurs trouvés.")

    conn = sqlite3.connect(PATH_DB)
    ensure_flux_table(conn)

    # Nettoyage complet des anciennes données dette
    # (ancienne structure subcategory_1 = nom institution, codes creditor_XXX)
    print("  Nettoyage des anciennes données dette_exterieure...")
    conn.execute("DELETE FROM flux WHERE indicator = 'dette_exterieure'")
    conn.commit()
    print("  Nettoyage terminé.")

    total_insere = 0

    for i, debtor in enumerate(debtor_countries):
        print(f"\n→ {debtor} ({i+1}/{len(debtor_countries)})")

        for series_code, subcategory in IDS_INDICATORS.items():
            rows = fetch_ids(debtor, series_code)
            if not rows:
                continue
            nb = upsert_rows(conn, debtor, subcategory, rows)
            total_insere += nb
            print(f"  {subcategory} : {nb} lignes")

        time.sleep(PAUSE)

    conn.close()
    print(f"\n{'='*60}")
    print(f"IDS terminé — {total_insere} lignes au total")
    print(f"{'='*60}")
    return total_insere


if __name__ == "__main__":
    run()
