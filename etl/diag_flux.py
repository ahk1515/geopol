# =============================================================
# GÉOPOL — DIAGNOSTIC DE DISTRIBUTION DES FLUX (lecture seule)
# =============================================================
# But : mesurer, indicateur par indicateur, la distribution des
#       valeurs et l'impact de différents seuils de filtrage,
#       AVANT de décider quels seuils appliquer.
#
# NE MODIFIE RIEN. N'écrit aucune ligne. Lecture seule.
# Imprime tout dans les logs (lisible dans GitHub Actions).
#
# Lancement : ajouter temporairement au pipeline, ou exécuter seul.
#   python -m etl.diag_flux         (depuis la racine du repo)
#
# À RETIRER une fois le diagnostic fait.
# =============================================================

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.config import PATH_DB

# Indicateurs de flux à diagnostiquer.
# Pour le commerce : SEULEMENT import_commercial (export_commercial est un
# doublon exact, le mesurer compterait deux fois la même réalité).
FLUX_INDICATORS = [
    "import_commercial",
    "dette_exterieure",
    "refugies",
    "transferts_armement",
    "commerce_ressources",
]

# Paliers de part relative testés (en fraction : 0.0005 = 0,05 %)
PALIERS_REL = [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005]

# Paliers absolus testés (USD) — pour les flux où le relatif n'a pas de sens
PALIERS_ABS = [1e5, 1e6, 1e7, 5e7, 1e8]

# Codes d'agrégats / sentinelles à ne JAMAIS compter comme partenaires.
# Agrégats IMF (G001…), sentinelles dette (__multilateral__…), etc.
def is_sentinel(code):
    if not code:
        return True
    if code.startswith("__"):   # sentinelles dette : __multilateral__, __private__, __bondholders__
        return True
    if len(code) == 3 and code[0] == "G" and code[1:].isdigit():  # G001, G998…
        return True
    if len(code) != 3:
        return True
    return False


def list_indicators_present(conn):
    """Quels indicateurs de flux existent réellement en base."""
    rows = conn.execute("SELECT DISTINCT indicator FROM flux").fetchall()
    return sorted(r[0] for r in rows if r[0])


