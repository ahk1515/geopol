# GÉOPOL — Prompt d'initialisation

Colle ce prompt en début de nouvelle conversation pour initialiser le contexte.

---

## CONTEXTE DU PROJET

Tu travailles sur **GÉOPOL**, une application web de visualisation géopolitique.
Tu es garant de la conception globale, de la cohérence de l'ensemble, et tu dois
développer un sens critique. Tu es concis dans tes réponses.

**Règle absolue : aucune modification de `index.html` sans aval explicite.**

---

## ARCHITECTURE GLOBALE

```
App web (GitHub Pages)
  ahk1515.github.io/geopol
        ↓ fetch DB
Stockage DB (Cloudflare R2)
  pub-710d496c94c74cb3837b8229bc8f4410.r2.dev/geopolitique.db
        ↑ upload
Pipeline ETL (GitHub Actions)
  Tourne automatiquement tous les lundis à 3h UTC
  Déclenchable manuellement depuis GitHub Actions
```

**Comptes :**
- GitHub : `ahk1515` / repo : `geopol`
- Cloudflare R2 : bucket `geopol-db`

---

## STACK TECHNIQUE

- `index.html` : app web autonome HTML/CSS/JS (~4600 lignes)
- sql.js (SQLite/WASM) : charge `geopolitique.db` via fetch depuis R2
- D3.js : visualisations
- Python 3.11 : scripts ETL sur GitHub Actions
- SQLite : base de données

---

## SCHÉMA SQL

```sql
Table identite :
  country_iso3 TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT, subcategory TEXT
  PRIMARY KEY (country_iso3, indicator, year)

Table flux :
  country_from TEXT, country_to TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT,
  subcategory_1 TEXT, subcategory_2 TEXT, subcategory_3 TEXT
  PRIMARY KEY (country_from, country_to, indicator, year, subcategory_1)
```

**Sentinelles flux :**
- `__multilateral__` : créditeur institutionnel (FMI, Banque Mondiale...)
- `__private__` : créditeur privé
- `__intra__` : flux interne au groupe (mode groupe)

---

## ÉTAT DE LA DB (dernière mise à jour)

- **Taille : ~123 Mo** (sur R2)
- **426 108 lignes** au total
- Période : 2000 → 2024 (configurable)

| Source | Indicateurs | Lignes | Table |
|---|---|---|---|
| Banque Mondiale | population, pib_usd, pib_par_hab, fecondite, reserve_change_or, ide_in, terres_arables, land_area, budget_defense_pib, depense_rd_pib, brevets_deposes | 57 165 | identite |
| OWID | age_median, volume_armee, violent_death, idps_securitaire, idps_climatique | 20 253 | identite |
| UNHCR | refugies | 91 150 | flux |
| Banque Mondiale IDS | dette_exterieure (bilaterale, multilaterale, obligations_privees, crediteurs_prives) | 248 255 | flux |
| Construits | densite, balance_commerciale, export_pct_pib, import_pct_pib, dette_pct_pib | 9 285 | identite |

---

## FICHIERS DU REPO GITHUB

```
geopol/
├── index.html                    App web principale (NE PAS MODIFIER sans aval)
├── config.json                   Liste des indicateurs affichés dans l'app
├── referentiel.json              Référentiel pays : ISO3, organisations, attributs, noms sources
├── requirements.txt              Dépendances Python pour GitHub Actions
├── run_etl.py                    Orchestrateur ETL — point d'entrée principal
├── todo.md                       Liste des tâches en cours
├── prompts_transformation_csv.md Prompts IA pour transformer CSV vers schéma GÉOPOL
├── etl/
│   ├── __init__.py
│   ├── config.py                 Configuration centrale ETL (années, pays, indicateurs)
│   ├── construits.py             Calcul des indicateurs dérivés (densité, balance...)
│   ├── build_db.py               Assemblage final DB + upload R2 + status.json
│   ├── build_referentiel.py      Génère referentiel.json depuis Excel + données organisations
│   └── sources/
│       ├── __init__.py
│       ├── banque_mondiale.py    API WB — indicateurs identite
│       ├── banque_mondiale_ids.py API WB IDS — dette bilatérale flux
│       ├── owid.py               OWID Charts API — indicateurs identite
│       ├── comtrade.py           UN Comtrade — commerce bilatéral (clé manquante)
│       ├── unhcr.py              UNHCR API — réfugiés flux
│       ├── etudiants.py          UNESCO/OCDE — désactivé en attente OPRI.zip
│       └── sipri.py              Parser SIPRI CSV — armement flux (semi-manuel)
└── .github/
    └── workflows/
        └── etl.yml               Scheduler GitHub Actions (lundi 3h UTC)
```

