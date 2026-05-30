# GÉOPOL — Prompt de reprise de conversation

> **Usage :** colle l'intégralité de ce fichier en début de nouvelle conversation avec Claude pour qu'il reprenne le projet là où on l'a laissé. L'assistant te demandera les fichiers spécifiques dont il a besoin selon la tâche.
>
> **Dernière mise à jour :** session mai 2026 — ajout `commerce_ressources`, refonte UI complète (Synthèse/Puissance/Relations), filtres zone + plage temporelle, support .csv.gz, purge globale ETL.

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

L'utilisateur préfère qu'on **avance par étapes courtes validées** plutôt qu'avec de grandes livraisons monobloc. Chaque modification doit être validée avant la suivante.

**Conventions de dialogue :**
- L'utilisateur teste en console (F12 du navigateur). La DB SQLite est `state.db`, **pas** `window.db`.
- Quand tu lui demandes des choix multiples, utilise le tool `ask_user_input_v0` plutôt que des listes à puces (bien plus rapide sur mobile pour lui).
- Tu peux le challenger franchement : « tu as raison de me reprendre » est mieux que « excellente question ! ».

---

## ARCHITECTURE DU SYSTÈME

```
       ┌─────────────────────┐
       │    Sources externes  │
       │  WB · OWID · UNHCR  │
       │  IDS · SIPRI · ...   │
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

---

## ARBORESCENCE DU REPO

```
ahk1515/geopol/
├── admin.html                    Interface d'administration (~3500 lignes)
├── index.html                    App publique (geopol_v2.html, ~4800 lignes)
├── config.json                   Liste des 43 indicateurs affichés dans l'app
├── etl_config.json               Bornes années, pays (modifié par admin)
├── referentiel.json              217 pays : ISO3, organisations, attributs
├── requirements.txt              Dépendances Python (requests, boto3)
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
│   ├── build_db.py               Assemblage DB + upload R2 + status.json
│   ├── build_referentiel.py      Génère referentiel.json
│   └── sources/
│       ├── __init__.py
│       ├── banque_mondiale.py    API WB — indicateurs identite
│       ├── banque_mondiale_ids.py API WB IDS — dette bilatérale flux
│       ├── owid.py               OWID Charts API
│       ├── comtrade.py           UN Comtrade (clé API manquante)
│       ├── unhcr.py              UNHCR API — réfugiés
│       ├── weo.py                IMF WEO — pib_usd, population (avec scale fix)
│       ├── etudiants.py          UNESCO/OCDE — désactivé
│       ├── sipri.py              Parser SIPRI CSV — armement (semi-auto)
│       ├── energy_institute.py   Energy Institute — énergie production/réserves
│       ├── manuel.py             Parser générique CSV manuels (supporte .csv.gz)
│       └── uploads/              Dépôt CSV semi-auto (SIPRI etc.)
│
├── uploads/
│   └── manuel/                   Dépôt CSV manuels (créés via admin onglet Imports)
│
└── .github/
    └── workflows/
        └── etl.yml               Scheduler GitHub Actions (lundi 3h UTC)
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
| `COMTRADE_API_KEY` | Clé UN Comtrade (manquante actuellement) |

---

## ÉTAT DE LA DB (réf.)

- **Taille** : ~410 Mo sur R2 après purge globale
- **Seuils** : warning à 450 Mo, erreur à 480 Mo (dans `build_db.py`)
- **Période** : 2000 → 2024 configurable via `etl_config.json` (`ANNEE_DEBUT`)
- **Lignes** : ~950 000 + 330 000 commerce_ressources

| Source | Indicateurs | Lignes | Table |
|---|---|---|---|
| Banque Mondiale | 12 indicateurs (population, PIB, etc.) | 57 165 | identite |
| OWID | 5 indicateurs (age_median, etc.) | 20 253 | identite |
| UNHCR | refugies | 91 150 | flux |
| Banque Mondiale IDS | dette_exterieure (subcategory_1) | 248 255 | flux |
| Construits | densite, balance_commerciale, etc. | 9 285 | identite |
| IMF WEO | pib_usd, population (projections incluses) | varies | identite |
| SIPRI | transferts_armement | varies | flux |
| Energy Institute | energie_production, energie_reserves | varies | identite |
| USGS MCS | mineraux_production, mineraux_reserves (en `kt`) | 718 | identite |
| resourcetrade.earth | commerce_ressources (en USD) | 330 856 | flux |

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
- commerce : import_commercial, **commerce_ressources**
- armement : transferts_armement, export_armement
- finance : dette_exterieure
- education : etudiants_international
- diplomatie : representation_diplomatique

---

## INDEX.HTML — STRUCTURE ACTUELLE

L'app a **3 onglets principaux** : Synthèse, Puissance, Relations.