def diag_basic(conn, indicator):
    """Distribution brute : nb lignes, min, médiane (approx), moyenne, max, total."""
    rows = conn.execute("""
        SELECT value FROM flux
        WHERE indicator = ? AND value IS NOT NULL AND value > 0
        ORDER BY value
    """, (indicator,)).fetchall()
    vals = [r[0] for r in rows]
    n = len(vals)
    if n == 0:
        print(f"    (aucune ligne)")
        return
    total = sum(vals)
    med = vals[n // 2]
    moy = total / n
    print(f"    lignes      : {n:,}")
    print(f"    min / max   : {vals[0]:,.0f}  /  {vals[-1]:,.0f}")
    print(f"    médiane     : {med:,.0f}")
    print(f"    moyenne     : {moy:,.0f}")
    print(f"    total       : {total:,.0f}")
    # déciles : où se situent les coupures naturelles
    print(f"    déciles de valeur :")
    for d in range(1, 10):
        idx = int(n * d / 10)
        print(f"      {d*10:>3}% des lignes ont une valeur ≤ {vals[idx]:,.0f}")


def diag_seuil_absolu(conn, indicator):
    """Combien de lignes / quelle part de la valeur seraient coupées par seuil absolu."""
    rows = conn.execute("""
        SELECT value FROM flux
        WHERE indicator = ? AND value IS NOT NULL AND value > 0
    """, (indicator,)).fetchall()
    vals = [r[0] for r in rows]
    n = len(vals)
    if n == 0:
        return
    total = sum(vals)
    print(f"    impact seuil ABSOLU (lignes coupées / valeur perdue) :")
    for s in PALIERS_ABS:
        coupe = [v for v in vals if v < s]
        nc = len(coupe)
        vc = sum(coupe)
        print(f"      < {s:>13,.0f} USD : {nc:>7,} lignes ({nc*100/n:4.1f}%)  "
              f"perte valeur {vc*100/total:5.2f}%")


def diag_seuil_bilateral(conn, indicator, paire_to_col, paire_from_col):
    """
    Impact d'un seuil RELATIF bilatéral : on coupe une ligne si sa part est
    sous le seuil À LA FOIS chez l'importateur (côté `to`) ET chez le
    fournisseur (côté `from`). Règle : supprimer si petit des DEUX côtés.

    paire_to_col / paire_from_col : noms de colonnes selon la sémantique du flux.
      Pour import_commercial : to=importateur, from=fournisseur.
    """
    # Totaux par acteur, dans chaque rôle, par année
    tot_to = {}
    for c, y, v in conn.execute(f"""
        SELECT {paire_to_col}, year, SUM(value) FROM flux
        WHERE indicator=? AND value>0 GROUP BY {paire_to_col}, year
    """, (indicator,)):
        tot_to[(c, y)] = v
    tot_from = {}
    for c, y, v in conn.execute(f"""
        SELECT {paire_from_col}, year, SUM(value) FROM flux
        WHERE indicator=? AND value>0 GROUP BY {paire_from_col}, year
    """, (indicator,)):
        tot_from[(c, y)] = v

    # Parcours des lignes, calcul des deux parts
    rows = conn.execute(f"""
        SELECT {paire_from_col}, {paire_to_col}, year, value FROM flux
        WHERE indicator=? AND value>0
    """, (indicator,)).fetchall()

    parts = []   # (value, part_to, part_from)
    n_sentinel = 0
    for cf, ct, y, v in rows:
        if is_sentinel(cf) or is_sentinel(ct):
            n_sentinel += 1
            continue
        tt = tot_to.get((ct, y), 0)
        tf = tot_from.get((cf, y), 0)
        pt = v / tt if tt else 0
        pf = v / tf if tf else 0
        parts.append((v, pt, pf))

    n = len(parts)
    if n == 0:
        print(f"    (aucune ligne exploitable après exclusion sentinelles)")
        return
    total = sum(p[0] for p in parts)
    if n_sentinel:
        print(f"    ({n_sentinel:,} lignes sentinelles/agrégats exclues du calcul)")
    print(f"    impact seuil RELATIF BILATÉRAL (coupe si < seuil chez A ET chez B) :")
    for s in PALIERS_REL:
        coupe = [(v, pt, pf) for (v, pt, pf) in parts if pt < s and pf < s]
        nc = len(coupe)
        vc = sum(c[0] for c in coupe)
        print(f"      < {s*100:5.3f}% des deux côtés : {nc:>7,} lignes ({nc*100/n:4.1f}%)  "
              f"perte valeur {vc*100/total:5.2f}%")


def run():
    print("=" * 64)
    print("DIAGNOSTIC DISTRIBUTION DES FLUX (lecture seule, aucune écriture)")
    print("=" * 64)

    if not os.path.exists(PATH_DB):
        print(f"❌ DB introuvable : {PATH_DB}")
        return 0

    conn = sqlite3.connect(PATH_DB)

    present = list_indicators_present(conn)
    print(f"\nIndicateurs de flux présents en base : {present}\n")

    for ind in FLUX_INDICATORS:
        if ind not in present:
            print(f"\n{'─'*60}\n▸ {ind} — ABSENT de la base, ignoré.")
            continue
        print(f"\n{'─'*60}")
        print(f"▸ {ind}")
        print(f"{'─'*60}")
        diag_basic(conn, ind)
        print()
        # Seuil absolu : utile pour tous
        diag_seuil_absolu(conn, ind)
        print()
        # Seuil relatif bilatéral : surtout pertinent pour le commerce.
        # Pour import_commercial : to=importateur, from=fournisseur.
        if ind == "import_commercial":
            diag_seuil_bilateral(conn, ind, "country_to", "country_from")
        elif ind == "dette_exterieure":
            # dette : country_to = débiteur, country_from = créancier (selon convention IDS)
            diag_seuil_bilateral(conn, ind, "country_to", "country_from")
        else:
            print("    (seuil relatif bilatéral non calculé pour ce flux — "
                  "voir seuil absolu ci-dessus)")

    conn.close()
    print(f"\n{'='*64}")
    print("Diagnostic terminé. Aucune donnée modifiée.")
    print(f"{'='*64}")
    return 0


if __name__ == "__main__":
    run()