---

## SECRETS GITHUB ACTIONS

| Secret | Usage |
|---|---|
| `R2_ACCOUNT_ID` | `45d0b33bededb719e901462a1419406f` |
| `R2_ACCESS_KEY_ID` | Clé accès R2 |
| `R2_SECRET_KEY` | Clé secrète R2 |
| `R2_BUCKET` | `geopol-db` |
| `R2_PUBLIC_URL` | `https://pub-710d496c94c74cb3837b8229bc8f4410.r2.dev` |
| `COMTRADE_API_KEY` | Clé UN Comtrade (manquante — à créer sur comtradeplus.un.org) |

---

## TROIS TYPES D'IMPORT (architecture admin)

| Type | Mécanisme | Sources |
|---|---|---|
| **Automatique** | API + script Python + GitHub Actions | WB, OWID, UNHCR, IDS, Comtrade |
| **Semi-automatique** | Dépôt CSV dans admin → R2 → parser Python | SIPRI, Energy Institute, UNDESA, Lowy |
| **Manuel assisté IA** | Prompt IA → CSV formaté → import admin | Données universitaires, alignement ONU... |

---

## RÉFÉRENTIEL PAYS (`referentiel.json`)

- **217 pays** couverts
- **149 Ko**
- Structure par ISO3 :
  - `iso2`, `nom`, `continent`, `region`
  - `organisations` : dict {nom_org: statut} (membre/observateur/candidat/associé/allié/signataire/ratifié/suspendu)
  - `attributs` : membre_permanent_cs_onu, puissance_nucleaire_declaree, puissance_nucleaire
  - `noms_sources` : correspondances noms pour SIPRI, UNHCR, UNDESA, dette

**Organisations couvertes :**
Alliances militaires (OTAN, OTSC, OCS, ANZUS, Five Eyes, QUAD, AUKUS),
Politiques globales (G7, G20, Commonwealth, Francophonie, CELAC),
Européennes (UE, CEI, Conseil Europe),
Africaines (UA, CEDEAO, CEEAC, IGAD, SADC, EAC, COI, UMA, CEN-SAD, COMESA),
Américaines (OEA, MERCOSUR, ALBA, CARICOM, ACEUM),
Asie-Pacifique (ASEAN, APEC, SAARC, PIF, RCEP, BRICS),
Ligue Arabe,
Économiques (OCDE, OMC, AIIB, GAFI, BRI, IEA),
Énergie (OPEP, OPEP+, GECF),
Traités (TNP, CWC, ATT, CPI, Paris, CNUDM)

---

## ADMIN.HTML — CONCEPTION (non encore développé)

4 onglets prévus :
1. **Suivi ETL** : statut sources, logs, déclenchement manuel
2. **Imports** : automatique / semi-automatique / manuel assisté IA
3. **Pilotage DB** : curseurs antériorité, nettoyage, taille, redéploiement R2
4. **Couverture** : matrice indicateur × pays × années, identification des trous

---

## SOURCES RESTANTES À INTÉGRER

| Source | Type | Statut |
|---|---|---|
| Comtrade | Automatique | Clé API manquante |
| SIPRI | Semi-auto | Parser prêt, en attente admin |
| Energy Institute | Semi-auto | Parser à coder |
| UNDESA migrants | Semi-auto | Parser à coder |
| Lowy (représentations) | Semi-auto | Parser à coder |
| ZEE Flanders Marine | Semi-auto | Parser à coder |
| UNESCO étudiants (OPRI.zip) | Semi-auto | À inspecter |
| Données universitaires | Manuel IA | Template prêt |

---

## RÈGLES DE CONCEPTION

1. `index.html` = référence intouchable sans aval explicite
2. Donnée absente → vide, jamais interpolée
3. Donnée révisée par la source → on écrase
4. Indicateur construit incomplet → vide
5. DB < 500 Mo (seuil de réévaluation architecture)
6. `country_from`/`country_to` = ISO3 ou sentinelle (`__multilateral__`, `__private__`, `__intra__`)
7. Les sources manuelles passent par admin → R2 → GitHub Actions
8. `config.json` = source de vérité des indicateurs affichés dans l'app

---

## PROCHAINES TÂCHES PRIORITAIRES

1. Intégrer `referentiel.json` dans `index.html` (mode groupe prédéfini)
2. Développer `admin.html`
3. Obtenir clé Comtrade
4. Coder parsers semi-automatiques restants
5. Mettre à jour notice PDF
