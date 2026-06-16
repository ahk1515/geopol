# =============================================================
# GÉOPOL — DIAGNOSTIC DISTRIBUTION DES FLUX v2 (lecture seule)
# =============================================================
# Version élargie : couvre TOUS les indicateurs de flux présents,
# détecte l'unité de chacun, et applique des paliers de seuil
# ADAPTÉS à l'unité (USD vs personnes vs indice TIV…).
#
# NE MODIFIE RIEN. Lecture seule. Imprime dans les logs.
#
# Lancement : appelé depuis run_etl (bloc DIAGNOSTIC TEMPORAIRE),
#   ou seul :  python -m etl.diag_flux
#
# À RETIRER une fois les seuils calibrés.
# =============================================================

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import PATH_DB

PALIERS_PAR_FAMILLE = {
    "monetaire": [1e5, 1e6, 1e7, 5e7, 1e8],
    "effectif":  [10, 25, 50, 100, 500, 1000],
    "indice":    [1, 5, 10, 50, 100],
    "compte":    [1, 2, 5, 10],
    "autre":     [1, 10, 100, 1000, 10000],
}
PALIERS_REL = [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005]


def unit_family(unit):
    if not unit:
        return "autre"
    u = unit.lower()
    if any(k in u for k in ("usd", "eur", "dollar", "€", "$")):
        return "monetaire"
    if any(k in u for k in ("person", "pers", "habitant", "migrant", "étud", "etud", "réfug", "refug", "élève", "eleve")):
        return "effectif"
    if "tiv" in u:
        return "indice"
    if any(k in u for k in ("nombre", "nb", "compte", "unité", "unite", "poste", "représ", "repres")):
        return "compte"
    return "autre"


def is_sentinel(code):
    if not code:
        return True
    if code.startswith("__"):
        return True
    if len(code) == 3 and code[0] == "G" and code[1:].isdigit():
        return True
    if len(code) != 3:
        return True
    return False


def dominant_unit(conn, indicator):
    rows = conn.execute(
        "SELECT unit, COUNT(*) FROM flux WHERE indicator=? AND value IS NOT NULL GROUP BY unit ORDER BY COUNT(*) DESC",
        (indicator,)
    ).fetchall()
    if not rows:
        return None, []
    return rows[0][0], rows


def fmt(v):
    try:
        return f"{v:,.0f}"
    except Exception:
        return str(v)


def diag_bilateral(conn, indicator):
    tot_to, tot_from = {}, {}
    for c, y, v in conn.execute(
        "SELECT country_to, year, SUM(value) FROM flux WHERE indicator=? AND value>0 GROUP BY country_to, year",
        (indicator,)
    ):
        tot_to[(c, y)] = v
    for c, y, v in conn.execute(
        "SELECT country_from, year, SUM(value) FROM flux WHERE indicator=? AND value>0 GROUP BY country_from, year",
        (indicator,)
    ):
        tot_from[(c, y)] = v
    parts = []
    n_sent = 0
    for cf, ct, y, v in conn.execute(
        "SELECT country_from, country_to, year, value FROM flux WHERE indicator=? AND value>0",
        (indicator,)
    ):
        if is_sentinel(cf) or is_sentinel(ct):
            n_sent += 1
            continue
        tt = tot_to.get((ct, y), 0)
        tf = tot_from.get((cf, y), 0)
        pt = v / tt if tt else 0
        pf = v / tf if tf else 0
        parts.append((v, pt, pf))
    n = len(parts)
    if n == 0:
        print("    (aucune ligne exploitable pour le relatif)")
        return
    total = sum(p[0] for p in parts)
    if n_sent:
        print(f"    ({n_sent:,} lignes sentinelles/agrégats exclues du relatif)")
    print(f"    impact seuil RELATIF BILATÉRAL (coupe si < seuil chez A ET chez B) :")
    for s in PALIERS_REL:
        coupe = [(v, pt, pf) for (v, pt, pf) in parts if pt < s and pf < s]
        nc = len(coupe)
        vc = sum(c[0] for c in coupe)
        print(f"      < {s*100:6.3f}% des 2 côtés : {nc:>7,} lignes ({nc*100/n:4.1f}%)  "
              f"perte valeur {vc*100/total:6.2f}%")


