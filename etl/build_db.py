# =============================================================
# GÉOPOL — Assemblage final et upload vers Cloudflare R2
# Tourne en dernier dans le pipeline ETL
# 
# Actions :
#   1. Vérifie la taille de la DB (alerte si > seuil)
#   2. Optimise la DB (VACUUM + index)
#   3. Upload vers Cloudflare R2
#   4. Écrit status.json sur R2 (lu par admin.html)
# =============================================================

import sqlite3
import requests
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import PATH_DB, PATH_STATUS

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
DB_SIZE_LIMIT_MB  = 450    # alerte si DB dépasse ce seuil (avant 500Mo)
DB_SIZE_ALERT_MB  = 480    # erreur bloquante si dépasse ce seuil

# Variables d'environnement (secrets GitHub Actions)
R2_ACCOUNT_ID    = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_KEY    = os.environ.get("R2_SECRET_KEY")
R2_BUCKET        = os.environ.get("R2_BUCKET", "geopol-db")
R2_PUBLIC_URL    = os.environ.get("R2_PUBLIC_URL")  # URL pub R2

# -------------------------------------------------------------
# VÉRIFICATION TAILLE
# -------------------------------------------------------------

def check_db_size():
    """
    Vérifie la taille de la DB et retourne (taille_mb, statut).
    statut : 'ok', 'warning', 'error'
    """
    if not os.path.exists(PATH_DB):
        raise FileNotFoundError(f"DB introuvable : {PATH_DB}")

    size_bytes = os.path.getsize(PATH_DB)
    size_mb    = size_bytes / (1024 * 1024)

    if size_mb > DB_SIZE_ALERT_MB:
        return size_mb, "error"
    elif size_mb > DB_SIZE_LIMIT_MB:
        return size_mb, "warning"
    return size_mb, "ok"


# -------------------------------------------------------------
# OPTIMISATION DB
# -------------------------------------------------------------