### Sélection du sujet (top bar, transverse)
- Bouton ⌕ Rechercher (modal de recherche pays/zone)
- Slider année (state.year)
- Sélecteur compareB pour Puissance

### Onglet Synthèse

**Cartes valeurs clés** avec sparklines + rang + infobulles (source + année réelle).

**Panorama 2 colonnes** avec **deux dénominateurs différents** :
- Col 1 « Qui pèse pour le sujet » : `volume_partenaire / volume_total_sujet` (part dans le sujet)
- Col 2 « Pour qui le sujet pèse » : `volume_partenaire / volume_mondial_partenaire` (poids du sujet chez chaque partenaire)
- Engrenages indépendants par colonne (pinned flux différents)
- Libellés contextuels par sens

**Bloc « Atouts en ressources »** :
- 3 sections : Énergie / Minéraux & métaux / Commerce de ressources
- **Production et réserves** (les 4 `_share`) : éclatement par sub1 (cobalt, lithium, pétrole, gaz, etc.) avec dictionnaire `RES_SUB_LABELS` (Pgm → Platinoïdes, etc.)
- **Commerce de ressources** : tableau 3 colonnes (catégorie | import | export) basé sur `commerce_ressources`. 6 catégories Chatham House traduites en français via `TRADE_CAT_LABELS`. Jauges orange (import) et verte (export). Balance en infobulle.
- **Seuil de notabilité paramétrable** (1% / 3% / 5%) via engrenage → modal. Stocké en localStorage (`geopol_res_threshold`).

### Onglet Puissance

**Nav indicateurs gauche** (sticky, catégories pliables + filtre recherche).

**Radar percentilé** avec engrenage indépendant (PIN_RADAR_KEY, axes à choix).

**Courbe** avec projections WEO en pointillés orange séparés (via subcategory='projection').

**Carte D3** geoNaturalEarth1, world-atlas CDN, choroplèthe verte par quantiles (8 buckets).

**Comparaison A vs B** : slot B permanent. Polygone B orange pointillé sur radar, courbe B superposée, valeur B + écart relatif % dans entête. Carte reste sur A seul.

**Bloc « Composition par type »** (étape B) : apparaît UNIQUEMENT pour les 4 indicateurs ressources (`energie_production`, `energie_reserves`, `mineraux_production`, `mineraux_reserves`). Bar chart horizontal trié, Top 10 visible + reste agrégé. Mode comparaison A/B : barres groupées verticalement par sub1 (vert A, orange B).

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

**Barre de filtres en haut** (sticky, reste visible au scroll) :
- **Breadcrumb cliquable** pour drill cumulé (`_relPath`)
- **Sélecteur Référentiel** (segmented) : Partenaire / Catégorie 1 / 2 / 3, n'affiche que les dimensions peuplées
- **Sélecteur Mesure** (segmented) : Volume / Influence (uniquement dim=partner)
- **Sélecteur Partenaires** (dropdown) : 🌍 Monde + zones géo + organisations depuis table `zones`, avec compteur de pays
- **Sélecteur Période** : mode ponctuel (bouton "Plage…") ou mode plage (2 selects min/max + bascule Σ/x̄ + bouton ×). Les bornes sont calculées depuis les années réellement dispo en DB pour l'indicateur.

**Layout principal** :
- Composition (treemap ou barres influence) + Évolution (aires empilées ou courbes influence) côte à côte en haut
- Carte du flux pleine largeur en bas

**Mode Volume vs Influence** :
- Volume : composition = treemap classique (volume sujet), part dans total sujet
- Influence : composition = bar chart horizontal trié par % d'influence, poids du sujet chez chaque partenaire (= volume_sujet / volume_mondial_partenaire). Aires empilées désactivées (pourcentages non additifs), remplacées par courbes superposées Top 5. Clic sur barre → épingle pays, courbe en orange épaisse + bloc stats.
- `_relInfluencePinned` (ISO3 sélectionné), `inf-bars` avec hauteur max 440px + scroll interne

**Carte en %** (Volume ou Influence) :
- Volume : couleur par part dans total sujet (pas en volume absolu)
- Influence : couleur par part chez chaque partenaire
- Hors zone filtrée : grisé `#dde4dd` avec infobulle "hors zone sélectionnée"