def diag_indicator(conn, indicator):
    print(f"\n{'-'*60}")
    print(f"> {indicator}")
    print(f"{'-'*60}")
    unit, unit_breakdown = dominant_unit(conn, indicator)
    fam = unit_family(unit)
    print(f"    unite dominante : '{unit}'  -> famille : {fam}")
    if len(unit_breakdown) > 1:
        autres = ", ".join(f"'{u}'x{n}" for u, n in unit_breakdown[1:4])
        print(f"    (autres unites presentes : {autres})")
    vals = [r[0] for r in conn.execute(
        "SELECT value FROM flux WHERE indicator=? AND value IS NOT NULL AND value>0 ORDER BY value",
        (indicator,)
    )]
    n = len(vals)
    if n == 0:
        print("    (aucune ligne avec valeur > 0)")
        return
    total = sum(vals)
    print(f"    lignes  : {n:,}")
    print(f"    min/max : {fmt(vals[0])} / {fmt(vals[-1])}")
    print(f"    mediane : {fmt(vals[n//2])}")
    print(f"    moyenne : {fmt(total/n)}")
    print(f"    total   : {fmt(total)}")
    print(f"    deciles :")
    for d in range(1, 10):
        idx = min(int(n * d / 10), n - 1)
        print(f"      {d*10:>3}% <= {fmt(vals[idx])}")
    paliers = PALIERS_PAR_FAMILLE.get(fam, PALIERS_PAR_FAMILLE["autre"])
    unit_lbl = unit or "?"
    print(f"    impact seuil ABSOLU (paliers en '{unit_lbl}') :")
    for s in paliers:
        coupe = [v for v in vals if v < s]
        nc = len(coupe)
        vc = sum(coupe)
        print(f"      < {fmt(s):>15} : {nc:>7,} lignes ({nc*100/n:4.1f}%)  "
              f"perte totale {vc*100/total:6.2f}%")
    if fam == "monetaire":
        diag_bilateral(conn, indicator)
    else:
        print(f"    (seuil relatif bilateral non pertinent pour unite '{unit_lbl}')")


def run():
    print("=" * 64)
    print("DIAGNOSTIC DISTRIBUTION DES FLUX v2 (lecture seule)")
    print("=" * 64)
    if not os.path.exists(PATH_DB):
        print(f"DB introuvable : {PATH_DB}")
        return 0
    conn = sqlite3.connect(PATH_DB)
    present = sorted(r[0] for r in conn.execute("SELECT DISTINCT indicator FROM flux") if r[0])
    a_diagnostiquer = [i for i in present if i != "export_commercial"]
    print(f"\nIndicateurs de flux presents : {present}")
    print(f"Diagnostiques (hors doublon export_commercial) : {a_diagnostiquer}")
    counts = {}
    for ind in a_diagnostiquer:
        counts[ind] = conn.execute(
            "SELECT COUNT(*) FROM flux WHERE indicator=? AND value IS NOT NULL", (ind,)
        ).fetchone()[0]
    ordre = sorted(a_diagnostiquer, key=lambda i: counts[i], reverse=True)
    print(f"\nClassement par volume de lignes :")
    for ind in ordre:
        print(f"    {counts[ind]:>9,}  {ind}")
    for ind in ordre:
        diag_indicator(conn, ind)
    conn.close()
    print(f"\n{'='*64}")
    print("Diagnostic v2 termine. Aucune donnee modifiee.")
    print(f"{'='*64}")
    return 0


if __name__ == "__main__":
    run()