def optimize_db():
    """
    VACUUM : recalcule l'espace, réduit la taille.
    Index : accélère les requêtes fréquentes de l'app.
    """
    conn = sqlite3.connect(PATH_DB)

    print("  Création des index...")
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_identite_country
            ON identite (country_iso3, indicator, year);

        CREATE INDEX IF NOT EXISTS idx_flux_from
            ON flux (country_from, indicator, year);

        CREATE INDEX IF NOT EXISTS idx_flux_to
            ON flux (country_to, indicator, year);

        CREATE INDEX IF NOT EXISTS idx_flux_bilateral
            ON flux (country_from, country_to, indicator, year);
    """)

    print("  VACUUM en cours (peut prendre quelques secondes)...")
    conn.execute("VACUUM")
    conn.close()
    print("  Optimisation terminée.")


# -------------------------------------------------------------
# STATISTIQUES DB
# -------------------------------------------------------------

def get_db_stats():
    """Retourne des statistiques basiques sur le contenu de la DB."""
    conn = sqlite3.connect(PATH_DB)
    stats = {}

    try:
        stats["nb_pays_identite"] = conn.execute(
            "SELECT COUNT(DISTINCT country_iso3) FROM identite"
        ).fetchone()[0]

        stats["nb_indicateurs_identite"] = conn.execute(
            "SELECT COUNT(DISTINCT indicator) FROM identite"
        ).fetchone()[0]

        stats["nb_lignes_identite"] = conn.execute(
            "SELECT COUNT(*) FROM identite"
        ).fetchone()[0]

        stats["nb_pays_flux"] = conn.execute(
            "SELECT COUNT(DISTINCT country_from) FROM flux"
        ).fetchone()[0]

        stats["nb_indicateurs_flux"] = conn.execute(
            "SELECT COUNT(DISTINCT indicator) FROM flux"
        ).fetchone()[0]

        stats["nb_lignes_flux"] = conn.execute(
            "SELECT COUNT(*) FROM flux"
        ).fetchone()[0]

        stats["annee_min"] = conn.execute(
            "SELECT MIN(year) FROM identite"
        ).fetchone()[0]

        stats["annee_max"] = conn.execute(
            "SELECT MAX(year) FROM identite"
        ).fetchone()[0]

    except Exception as e:
        print(f"  ⚠️  Erreur stats : {e}")

    conn.close()
    return stats


# -------------------------------------------------------------
# UPLOAD VERS R2
# -------------------------------------------------------------

def upload_to_r2(local_path, remote_key):
    """
    Upload un fichier vers Cloudflare R2 via l'API S3-compatible.
    Utilise boto3 si disponible, sinon requests avec signature AWS4.
    """
    try:
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

        file_size = os.path.getsize(local_path)
        print(f"  Upload de {remote_key} ({file_size / 1024 / 1024:.1f} Mo)...")

        with open(local_path, "rb") as f:
            s3.upload_fileobj(
                f,
                R2_BUCKET,
                remote_key,
                ExtraArgs={"ContentType": "application/octet-stream"},
            )

        print(f"  ✅ Upload terminé.")
        return True

    except ImportError:
        print("  ⚠️  boto3 non disponible — upload ignoré.")
        print("       Ajoute boto3 aux dépendances GitHub Actions.")
        return False
    except Exception as e:
        print(f"  ❌ Erreur upload R2 : {e}")
        return False


# -------------------------------------------------------------
# STATUS.JSON
# -------------------------------------------------------------

def write_status(stats, size_mb, size_status, upload_ok, sources_status):
    """
    Écrit status.json localement puis l'uploade sur R2.
    Ce fichier est lu par admin.html pour afficher le tableau de bord.
    """
    status = {
        "last_run":       datetime.now(timezone.utc).isoformat(),
        "db_size_mb":     round(size_mb, 1),
        "db_size_status": size_status,
        "upload_ok":      upload_ok,
        "stats":          stats,
        "sources":        sources_status,
    }

    # Sauvegarde locale
    with open(PATH_STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    # Upload sur R2
    if upload_ok:
        upload_to_r2(PATH_STATUS, "status.json")

    return status


# -------------------------------------------------------------
# TABLE ZONES (groupes prédéfinis pour l'app)
# -------------------------------------------------------------

def build_zones(referentiel_path=None):
    """
    Peuple la table zones dans la DB depuis referentiel.json.
    Chaque organisation devient un groupe sélectionnable dans l'app.
    """
    # Chercher referentiel.json
    if not referentiel_path:
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "referentiel.json"),
            "referentiel.json",
        ]
        for c in candidates:
            if os.path.exists(c):
                referentiel_path = c
                break

    if not referentiel_path or not os.path.exists(referentiel_path):
        print("  ⚠️  referentiel.json non trouvé — table zones ignorée")
        return 0

    with open(referentiel_path, encoding="utf-8") as f:
        referentiel = json.load(f)

    # Noms complets des organisations
    ORG_NOMS = {
        "OTAN": "OTAN", "UE": "Union Européenne", "OCDE": "OCDE",
        "G7": "G7", "G20": "G20", "BRICS": "BRICS",
        "OCS": "Organisation de Coopération de Shanghai",
        "OTSC": "Organisation du Traité de Sécurité Collective",
        "OPEP": "OPEP", "OPEP+": "OPEP+",
        "ASEAN": "ASEAN", "ANZUS": "ANZUS",
        "Five Eyes": "Five Eyes", "QUAD": "QUAD", "AUKUS": "AUKUS",
        "LA": "Ligue Arabe", "MERCOSUR": "MERCOSUR",
        "UNASUR": "UNASUR", "ACEUM": "ACEUM", "CELAC": "CELAC",
        "UA": "Union Africaine", "CEDEAO": "CEDEAO",
        "CEEAC": "CEEAC", "IGAD": "IGAD", "SADC": "SADC",
        "EAC": "EAC", "COI": "Commission Océan Indien",
        "UMA": "Union du Maghreb Arabe", "CEN-SAD": "CEN-SAD",
        "COMESA": "COMESA", "OEA": "OEA", "ALBA": "ALBA",
        "CARICOM": "CARICOM", "Commonwealth": "Commonwealth",
        "Francophonie": "Francophonie", "APEC": "APEC",
        "SAARC": "SAARC", "PIF": "Forum Îles du Pacifique",
        "RCEP": "RCEP", "CEI": "CEI",
        "Conseil Europe": "Conseil de l'Europe",
        "OMC": "OMC", "AIIB": "AIIB", "GAFI": "GAFI",
        "BRI": "Initiative Ceinture et Route", "IEA": "IEA",
        "GECF": "GECF", "TNP": "TNP", "CPI": "CPI",
        "Paris": "Accord de Paris", "CNUDM": "CNUDM",
        "CWC": "Convention Armes Chimiques", "ATT": "Traité Commerce Armes",
    }

    # Groupes géographiques depuis continent/région
    GEO_GROUPES = {}
    for iso3, data in referentiel.items():
        continent = data.get("continent", "")
        region    = data.get("region", "")
        if continent:
            GEO_GROUPES.setdefault(f"GEO_{continent}", {"nom": continent, "pays": []})
            GEO_GROUPES[f"GEO_{continent}"]["pays"].append(iso3)
        if region:
            key = f"GEO_{region.replace(' ', '_')}"
            GEO_GROUPES.setdefault(key, {"nom": region, "pays": []})
            GEO_GROUPES[key]["pays"].append(iso3)

    # Construction des zones organisations
    zones = {}  # zone_id -> {nom, pays: set}
    STATUTS_MEMBRES = {"membre", "ratifié", "signataire", "allié", "partenaire"}

    for iso3, data in referentiel.items():
        for org, statut in data.get("organisations", {}).items():
            if statut in STATUTS_MEMBRES:
                if org not in zones:
                    zones[org] = {"nom": ORG_NOMS.get(org, org), "pays": set()}
                zones[org]["pays"].add(iso3)

    # Insertion en DB
    conn = sqlite3.connect(PATH_DB)
    conn.execute("DROP TABLE IF EXISTS zones")
    conn.execute("""
        CREATE TABLE zones (
            zone_id      TEXT,
            zone_nom     TEXT,
            country_iso3 TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zones_id ON zones(zone_id)")

    rows = []
    # Organisations
    for zone_id, data in zones.items():
        for iso3 in sorted(data["pays"]):
            rows.append((zone_id, data["nom"], iso3))

    # Groupes géographiques
    for zone_id, data in GEO_GROUPES.items():
        for iso3 in sorted(data["pays"]):
            rows.append((zone_id, data["nom"], iso3))

    conn.executemany(
        "INSERT INTO zones (zone_id, zone_nom, country_iso3) VALUES (?, ?, ?)",
        rows
    )
    conn.commit()

    nb_zones = len(zones) + len(GEO_GROUPES)
    nb_rows  = len(rows)
    conn.close()

    print(f"  ✅ {nb_zones} groupes créés ({nb_rows} lignes)")
    return nb_rows


# -------------------------------------------------------------
# POINT D'ENTRÉE
# -------------------------------------------------------------

def run(sources_status=None):
    """
    sources_status : dict optionnel passé par le pipeline principal
    Format : {"banque_mondiale": {"status": "ok", "rows": 12000}, ...}
    """
    print("=" * 60)
    print("BUILD — Assemblage final et upload R2")
    print("=" * 60)

    # 1. Vérification taille
    print("\n→ Vérification taille DB")
    size_mb, size_status = check_db_size()
    print(f"  Taille : {size_mb:.1f} Mo — statut : {size_status}")

    if size_status == "error":
        print(f"  ❌ DB trop volumineuse ({size_mb:.1f} Mo > {DB_SIZE_ALERT_MB} Mo)")
        print("     Réduis l'antériorité dans admin.html avant de continuer.")
        sys.exit(1)
    elif size_status == "warning":
        print(f"  ⚠️  Attention : DB approche la limite ({size_mb:.1f} Mo)")

    # 2. Construction table zones
    print("\n→ Construction table zones")
    build_zones()

    # 3. Optimisation
    print("\n→ Optimisation DB")
    optimize_db()

    # Taille post-optimisation
    size_mb_post = os.path.getsize(PATH_DB) / (1024 * 1024)
    print(f"  Taille après optimisation : {size_mb_post:.1f} Mo")

    # 3. Statistiques
    print("\n→ Statistiques DB")
    stats = get_db_stats()
    for k, v in stats.items():
        print(f"  {k} : {v}")

    # 4. Upload DB vers R2
    print("\n→ Upload DB vers R2")
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_KEY]):
        print("  ⚠️  Secrets R2 manquants — upload ignoré (mode local)")
        upload_ok = False
    else:
        upload_ok = upload_to_r2(PATH_DB, "geopolitique.db")

    # 5. Écriture status.json
    print("\n→ Écriture status.json")
    status = write_status(
        stats         = stats,
        size_mb       = size_mb_post,
        size_status   = size_status,
        upload_ok     = upload_ok,
        sources_status = sources_status or {},
    )
    print(f"  ✅ status.json écrit")

    print(f"\n{'='*60}")
    print(f"BUILD terminé")
    if upload_ok:
        print(f"DB disponible sur R2")
    print(f"{'='*60}")

    return upload_ok


if __name__ == "__main__":
    run()