**État Relations (variables JS)** :
- `_relEntryKey`, `_relDim`, `_relPath`, `_relCatCollapsed`
- `_relMetric` ('volume' | 'influence')
- `_relInfluencePinned`
- `_relZoneFilter`, `_relZonePartnersCache`
- `_relYearRange` ([yMin, yMax] ou null), `_relYearAggMode` ('sum' | 'avg')

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
- **Manuel assisté IA** : prompts identite/flux affichés copiables. Drag&drop CSV ou **CSV.GZ** → validation + détection conflits (depuis DB en mémoire) → commit dans `uploads/manuel/`

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
- Helpers communs : `escapeHtml`, `safeExec`, `escapeSql`, `sqlList`, `fmtNumber`, `fmtWithUnit`, `scaleSuffix`
- Cache : `cache.identite`, `cache.flux`, `cache.world` ; helpers `_fluxTimelineCache`, `_fluxPartnerTotalsCache`, `_fluxPartnerTotalsTimelineCache`
- Singleton `_worldTopoCache` + `loadWorldTopology()` partagé entre Puissance et Relations

**Code JavaScript admin :**
- Vanilla JS aussi
- Helpers GitHub : `ghFetch`, `ghReadFile`, `ghWriteFile` (base64 UTF-8 safe), `ghTriggerWorkflow`, `ghListRuns`
- Hooks `showPanel` chaînés pour modularité

**Schéma data :**
- `country_iso3` toujours en MAJUSCULES (3 lettres)
- `year` en INTEGER 4 chiffres
- `value` en REAL, jamais 0 par défaut quand la source dit vide
- `source` = nom propre de la source (ex: "Banque Mondiale", "UNHCR", "resourcetrade.earth", "MCS USGS")

**Unités standards (cohérence entre sources) :**
- Énergie et minéraux : `kt` (kilotonnes). MCS USGS converti depuis metric tons, kg, thousand metric dry tons.
- Commerce : `USD` (pas en milliers). resourcetrade.earth × 1000 à l'import (source donne en 1000USD).
- WEO : USD natif (Trillions × 1e9), personnes natives (Millions × 1e6). Conversion via dictionnaire `SCALE_FACTORS` à l'INSERT.

**Workflow d'édition :**
- Aucune modification de fichier sans aval explicite
- Toujours signaler **quels autres fichiers** seront impactés
- Préférer **petites étapes validées** à grosses livraisons
- Tester la syntaxe (JS via `node --check`, Python via `ast.parse`) avant livraison

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

---

## DÉCISIONS ARCHITECTURALES IMPORTANTES (historique)

1. **DB en lecture seule depuis le navigateur** : admin lit la DB R2 en mémoire via sql.js, mais ne peut pas la modifier. Toute modification passe par GitHub Actions.

2. **Pas de clé R2 dans le navigateur** : les commits passent par l'API GitHub (PAT), pas par R2 direct. Cohérent et auditable (commits visibles dans l'historique git).

3. **`config.json` toggle uniquement d'affichage** : désactiver un indicateur dans `config.json` le cache dans l'app mais n'arrête pas la collecte ETL. Pour arrêter la collecte → modifier `etl/config.py` manuellement.

4. **CSV manuel : risque d'écrasement** : `INSERT OR REPLACE` peut écraser les sources auto. Solution : utiliser des indicateurs distincts pour projections (ex: `pib_usd_dgtresor` au lieu de `pib_usd`), OU des années non couvertes.

5. **`manuel.py` tourne en dernier dans `PIPELINE`** : donc en cas de collision, le manuel gagne. Volontaire pour permettre les corrections d'expert.

6. **Bornes années via `etl_config.json`** : `config.py` lit ce fichier au démarrage du pipeline. Pas besoin de modifier le YAML GitHub Actions.

7. **Purge globale (corrigée en mai 2026)** : `build_db.py::purge_hors_bornes()` supprime **toutes les lignes** < `ANNEE_DEBUT` sans filtre par source, parce que les CSV sources restent archivés sur GitHub et seront relus au prochain run. Avant : seuls BM/OWID/UNHCR étaient purgés.

8. **Ordre `build_db.py` (corrigé en mai 2026)** : purge → zones → VACUUM → contrôle taille → upload. Avant : contrôle de taille en premier, avec exit(1) si > seuil, ce qui empêchait la purge de jamais tourner.

9. **commerce_ressources (resourcetrade.earth)** : indicateur flux avec 6 catégories (Fossil fuels, Metals and minerals, Agricultural products, Forestry products, Fertilizers, Pearls and gemstones). Période 2020-2024. Stocké en USD, fichier source en `.csv.gz` (3,5 Mo au lieu de 29 Mo).

10. **Filtres Relations transversaux** : zone + plage + métrique + référentiel se combinent librement. Persistent au changement d'indicateur, reset au changement de sujet.

11. **Carte Relations en % (corrigée en mai 2026)** : Volume → % du sujet, Influence → % chez chaque partenaire. Plus de volume absolu qui faisait ressortir uniquement USA/Chine.

12. **Sticky UI** : barre de filtres Relations + nav indicateurs (Puissance et Relations) sont en `position: sticky` pour rester visibles au scroll.

