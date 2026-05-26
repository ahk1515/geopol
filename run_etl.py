# =============================================================
# GÉOPOL — Orchestrateur ETL principal
# Appelle tous les scripts dans le bon ordre
# Agrège les statuts pour status.json
#
# Ordre d'exécution :
#   1. Sources automatiques (APIs)
#   2. Indicateurs construits
#   3. Assemblage + upload R2
# =============================================================

import sys
import os
import json
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etl.config import PATH_DB, PATH_STATUS, load_admin_config

# -------------------------------------------------------------
# IMPORT DES SCRIPTS ETL
# -------------------------------------------------------------
from etl.sources import banque_mondiale, owid, comtrade, unhcr, etudiants, banque_mondiale_ids, sipri, manuel, energy_institute
from etl import construits, build_db

# -------------------------------------------------------------
# PIPELINE
# -------------------------------------------------------------

# Ordre d'exécution avec métadonnées
PIPELINE = [
    {
        "id":          "banque_mondiale",
        "label":       "Banque Mondiale",
        "module":      banque_mondiale,
        "type":        "automatique",
        "obligatoire": True,
    },
    {
        "id":          "owid",
        "label":       "Our World In Data",
        "module":      owid,
        "type":        "automatique",
        "obligatoire": False,
    },
    {
        "id":          "comtrade",
        "label":       "UN Comtrade",
        "module":      comtrade,
        "type":        "automatique",
        "obligatoire": False,
    },
    {
        "id":          "unhcr",
        "label":       "UNHCR Réfugiés",
        "module":      unhcr,
        "type":        "automatique",
        "obligatoire": False,
    },
    {
        "id":          "banque_mondiale_ids",
        "label":       "Dette bilatérale (IDS)",
        "module":      banque_mondiale_ids,
        "type":        "automatique",
        "obligatoire": False,
    },
    {
        "id":          "sipri",
        "label":       "SIPRI Arms Transfers",
        "module":      sipri,
        "type":        "semi-automatique",
        "obligatoire": False,
    },
    {
        "id":          "energy_institute",
        "label":       "Energy Institute",
        "module":      energy_institute,
        "type":        "semi-automatique",
        "obligatoire": False,
    },
    {
        "id":          "manuel",
        "label":       "Imports manuels (IA)",
        "module":      manuel,
        "type":        "manuel",
        "obligatoire": False,
    },
    # Étudiants internationaux — désactivé temporairement
    # En attente d'inspection du fichier OPRI.zip (UNESCO)
    # {
    #     "id":          "etudiants",
    #     "label":       "Étudiants internationaux",
    #     "module":      etudiants,
    #     "type":        "automatique",
    #     "obligatoire": False,
    # },
]

# -------------------------------------------------------------
# EXÉCUTION
# -------------------------------------------------------------

def run_step(step):
    """
    Exécute un step du pipeline.
    Retourne un dict de statut.
    """
    start  = datetime.now(timezone.utc)
    status = {
        "id":         step["id"],
        "label":      step["label"],
        "type":       step["type"],
        "start":      start.isoformat(),
        "end":        None,
        "status":     "pending",
        "rows":       0,
        "error":      None,
    }

    try:
        rows = step["module"].run()
        status["rows"]   = rows or 0
        status["status"] = "ok"
        print(f"\n✅ {step['label']} — {status['rows']} lignes")
    except Exception as e:
        status["status"] = "error"
        status["error"]  = str(e)
        tb = traceback.format_exc()
        print(f"\n❌ {step['label']} — ERREUR : {e}")
        print(tb)

        if step.get("obligatoire"):
            print("  Step obligatoire échoué — arrêt du pipeline.")
            raise

    status["end"] = datetime.now(timezone.utc).isoformat()
    return status


def run():
    print("=" * 60)
    print("GÉOPOL — Pipeline ETL complet")
    print(f"Démarrage : {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Rechargement config admin (antériorité, pays, etc.)
    load_admin_config()

    sources_status = {}
    pipeline_ok    = True

    # ── Étape 1 : Sources automatiques ──────────────────────
    print("\n\n━━ SOURCES AUTOMATIQUES ━━")
    for step in PIPELINE:
        print(f"\n{'─'*40}")
        print(f"  {step['label']}")
        print(f"{'─'*40}")
        try:
            status = run_step(step)
        except Exception:
            pipeline_ok = False
            break
        sources_status[step["id"]] = status

    if not pipeline_ok:
        print("\n❌ Pipeline interrompu sur step obligatoire.")
        sys.exit(1)

    # ── Étape 2 : Indicateurs construits ────────────────────
    print(f"\n\n{'─'*40}")
    print("━━ INDICATEURS CONSTRUITS ━━")
    print(f"{'─'*40}")
    try:
        nb_construits = construits.run()
        sources_status["construits"] = {
            "id":     "construits",
            "label":  "Indicateurs construits",
            "type":   "calcul",
            "status": "ok",
            "rows":   nb_construits,
            "error":  None,
        }
    except Exception as e:
        print(f"❌ Erreur indicateurs construits : {e}")
        sources_status["construits"] = {
            "id":     "construits",
            "label":  "Indicateurs construits",
            "type":   "calcul",
            "status": "error",
            "rows":   0,
            "error":  str(e),
        }

    # ── Étape 3 : Assemblage + upload ───────────────────────
    print(f"\n\n{'─'*40}")
    print("━━ ASSEMBLAGE ET UPLOAD ━━")
    print(f"{'─'*40}")
    try:
        build_db.run(sources_status=sources_status)
    except SystemExit as e:
        # build_db peut appeler sys.exit(1) si DB trop grosse
        print(f"\n❌ Build interrompu (code {e.code})")
        sys.exit(e.code)
    except Exception as e:
        print(f"\n❌ Erreur build : {e}")
        sys.exit(1)

    # ── Résumé final ─────────────────────────────────────────
    print(f"\n\n{'='*60}")
    print("RÉSUMÉ DU PIPELINE")
    print(f"{'='*60}")
    for sid, s in sources_status.items():
        icon  = "✅" if s["status"] == "ok" else "❌"
        rows  = s.get("rows", 0)
        error = f" — {s['error']}" if s.get("error") else ""
        print(f"  {icon}  {s['label']:<35} {rows:>8} lignes{error}")

    total = sum(s.get("rows", 0) for s in sources_status.values())
    print(f"\n  Total : {total} lignes insérées/mises à jour")
    print(f"  Fin   : {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
