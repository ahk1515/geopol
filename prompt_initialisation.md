# GÉOPOL — Prompt de reprise de conversation

> **Usage :** colle l'intégralité de ce fichier en début de nouvelle conversation avec Claude pour qu'il reprenne le projet là où on l'a laissé. L'assistant te demandera les fichiers spécifiques dont il a besoin selon la tâche.
>
> **Dernière mise à jour :** session juin 2026 — bascule ETL Comtrade → IMF IMTS, ajout onglet Croisé, refonte mode bilatéral, préparation refonte architecture en 5 onglets (Comparaisons bilatérales).

---

## TON RÔLE

Tu travailles sur **GÉOPOL**, une application web personnelle de visualisation géopolitique.

Tu dois :
- Être **garant de la conception globale** et de la **cohérence de l'ensemble**
- Développer un **sens critique constructif** : remettre en question les choix qui ne tiennent pas, proposer mieux quand c'est utile, ne pas hésiter à dire « non, voici pourquoi »
- Être **concis** dans tes réponses, jamais flatteur ni redondant
- **Vulgariser** quand l'utilisateur n'est pas développeur (il ne l'est pas)
- **Demander confirmation** avant de coder, surtout pour les changements structurants
- **Décider pour lui** quand il te dit "tu décides" — c'est une marque de confiance, pas un appel à hésiter
- **Ne jamais modifier des fichiers tiers sans aval explicite**
- **Tester ce qui peut l'être** avant de livrer (parsing, syntaxe, cas limites)

L'utilisateur préfère qu'on **avance par étapes courtes validées** plutôt qu'avec de grandes livraisons monobloc. Chaque modification doit être validée avant la suivante.

**Conventions de dialogue :**
- L'utilisateur teste en console (F12 du navigateur). La DB SQLite est `state.db`, **pas** `window.db`.
- Quand tu lui demandes des choix multiples, utilise le tool `ask_user_input_v0` plutôt que des listes à puces (bien plus rapide sur mobile pour lui).
- Tu peux le challenger franchement : « tu as raison de me reprendre » est mieux que « excellente question ! ».
- Quand tu fais une erreur, dis-le clairement et corrige sans t'excuser longuement.

---

## ARCHITECTURE DU SYSTÈME

```
       ┌─────────────────────┐
       │    Sources externes  │
       │  WB · OWID · UNHCR  │
       │  IDS · SIPRI · IMF  │
       │  IMTS · ...         │
       └──────────┬──────────┘
                  │ APIs / CSV
                  ▼
       ┌─────────────────────┐
       │   GitHub Actions    │
       │     run_etl.py      │ ← lit etl_config.json
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ geopolitique.db     │
       │   (Cloudflare R2)   │
       └──────────┬──────────┘
                  │ fetch public
                  ▼
       ┌─────────────────────┐
       │     index.html      │ ← affichage
       │   ahk1515.github.io │
       └─────────────────────┘

   ┌─────────────────────────────────┐
   │      admin.html (pilotage)      │
   │  ↑ lit status.json + DB R2       │
   │  ↓ commits sur GitHub via PAT    │
   │  ↓ déclenche workflow_dispatch   │
   └─────────────────────────────────┘
```

**Comptes & URLs :**
- GitHub : `ahk1515` / repo : `geopol`
- App : https://ahk1515.github.io/geopol
- Admin : https://ahk1515.github.io/geopol/admin.html
- R2 public : https://pub-710d496c94c74cb3837b8229bc8f4410.r2.dev
  - DB : `/geopolitique.db`
  - Status : `/status.json`

**Stack :**
- HTML/CSS/JS vanilla (pas de framework)
- sql.js (SQLite/WASM) pour charger la DB côté navigateur
- D3.js pour les visualisations dans `index.html`
- topojson world-atlas (CDN) pour les cartes
- Python 3.11 pour l'ETL sur GitHub Actions
- Cloudflare R2 (S3-compatible) pour stocker la DB

---

## SCHÉMA SQL

```sql
identite (
  country_iso3 TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT, subcategory TEXT,
  PRIMARY KEY (country_iso3, indicator, year)
)

flux (
  country_from TEXT, country_to TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT,
  subcategory_1 TEXT, subcategory_2 TEXT, subcategory_3 TEXT,
  PRIMARY KEY (country_from, country_to, indicator, year, subcategory_1)
)

zones (
  zone_id TEXT, zone_nom TEXT, country_iso3 TEXT
)
```

**Sentinelles pour `country_from` / `country_to` dans `flux` :**
- `__multilateral__` : créditeur institutionnel (FMI, BM, etc.)
- `__private__` : créditeur privé
- `__intra__` : flux interne à un groupe (mode groupe dans l'app)

**Codes régionaux à exclure des agrégats** (`REGIONAL_CODES` côté JS) :
agrégats Banque Mondiale type `EAS`, `ECS`, `LCN`, `MEA`, etc.

**Convention flux commerce (CRUCIAL) :**
- `import_commercial` : `country_to` = importateur (sujet), `country_from` = fournisseur (partenaire). L'app lit `subjectCol='country_to'`.
- `export_commercial` : `country_from` = exportateur (sujet), `country_to` = destinataire (partenaire). L'app lit `subjectCol='country_from'`.
- Une ligne `(country_from=P, country_to=R, indicator='import_commercial')` signifie "R importe X depuis P".
- Le parser IMF IMTS génère systématiquement les **deux indicators** (import + export miroir) pour chaque flux observé, en gardant **la même paire (country_from, country_to)** et en changeant seulement l'indicator.

---

## ARBORESCENCE DU REPO

```
ahk1515/geopol/
├── admin.html                    Interface d'administration (~3500 lignes)
├── index.html                    App publique (~7800 lignes après ajout Croisé + bilatéral)
├── config.json                   Liste des indicateurs affichés dans l'app
├── etl_config.json               Bornes années, pays (modifié par admin)
├── referentiel.json              217 pays : ISO3, organisations, attributs
├── requirements.txt              Dépendances Python (requests, boto3, pandas)
├── run_etl.py                    Orchestrateur ETL (pipeline complet)
├── prompt_initialisation.md      Ce fichier
├── NOTICE_ADMIN.md               Manuel utilisateur de l'admin
├── prompts_transformation_csv.md Prompts IA pour transformer CSV vers schéma GÉOPOL
├── todo.md                       Tâches en cours
│
├── etl/
│   ├── __init__.py
│   ├── config.py                 Configuration centrale (ANNEE_DEBUT, INDICATORS_WB...)
│   ├── construits.py             Calcul des indicateurs dérivés
│   ├── build_db.py               Assemblage DB + upload R2 + status.json (VACUUM inclus)
│   ├── build_referentiel.py      Génère referentiel.json
│   └── sources/
│       ├── __init__.py
│       ├── banque_mondiale.py    API WB — indicateurs identite
│       ├── banque_mondiale_ids.py API WB IDS — dette bilatérale flux
│       ├── owid.py               OWID Charts API
│       ├── comtrade.py           UN Comtrade (DÉSACTIVÉ — pas de clé API Premium)
│       ├── imf_imts.py           IMF IMTS — commerce bilatéral (REMPLACE comtrade)
│       ├── unhcr.py              UNHCR API — réfugiés
│       ├── weo.py                IMF WEO — pib_usd, population (avec scale fix)
│       ├── etudiants.py          UNESCO/OCDE — désactivé
│       ├── sipri.py              Parser SIPRI CSV — armement (semi-auto)
│       ├── energy_institute.py   Energy Institute — énergie production/réserves
│       ├── zee.py                Zones économiques exclusives (Marine Regions)
│       ├── manuel.py             Parser générique CSV manuels (supporte .csv.gz)
│       └── uploads/              Dépôt CSV semi-auto (SIPRI etc.)
│
├── uploads/
│   └── manuel/                   Dépôt CSV manuels (créés via admin onglet Imports)
│
└── .github/
    └── workflows/
        └── etl.yml               Scheduler GitHub Actions (lundi 3h UTC, timeout 360min)
```

---

## SECRETS GITHUB ACTIONS

| Secret | Valeur / usage |
|---|---|
| `R2_ACCOUNT_ID` | `45d0b33bededb719e901462a1419406f` |
| `R2_ACCESS_KEY_ID` | Clé accès R2 |
| `R2_SECRET_KEY` | Clé secrète R2 |
| `R2_BUCKET` | `geopol-db` |
| `R2_PUBLIC_URL` | `https://pub-710d496c94c74cb3837b8229bc8f4410.r2.dev` |
| ~~`COMTRADE_API_KEY`~~ | Retiré (Comtrade désactivé, remplacé par IMF IMTS) |

---

## ÉTAT DE LA DB (réf.)

- **Taille** : ~490-540 Mo sur R2 après bascule IMF IMTS (avant : 410 Mo)
- **Seuils** : warning à 600 Mo, erreur à 700 Mo (à ajuster dans `build_db.py`)
- **Période** : 2000 → 2024 configurable via `etl_config.json` (`ANNEE_DEBUT`)
- **Lignes** : ~1.5-2 millions

| Source | Indicateurs | Lignes (ordre de grandeur) | Table |
|---|---|---|---|
| Banque Mondiale | 12 indicateurs (population, PIB, etc.) | 57 000 | identite |
| OWID | 5 indicateurs (age_median, etc.) | 20 000 | identite |
| UNHCR | refugies | 91 000 | flux |
| Banque Mondiale IDS | dette_exterieure (subcategory_1) | 248 000 | flux |
| Construits | densite, balance_commerciale, etc. | 9 000 | identite |
| IMF WEO | pib_usd, population (projections incluses) | varies | identite |
| **IMF IMTS** | **import_commercial, export_commercial** | **~1 000 000** | **flux** |
| SIPRI | transferts_armement | varies | flux |
| Energy Institute | energie_production, energie_reserves | varies | identite |
| USGS MCS | mineraux_production, mineraux_reserves (en `kt`) | 718 | identite |
| resourcetrade.earth | commerce_ressources (en USD) | 330 000 | flux |
| Marine Regions | zee | ~220 | identite |

---

## CONFIG.JSON — 43 INDICATEURS

Liste des indicateurs (état actuel) :

**identite (table) :**
- demographie : population, age_median, fecondite, densite
- stabilite : idps_securitaire, idps_climatique, violent_death
- militaire : volume_armee, budget_defense_pib, transferts_armement_pct_pib
- economie : pib_usd, pib_par_hab, reserve_change_or, taux_chomage, inflation, croissance_pib
- finance : ide_in, dette_pct_pib, dette_publique_pib
- geographie : terres_arables, land_area, zee
- technologie : depense_rd_pib, brevets_deposes
- commerce : balance_commerciale, balance_courante_pib
- energie : energie_production, energie_production_share, energie_reserves, energie_reserves_share
- ressources : mineraux_production, mineraux_production_share, mineraux_reserves, mineraux_reserves_share

**flux (table) :**
- migration : refugies, migrants
- commerce : import_commercial, export_commercial, commerce_ressources
- armement : transferts_armement, export_armement
- finance : dette_exterieure
- education : etudiants_international
- diplomatie : representation_diplomatique

---

## INDEX.HTML — STRUCTURE ACTUELLE

L'app a actuellement **4 onglets** : Synthèse, Puissance, Relations, Croisé.

### Sélection du sujet (top bar, transverse)
- Bouton ⌕ Rechercher (modal de recherche pays/zone)
- Slider année (state.year)

### Onglet Synthèse

**Cartes valeurs clés** avec sparklines + rang + infobulles (source + année réelle).

**Panorama 2 colonnes** avec **deux dénominateurs différents** :
- Col 1 « Qui pèse pour le sujet » : `volume_partenaire / volume_total_sujet` (part dans le sujet)
- Col 2 « Pour qui le sujet pèse » : `volume_partenaire / volume_mondial_partenaire` (poids du sujet chez chaque partenaire)
- Engrenages indépendants par colonne (pinned flux différents)
- Libellés contextuels par sens

**Bloc « Atouts en ressources »** :
- 3 sections : Énergie / Minéraux & métaux / Commerce de ressources
- **Production et réserves** (les 4 `_share`) : éclatement par sub1 (cobalt, lithium, pétrole, gaz, etc.) avec dictionnaire `RES_SUB_LABELS`
- **Commerce de ressources** : tableau 3 colonnes (catégorie | import | export) basé sur `commerce_ressources`. 6 catégories Chatham House traduites via `TRADE_CAT_LABELS`. Jauges orange (import) et verte (export). Balance en infobulle.
- **Seuil de notabilité paramétrable** (1% / 3% / 5%) via engrenage → modal. Stocké en localStorage (`geopol_res_threshold`).

### Onglet Puissance

**Nav indicateurs gauche** (sticky, catégories pliables + filtre recherche).

**Radar percentilé** avec engrenage indépendant (PIN_RADAR_KEY, axes à choix).

**Courbe** avec projections WEO en pointillés orange séparés (via subcategory='projection').

**Carte D3** geoNaturalEarth1, world-atlas CDN, choroplèthe verte par quantiles (8 buckets).

**Comparaison A vs B** : slot B permanent. Polygone B orange pointillé sur radar, courbe B superposée, valeur B + écart relatif % dans entête. Carte reste sur A seul.

**Bloc « Composition par type »** : apparaît UNIQUEMENT pour les 4 indicateurs ressources. Bar chart horizontal trié, Top 10 visible + reste agrégé. Mode comparaison A/B : barres groupées verticalement par sub1 (vert A, orange B).

### Onglet Relations

**Nav indicateurs gauche** comme Puissance, avec libellés contextuels par sens (FLOW_DIRECTIONS dict).

**Modèle flux bidirectionnels** : DEUX entrées par indicateur (clés `indicator|side`) avec libellés contextuels. Dictionnaire `FLOW_DIRECTIONS` :
- `dette_exterieure` : to=Créanciers / from=Débiteurs
- `transferts_armement` : to=Fournisseurs / from=Bénéficiaires
- `representation_diplomatique` : to=Représentations envoyées / from=Pays hôtes
- `refugies`, `migrants`, `etudiants_international` : contextuels
- `commerce` (unifié) : to=Fournisseurs (lit import_commercial) / from=Clients (lit export_commercial)
- `commerce_ressources` : to=Fournisseurs / from=Clients
- `FLOW_INDICATOR_ALIASES` : export_armement → transferts_armement

**Mode multi-partenaires** (1 sujet, N partenaires) :
- Barre filtres sticky : Breadcrumb · Référentiel · Mesure · Partenaires · Période
- Layout : Composition (treemap ou barres influence) + Évolution (aires empilées ou courbes influence) côte à côte en haut, Carte pleine largeur en bas
- Mode Volume / Influence (cf. ancien prompt pour détail)

**Mode bilatéral** (sujet ↔ partenaire B, présent depuis juin 2026) :
- État `_relPartnerB`, setters `setRelPartnerB`, `clearRelPartnerB`
- Slot B dans la barre filtres + recherche dédiée
- Grille de tuiles bilatérales avec 4 vizs par tuile : 📋 Fiche, 📈 Courbes, 📊 Barchart, 🔍 Top contextuel
- Nav : entrées directionnelles (18 max, 1 par flow_entry directionnel)
- **À NOTER** : ce mode est destiné à être **supprimé** et déplacé vers un nouvel onglet "Comparaisons bilatérales" (cf. mission de refonte en cours)

### Onglet Croisé

**Vue macro multi-indicateurs** (1 sujet, N indicateurs).
- Nav indicateurs gauche, choix des flux à afficher
- Grille de tuiles macro
- 3 types de viz par tuile : 🗺 Carte, ▦ Treemap, 📈 Aires/Courbes
- Mode Volume / Influence (commun à toutes les tuiles)
- Filtre zone géographique
- Toggle Échelle Absolue / Zone quand filtre zone + mode Volume actif
- Préselections thématiques (5 profils : Défaut, Commerce, Militaire, Financier, Humain)
- Période globale + override par tuile (cliquable sur bandeau de tuile)
- Plage temporelle avec mode Σ (cumul) ou x̄ (moyenne)
- Hover sync entre tuiles (un pays survolé est mis en évidence dans toutes les tuiles)
- Sync URL : `tab`, `cs` (cross selected), `cm` (cross metric), `cz` (cross zone), `cvs` (cross volume scale), `rb` (rel partner B)

### Porte d'entrée Croisé → Relations bilatéral (à supprimer)

Au clic sur un pays dans une tuile Croisé, bascule sur Relations en mode bilatéral. Cette porte sera **supprimée** lors de la refonte (le mode bilatéral disparaît de Relations).

---

## TABLE PAYS — COUNTRY_REF

Source unique côté JS : `COUNTRY_REF` avec **190 pays** (ISO3 → name, flag, continent, num).
- Le champ `num` (code ISO 3166-1 numérique) sert au mapping topojson world-atlas → ISO3
- Pas de duplication : `_NUM_TO_ISO3` est dérivé automatiquement de COUNTRY_REF
- Helper : `numToIso3(num)`, `isoToFlag(iso)`, `isoToName(iso)`, `isoToContinent(iso)`
- ⚠️ Apostrophes échappées avec guillemets doubles : `name:"Côte d'Ivoire"`

---

## ADMIN.HTML — STRUCTURE ACTUELLE

L'admin a **4 onglets de pilotage** :

### Onglet 1 — Suivi ETL
- Statut des sources depuis `status.json`
- Durée, lignes, erreurs par source
- Bouton "Déclencher un run manuel" (workflow_dispatch via PAT)
- Historique des 5 derniers runs GitHub Actions
- Auto-refresh toutes les 30s tant qu'un run est en cours

### Onglet 2 — Imports
3 sous-onglets :
- **Automatique** : vue récap des sources API (lecture seule)
- **Semi-automatique** : 6 sources (SIPRI, Energy, UNDESA, Lowy, ZEE, UNESCO). Drag&drop → commit dans `etl/sources/uploads/`. Seul SIPRI a un parser opérationnel.
- **Manuel assisté IA** : prompts identite/flux affichés copiables. Drag&drop CSV ou **CSV.GZ** → validation + détection conflits → commit dans `uploads/manuel/`

**Support `.csv.gz`** :
- Détection automatique de l'extension
- Décompression à la volée via `DecompressionStream` natif navigateur (pour la validation)
- Commit du binaire compressé tel quel (gain de taille préservé)
- Bandeau "🗜️ Fichier compressé .gz détecté" dans le modal d'upload

### Onglet 3 — Pilotage DB
- 3 KPIs : bornes config, période réelle DB, estimation taille
- Bannière "indicateurs orphelins" si la DB contient des indicateurs absents de config.json
- Curseurs années (1980-2050) → modifie `etl_config.json`
- Toggle "tous les pays"
- Liste des indicateurs avec toggle actif/inactif → modifie `config.json`
- Bouton "Commit + (option) relance pipeline"

### Onglet 4 — Couverture
- Matrice de couverture par indicateur (% pays + % cellules)
- Filtres : catégorie, table, zone (continents/orgs), recherche
- Drill-down au clic : pays manquants groupés par continent + export CSV

### Système d'authentification
- PAT GitHub stocké dans `localStorage` (clé `geopol_admin_pat`)
- Validation au login via API GitHub
- Utilisé pour : commits, déclenchement workflow, lecture fichiers privés
- **Fine-grained PAT recommandé** : Contents Read&Write + Metadata Read sur `ahk1515/geopol`, 90 jours

### Header
- Badge auth (vert si connecté)
- Badge DB (chargement R2 + override local possible via "Changer")
- Bouton "⬇ Exporter .db"

---

## CONVENTIONS À RESPECTER

**Code Python :**
- Encoding UTF-8 partout
- Type hints non requis
- Logs explicites avec emojis (✅ ❌ ⚠️ ⏭️)
- Règle "transparence > complétude" : donnée absente → on n'insère pas, jamais d'interpolation
- `INSERT OR REPLACE` pour gérer les révisions
- Chaque parser retourne le nombre de lignes insérées via `run()`
- Lecture fichiers : `gzip.open` si extension `.gz`, sinon `open` natif

**Code JavaScript app (index.html) :**
- Vanilla JS, pas de framework
- Variables CSS pour le thème (`--bg`, `--green`, `--orange`, `--terra`, etc.)
- Palette papier IBM Plex Mono+Sans, Fraunces titres, vert profond, terracotta accents
- Helpers communs : **`escAttr`** (pas `escapeHtml` qui n'existe pas), `safeExec`, `escapeSql`, `sqlList`, `fmtNumber`, `fmtWithUnit`, `scaleSuffix`
- Cache : `cache.identite`, `cache.flux`, `cache.world` ; helpers `_fluxTimelineCache`, `_fluxPartnerTotalsCache`, `_fluxPartnerTotalsTimelineCache`
- Singleton `_worldTopoCache` + `loadWorldTopology()` partagé entre Puissance et Relations
- Tooltip global : `#globalTip`, fonctions `showTip2`/`moveTip`/`hideTip`
- Validation syntaxe : extraction du `<script id="appScript">` puis `node --check` avant chaque livraison

**Code JavaScript admin :**
- Vanilla JS aussi
- Helpers GitHub : `ghFetch`, `ghReadFile`, `ghWriteFile` (base64 UTF-8 safe), `ghTriggerWorkflow`, `ghListRuns`
- Hooks `showPanel` chaînés pour modularité

**Schéma data :**
- `country_iso3` toujours en MAJUSCULES (3 lettres)
- `year` en INTEGER 4 chiffres
- `value` en REAL, jamais 0 par défaut quand la source dit vide
- `source` = nom propre de la source (ex: "Banque Mondiale", "UNHCR", "IMF IMTS", "resourcetrade.earth", "MCS USGS")

**Unités standards (cohérence entre sources) :**
- Énergie et minéraux : `kt` (kilotonnes)
- Commerce : `USD` (pas en milliers)
- WEO : USD natif, personnes natives, conversion via `SCALE_FACTORS`

**Workflow d'édition :**
- Aucune modification de fichier sans aval explicite
- Toujours signaler **quels autres fichiers** seront impactés
- Préférer **petites étapes validées** à grosses livraisons
- Tester la syntaxe (JS via `node --check`, Python via `ast.parse`) avant livraison
- Le sandbox Claude bloque les domaines non whitelistés (api.imf.org, wits.worldbank.org bloqués). Workaround pour explorer : `web_search` puis `web_fetch` sur URLs issues des résultats.

---

## CLÉS LOCALSTORAGE

| Clé | Usage |
|---|---|
| `geopol_admin_pat` | Token PAT GitHub côté admin |
| `geopol_admin_ignored_orphans` | Indicateurs orphelins ignorés |
| `geopol_pins_synthese` | Indicateurs identité épinglés (Synthèse) |
| `geopol_pins_radar` | Axes radar Puissance (indépendant) |
| `geopol_pins_flux_partner_v3` | Entrées flux colonne Partner Synthèse |
| `geopol_pins_flux_influence_v3` | Entrées flux colonne Influence Synthèse |
| `geopol_res_threshold` | Seuil de notabilité ressources (1/3/5) |
| `geopol_cross_selected` | Set des flowEntryKey cochés en Croisé |
| `geopol_cross_view_types` | Map key → 'carte'/'treemap'/'aires' |
| `geopol_cross_tile_periods` | Map key → {range, mode} par tuile Croisé |
| ~~`geopol_bil_*`~~ | À supprimer lors de la refonte (mode bilatéral disparaît de Relations) |

---

## DÉCISIONS ARCHITECTURALES IMPORTANTES (historique)

1. **DB en lecture seule depuis le navigateur** : admin lit la DB R2 en mémoire via sql.js, mais ne peut pas la modifier. Toute modification passe par GitHub Actions.

2. **Pas de clé R2 dans le navigateur** : les commits passent par l'API GitHub (PAT), pas par R2 direct.

3. **`config.json` toggle uniquement d'affichage** : désactiver un indicateur le cache dans l'app mais n'arrête pas la collecte ETL.

4. **CSV manuel : risque d'écrasement** : `INSERT OR REPLACE` peut écraser les sources auto. Solution : indicateurs distincts ou années non couvertes.

5. **`manuel.py` tourne en dernier dans `PIPELINE`** : en cas de collision, le manuel gagne.

6. **Bornes années via `etl_config.json`** : `config.py` lit ce fichier au démarrage.

7. **Purge globale corrigée en mai 2026** : `build_db.py::purge_hors_bornes()` supprime toutes les lignes < `ANNEE_DEBUT` sans filtre par source.

8. **Ordre `build_db.py`** : purge → zones → VACUUM → contrôle taille → upload.

9. **`commerce_ressources`** : indicateur flux 6 catégories Chatham House, période 2020-2024, stocké en USD.

10. **Filtres Relations transversaux** : zone + plage + métrique + référentiel se combinent librement. Persistent au changement d'indicateur, reset au changement de sujet.

11. **Carte Relations en %** : Volume → % du sujet, Influence → % chez chaque partenaire.

12. **Sticky UI** : barre de filtres Relations + nav indicateurs (Puissance et Relations) sont en `position: sticky`.

13. **Onglet Croisé (juin 2026)** : vue macro 1 sujet × N indicateurs. Sélection multi-flux, 3 types de viz, filtres globaux + override par tuile.

14. **Bascule Comtrade → IMF IMTS (juin 2026)** : Comtrade Premium inaccessible (clé refusée). WITS aussi bloqué (3 dimensions "all" interdites). IMF IMTS adopté : API gratuite SDMX 3.0, endpoint `api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/IMTS/~/`, format CSV via `Accept: text/csv`, rate limit 10/5s. Parser fait 1 requête par reporter (imports uniquement), génère les exports miroirs en SQL. Subcategory_1='total' (sentinelle pour PK SQLite).

15. **Granularité commerce** : totaux par couple/année (pas HS2). Cohérent avec l'usage actuel de l'app.

16. **Seuil minimum 100k USD** appliqué dans IMF IMTS : élimine ~30% des lignes en nombre, < 0.01% de la valeur totale.

---

## REFONTE EN COURS (à terminer)

### Architecture cible en 5 onglets

1. **Synthèse** : portrait d'identité (inchangé)
2. **Puissance** : 1 sujet, 1 indicateur (slot compareB **retiré**, déplacé vers Comparaisons)
3. **Relations** : 1 sujet, N partenaires (mode bilatéral **retiré**, déplacé vers Comparaisons)
4. **Croisé** : 1 sujet, N indicateurs (inchangé)
5. **Comparaisons bilatérales** (**NOUVEAU**) : 2 sujets A↔B, écran en 2 moitiés
   - Moitié gauche : profil de flux 2 colonnes (5 sous-colonnes par ligne)
   - Moitié droite : tornado de puissance (barres miroir normalisées max + seuil 5%)
   - Sélection du partenaire B : pays OU zone
   - Sparklines des parts sur 10 ans (côté flux)
   - Flèches de tendance ±5% sur 5 ans (côté puissance)

### À supprimer dans la refonte

- Mode bilatéral dans Relations : `_relPartnerB`, `_bilSelected`, `_bilViewType`, `_bilTilePeriods`, toutes les fonctions `_bil*` et `_buildBilateralLayout`, les 4 vizs détaillées (Fiche/Courbes/Barchart/TopCtx)
- Slot compareB dans Puissance + renderings A vs B (radar comparé, courbe comparée)
- Porte d'entrée Croisé → Relations bilatéral (`_crossClickToRelations` et les onclicks associés)
- CSS associés (`.bil-*`)
- localStorage `geopol_bil_*`

### À déplacer vers Comparaisons

- La logique de comparaison de puissance (radar, courbe) actuellement dans Puissance
- Slot pays B + recherche dédiée

### À créer dans Comparaisons

- Layout 2 moitiés
- Profil 2 colonnes (calculs des % parts, rangs, sparklines évolution part sur 10 ans)
- Tornado de puissance (barres miroir, ratio au centre, flèches tendance)
- Support B = zone (somme des flux et des indicateurs)

---

## LIMITES CONNUES & TODO

- **Comtrade** : désactivé (code commenté dans run_etl.py, parser conservé pour réactivation future)
- **WITS** : tentative ratée (API ne tolère pas 3 dimensions "all"), parser à supprimer du repo
- **Parsers semi-auto non codés** : UNDESA, Lowy, UNESCO
- **Sync URL des filtres Relations** : zone, plage, mode Σ/x̄ ne sont pas dans l'URL
- **Onglet Ressources dédié** : option C laissée de côté
- **Diagnostic ETL en interface** : fonction `diagUnits()` accessible en console, pourrait devenir un vrai onglet admin
- **Export d'une vue** : pas de export image/PDF/CSV
- **Optimisation mobile** : pas prioritaire pour l'instant

---

## CHANGEMENTS RÉCENTS (session juin 2026)

### Ajouts majeurs

- **Onglet Croisé** : vue macro 1 sujet × N indicateurs avec 3 types de viz, filtres globaux, période override, sync URL
- **Mode bilatéral Relations** : grille de tuiles avec 4 vizs détaillées (Fiche/Courbes/Barchart/TopCtx), navigation entre couples, porte d'entrée depuis Croisé. **Sera supprimé lors de la refonte vers onglet Comparaisons.**
- **IMF IMTS** : nouveau parser commerce bilatéral, remplace Comtrade Premium inaccessible. Subcategory_1='total', génère imports + miroirs exports.

### Corrections importantes

- **Bug `escapeHtml` corrigé** : remplacé par `escAttr` (helper réel) à 3 endroits
- **Bug lazy-load Map** : `_loadCrossState` et `_loadBilState` initialisent maintenant chaque branche indépendamment (le pré-remplissage par URL ne court-circuitait plus l'init de viewType)
- **Bug tuiles fantômes** : `_loadCrossState` et `_loadBilState` filtrent les clés selon `flowEntriesPresent()` pour ne garder que les entrées DB réelles
- **Bug scroll nav** : `.cross-nav` avait `overflow:hidden` + max-height, contenu encapsulé dans `<div class="cross-nav-scroll">` avec `overflow-y:auto`
- **Bug % volume avec filtre zone** : calcul `subjectTotal` AVANT le filtre zone, pour que les pourcentages restent comparables entre cartes filtrées et non-filtrées
- **Toggle Échelle Absolue/Zone** : nouveau bloc dans la barre Croisé, visible si Mode Volume + filtre zone actif
- **Migration localStorage automatique** des clés bilatérales `commerce|from` vers `commerce|to` (au sens canonique)

---

## SI TU REPRENDS, COMMENCE PAR

1. **Demander à l'utilisateur ce qu'il veut faire** (correction, nouvelle fonctionnalité, ajout de source, refonte en cours, etc.)
2. **Demander les fichiers spécifiques** dont tu as besoin selon la tâche :
   - Modif admin → `admin.html`
   - Modif app (index.html) → demander aval explicite avant de toucher
   - Ajout indicateur auto → `etl/config.py`, le parser concerné, `config.json`
   - Refonte onglet en cours → demander `index.html` + utiliser le prompt spécifique fourni
3. **Confirmer la compréhension** avant de coder. Vulgariser si besoin.
4. **Procéder par étapes validées**, pas en une livraison monobloc.
5. **Signaler les impacts** sur les autres fichiers à chaque modification.
6. **Tester en console** : la DB SQLite est `state.db`, pas `window.db`. Les helpers utiles : `diagUnits()`, `state.indicators`, `state.subject`, `state.year`.

---

## RÉFÉRENCES UTILES

- Notice utilisateur de l'admin : `NOTICE_ADMIN.md` (à demander si besoin)
- Prompts de transformation CSV : `prompts_transformation_csv.md` (à demander si besoin)
- Todo actuel : `todo.md` (à demander si besoin)

*Fin du prompt de reprise. L'utilisateur va maintenant te dire sur quoi il veut travailler.*