---

## LIMITES CONNUES & TODO

- **Comtrade** : clé API manquante, source désactivée
- **Parsers semi-auto non codés** : UNDESA, Lowy, ZEE, UNESCO
- **Désalignement `zones.zone_type`** : `build_db.py` crée zones sans `zone_type`, alors qu'`index.html` (mode démo) attendait cette colonne (à vérifier)
- **Sync URL des filtres Relations** : zone, plage, mode Σ/x̄ ne sont pas dans l'URL → partage difficile
- **Comparaison A vs B sur Synthèse** : existe sur Puissance uniquement
- **Étudiants internationaux** : désactivé dans `run_etl.py`, OPRI.zip à inspecter
- **Onglet Ressources dédié** : option C laissée de côté, à voir si A+B (bloc Atouts enrichi + bloc Composition Puissance) suffisent
- **Diagnostic ETL en interface** : fonction `diagUnits()` accessible en console, pourrait devenir un vrai onglet admin
- **Export d'une vue** : pas de export image/PDF/CSV

---

## CHANGEMENTS RÉCENTS (session mai 2026)

### Ajouts majeurs

- **commerce_ressources** : nouvel indicateur flux (resourcetrade.earth, 330 856 lignes 2020-2024)
- **Support `.csv.gz`** côté admin (DecompressionStream) et côté ETL (`gzip.open` dans `manuel.py`)
- **Bloc Atouts en ressources** dans Synthèse : éclatement par sub1 + section Commerce 3 colonnes
- **Bloc Composition par type** dans Puissance : bar chart pour 4 indicateurs ressources
- **Filtre Zone Relations** : dropdown avec zones géo + organisations
- **Filtre Plage temporelle Relations** : 2 selects min/max + bascule Σ/x̄
- **Mode Influence Relations** : bar chart horizontal + courbes superposées + zoom au clic
- **Carte en pourcentage** : Volume → % du sujet, Influence → % chez partenaire
- **Seuil de notabilité paramétrable** ressources : 1/3/5%, stocké localStorage
- **Sticky UI** : barre filtres + nav indicateurs

### Corrections importantes

- **`build_db.py`** : purge globale (était limitée à 4 sources) + ordre des étapes (contrôle taille était avant purge)
- **`weo.py`** : conversion d'unité (Trillions/Millions → USD/personnes natifs) via dict `SCALE_FACTORS`
- **MCS USGS** : harmonisé en `kt` (option choisie : tout en kilotonnes, pas en tonnes)
- **`getCompoBySub1`** : retire la borne `year <= y` qui masquait les données récentes
- **Table pays** : `COUNTRY_REF` source unique, +43 pays (Mauritanie, Côte d'Ivoire, Luxembourg, Islande, et autres)
- **Terminologie** : « chez ce partenaire » au lieu de « total mondial » dans les infobulles
- **Apostrophe Côte d'Ivoire** : échappée avec guillemets doubles

---

## SI TU REPRENDS, COMMENCE PAR

1. **Demander à l'utilisateur ce qu'il veut faire** (correction, nouvelle fonctionnalité, ajout de source, etc.)
2. **Demander les fichiers spécifiques** dont tu as besoin selon la tâche :
   - Modif admin → `admin.html`
   - Modif app (index.html) → demander aval explicite avant de toucher, et préférer travailler sur `geopol_v2.html` si c'est le nom du fichier livré
   - Ajout indicateur auto → `etl/config.py`, le parser concerné, `config.json`
   - Ajout source semi-auto → `etl/config.py`, `run_etl.py`, modèle `etl/sources/sipri.py`
   - Modif pipeline → `run_etl.py`, `etl/build_db.py`
3. **Confirmer la compréhension** avant de coder. Vulgariser si besoin.
4. **Procéder par étapes validées**, pas en une livraison monobloc.
5. **Signaler les impacts** sur les autres fichiers à chaque modification.
6. **Tester en console** : la DB SQLite est `state.db`, pas `window.db`. Les helpers utiles : `diagUnits()`, `state.indicators`, `state.subject`, `state.year`.

---

## RÉFÉRENCES UTILES

- Notice utilisateur de l'admin : `NOTICE_ADMIN.md` (à demander si besoin)
- Prompts de transformation CSV : `prompts_transformation_csv.md` (à demander si besoin)
- Todo actuel : `todo.md` (à demander si besoin)
- Fichiers ressources livrés en mai 2026 :
  - `commerce_ressources_resourcetrade_2020_2024.csv.gz` (dans `uploads/manuel/`)
  - `MCS_geopol_harmonise_kt.csv` (dans `uploads/manuel/`)

*Fin du prompt de reprise. L'utilisateur va maintenant te dire sur quoi il veut travailler.*
