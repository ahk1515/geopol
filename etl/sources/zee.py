# =============================================================
# GÉOPOL — Parser Zone Économique Exclusive (ZEE)
# Source : Flanders Marine Institute — Marine Regions
# https://www.marineregions.org/
#
# Schéma identite :
#   indicator    = zee
#   subcategory  = None
#   year         = 2023 (version v12 du dataset)
#   value        = surface ZEE totale en km²
#   unit         = km²
#
# Méthode :
#   - Interroge le WFS GeoServer de Marine Regions
#   - Filtre POL_TYPE = '200NM' uniquement (ZEE maritime)
#   - Agrège par ISO_SOV1 (État souverain) → somme AREA_KM2
#   - Joint regimes comptés à 100% dans chaque État
#
# Source automatique — tourne dans le pipeline standard.
# Données quasi-statiques (version dataset : 2023).
# =============================================================

import sqlite3
import requests
import time
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import PATH_DB

SOURCE    = "Marine Regions"
UNIT      = "km2"
YEAR      = 2023  # version v12 du dataset Marine Regions
PAUSE     = 1.0
PAGE_SIZE = 500

WFS_URL = (
    "https://geo.vliz.be/geoserver/MarineRegions/ows"
    "?service=WFS"
    "&version=1.0.0"
    "&request=GetFeature"
    "&typeName=MarineRegions:eez"
    "&outputFormat=application/json"
    "&propertyName=ISO_SOV1,ISO_SOV2,ISO_SOV3,POL_TYPE,AREA_KM2"
    "&maxFeatures={page_size}"
    "&startIndex={start}"
)

# Codes ISO3 non standard dans Marine Regions → ISO3 GÉOPOL
MR_ISO3_FIX = {
    "XKX": "XKX",   # Kosovo — déjà correct
    "TWN": "TWN",   # Taiwan
    "PSE": "PSE",   # Palestine
    "ESH": "ESH",   # Sahara occidental
}

# Entités à ignorer (haute mer, zones sans État souverain)
IGNORE_ISO3 = {"HSP", "ATA", None, ""}


def fetch_page(start):
    """Récupère une page de features WFS."""
    url = WFS_URL.format(page_size=PAGE_SIZE, start=start)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def run():
    print("=" * 60)
    print("ETL — Zone Économique Exclusive (Marine Regions v12)")
    print("=" * 60)

    # Agréger AREA_KM2 par ISO_SOV1
    zee_by_country = defaultdict(float)
    total_features = 0
    start = 0

    print("\n→ Téléchargement WFS...")
    while True:
        try:
            data = fetch_page(start)
        except Exception as e:
            print(f"  ❌ Erreur page start={start} : {e}")
            break

        features = data.get("features", [])
        if not features:
            break

        for feat in features:
            props    = feat.get("properties", {})
            pol_type = props.get("POL_TYPE", "")
            area     = props.get("AREA_KM2")
            iso_sov1 = props.get("ISO_SOV1", "")
            iso_sov2 = props.get("ISO_SOV2", "")
            iso_sov3 = props.get("ISO_SOV3", "")

            # Filtrer uniquement ZEE 200NM
            if pol_type not in ("200NM", "200NM (partial)"):
                continue

            if not area or float(area) <= 0:
                continue

            area = float(area)

            # Attribuer à chaque souverain (joint regime → 100% dans chacun)
            for iso3 in [iso_sov1, iso_sov2, iso_sov3]:
                if iso3 and iso3 not in IGNORE_ISO3 and len(iso3) == 3:
                    iso3 = MR_ISO3_FIX.get(iso3, iso3)
                    zee_by_country[iso3] += area

        total_features += len(features)
        print(f"  {total_features} polygones traités...", end='\r')

        if len(features) < PAGE_SIZE:
            break

        start += PAGE_SIZE
        time.sleep(PAUSE)

    print(f"\n  {total_features} polygones traités au total")
    print(f"  {len(zee_by_country)} pays avec ZEE")

    if not zee_by_country:
        print("  ❌ Aucune donnée récupérée")
        return 0

    # Insertion en base
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

    # Supprimer les anciennes données ZEE avant réinsertion
    conn.execute("DELETE FROM identite WHERE indicator = 'zee' AND source = ?", (SOURCE,))

    rows = [
        (iso3, "zee", YEAR, round(area, 1), UNIT, SOURCE, None)
        for iso3, area in sorted(zee_by_country.items())
    ]

    conn.executemany("""
        INSERT OR REPLACE INTO identite
            (country_iso3, indicator, year, value, unit, source, subcategory)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"ZEE terminé — {len(rows)} pays insérés")
    # Top 5 pour vérification
    top5 = sorted(zee_by_country.items(), key=lambda x: -x[1])[:5]
    print("Top 5 :")
    for iso3, area in top5:
        print(f"  {iso3} : {area:,.0f} km²")
    print(f"{'='*60}")
    return len(rows)


if __name__ == "__main__":
    run()
