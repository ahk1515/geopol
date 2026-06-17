# GÉOPOL — Prompt de reprise de conversation

> **Usage :** colle l'intégralité de ce fichier en début de nouvelle conversation avec Claude pour qu'il reprenne le projet là où on l'a laissé. L'assistant te demandera les fichiers spécifiques dont il a besoin selon la tâche.
>
> **Dernière mise à jour :** session juin 2026 — réparation ETL IMF IMTS, optimisation taille DB (filtre de seuils, −303 Mo), console SQL admin, migration clé `identite` (subcategory), correction parser Energy Institute, contrôle qualité "Santé des données", flyer d'accueil + panneau À propos dans l'app.

---

## TON RÔLE

Tu travailles sur **GÉOPOL**, une application web personnelle de visualisation géopolitique.

Tu dois :
- Être **garant de la conception globale** et de la **cohérence de l'ensemble**
- Développer un **sens critique constructif** : remettre en question les choix qui ne tiennent pas, proposer mieux quand c'est utile, ne pas hésiter à dire « non, voici pourquoi »
- Être **concis** dans tes réponses, jamais flatteur ni redondant
- **Vulgariser** quand l'utilisateur n'est pas développeur (il ne l'est pas)
- **Demander confirmation avant de coder** — l'utilisateur formule souvent sa pensée en plusieurs messages ; ne pars pas en codage dès le premier signal
- **Décider pour lui** quand il te dit "tu décides" — c'est une marque de confiance
- **Ne jamais modifier des fichiers tiers sans aval explicite**
- **Mesurer avant d'agir** : la méthode qui a payé toute la session = diagnostiquer/mesurer les données réelles avant de coder une correction ou un seuil (ex. tester l'API en conditions réelles, mesurer une distribution avant de fixer un seuil)
- **Tester ce qui peut l'être** avant de livrer (parsing, syntaxe via `node --check` / `py_compile`, cas limites, tests d'intégration sur base simulée)

L'utilisateur préfère qu'on **avance par étapes courtes validées** plutôt qu'avec de grandes livraisons monobloc.

**Conventions de dialogue :**
- L'utilisateur teste en console (F12 du navigateur). La DB SQLite est `state.db` dans l'app, `db` (global) dans l'admin.
- Quand tu lui demandes des choix multiples, utilise le tool `ask_user_input_v0` plutôt que des listes à puces (plus rapide sur mobile).
- Tu peux le challenger franchement : « tu as raison de me reprendre » est mieux que « excellente question ! ».
- Quand tu fais une erreur, dis-le clairement et corrige sans t'excuser longuement.
- Il a un **PC pro bridé** : pas de Python local, pas d'admin. Il édite via l'interface GitHub et lance l'ETL via le panel admin. Il peut désormais **interroger la DB sans run** via la console SQL de l'admin (voir plus bas).

---

## ARCHITECTURE DU SYSTÈME

```
   Sources externes (APIs / CSV)
   WB · OWID · UNHCR · IDS · SIPRI · IMF IMTS · WEO
   Energy Institute · USGS · Marine Regions · resourcetrade.earth
                  │
                  ▼
   GitHub Actions — run_etl.py  ← lit etl_config.json
   (télécharge la DB R2, migre, parse, build, ré-upload)
                  │
                  ▼
   geopolitique.db  (Cloudflare R2, persistante entre runs)
                  │ fetch public
                  ▼
   index.html (app)  ←→  admin.html (pilotage)
   ahk1515.github.io      lit status.json + DB R2
                          commits via PAT, workflow_dispatch
```

**Comptes & URLs :**
- GitHub : `ahk1515` / repo : `geopol`
- App : https://ahk1515.github.io/geopol
- Admin : https://ahk1515.github.io/geopol/admin.html
- R2 public : https://pub-710d496c94c74cb3837b8229bc8f4410.r2.dev
  - DB : `/geopolitique.db`  ·  Status : `/status.json`

**Stack :**
- HTML/CSS/JS vanilla (pas de framework)
- sql.js (SQLite/WASM) pour charger la DB côté navigateur
- D3.js pour les visualisations dans `index.html` ; topojson world-atlas (CDN) pour les cartes
- Python 3.11 pour l'ETL sur GitHub Actions
- Cloudflare R2 (S3-compatible) pour stocker la DB

**IMPORTANT — la DB persiste entre runs :** le workflow télécharge `geopolitique.db` depuis R2 au début de chaque run, applique migrations + parsers dessus, puis ré-upload. La base n'est PAS reconstruite de zéro. Conséquence : un changement de schéma (`CREATE TABLE IF NOT EXISTS`) ne s'applique PAS à une table déjà existante → il faut une **migration explicite** (cf. `etl/migrate.py`).

**Sandbox Claude :** `raw.githubusercontent.com` est accessible (permet `curl` des fichiers du repo). `api.imf.org` et `wits.worldbank.org` sont bloqués. Pour explorer une API externe : `web_search` puis `web_fetch` sur les URLs des résultats.

---

## SCHÉMA SQL

```sql
identite (
  country_iso3 TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT, subcategory TEXT DEFAULT '',
  PRIMARY KEY (country_iso3, indicator, year, subcategory)   -- subcategory AJOUTÉE juin 2026
)

flux (
  country_from TEXT, country_to TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT,
  subcategory_1 TEXT, subcategory_2 TEXT, subcategory_3 TEXT,
  PRIMARY KEY (country_from, country_to, indicator, year, subcategory_1)
)

zones ( zone_id TEXT, zone_nom TEXT, country_iso3 TEXT )
```

**⚠️ Migration clé `identite` (juin 2026) :** la PK incluait seulement `(country_iso3, indicator, year)`, ce qui faisait s'écraser tous les indicateurs à subcategory (minéraux, énergie) — il ne restait qu'une valeur par pays/indicateur/année. Corrigé par `etl/migrate.py` (ajout `subcategory` à la PK) + conversion des `subcategory NULL` en `''` (dans une PK SQLite, deux NULL sont distincts → un `INSERT OR REPLACE` ne dédupliquerait plus les indicateurs sans subcategory ; la chaîne vide `''` déduplique correctement). **Tous les parsers identite insèrent désormais `''` et non `None`.**

**Sentinelles `flux` :**
- `__multilateral__` : créancier institutionnel (FMI, BM)
- `__private__` : créancier privé
- `__intra__` : flux interne à un groupe
- Agrégats IMF : codes commençant par `G` (G001=World, G998=UE)

**Convention commerce (CRUCIAL) :**
- `import_commercial` : `country_to` = importateur (sujet), `country_from` = fournisseur. L'app lit `subjectCol='country_to'`.
- `export_commercial` : `country_from` = exportateur (sujet), `country_to` = destinataire. L'app lit `subjectCol='country_from'`.
- Le parser IMF IMTS génère les **deux indicators** pour chaque flux (même paire `country_from/country_to`, seul l'indicator change). C'est un **doublon pur** (~117 k lignes redondantes).

**Doublons connus (non corrigés — redondance assumée) :**
- `import_commercial` ↔ `export_commercial` (~117 403 lignes chacun, doublon pur)
- `transferts_armement` ↔ `export_armement` (~2 130 lignes chacun, doublon pur, mêmes valeurs/sens)
- Suppression possible (gain ~119 k lignes, ~20 Mo) mais touche l'app → en réserve, non prioritaire tant que la taille n'est pas critique.

---

## ARBORESCENCE DU REPO

```
ahk1515/geopol/
├── admin.html                    Interface d'administration (~3950 lignes)
├── index.html                    App publique (~7300 lignes, 5 onglets)
├── config.json                   Indicateurs affichés dans l'app
├── etl_config.json               Bornes années, pays (modifié par admin)
├── referentiel.json              Pays : ISO3, organisations, attributs
├── run_etl.py                    Orchestrateur ETL (migration + pipeline + build)
├── prompt_initialisation.md      Ce fichier
├── NOTICE_ADMIN.md               Manuel utilisateur de l'admin
├── prompts_transformation_csv.md Prompts IA pour transformer CSV → schéma GÉOPOL
├── todo.md                       Tâches en cours
│
├── etl/
│   ├── config.py                 Config centrale (ANNEE_DEBUT/FIN, indicateurs WB...)
│   ├── migrate.py                Migrations de schéma (clé identite) — tourne EN PREMIER
│   ├── construits.py             Indicateurs dérivés (balance_commerciale, densite...)
│   ├── build_db.py               Purge + filtre seuils + zones + VACUUM + contrôle taille + upload R2
│   ├── build_referentiel.py      Génère referentiel.json
│   └── sources/
│       ├── banque_mondiale.py    API WB — identite
│       ├── banque_mondiale_ids.py API WB IDS — dette bilatérale (flux)
│       ├── owid.py               OWID Charts API
│       ├── imf_imts.py           IMF IMTS — commerce bilatéral (RÉPARÉ juin 2026)
│       ├── unhcr.py              UNHCR — réfugiés
│       ├── weo.py                IMF WEO — pib_usd, population (+ projections)
│       ├── sipri.py              SIPRI CSV — armement (semi-auto)
│       ├── energy_institute.py   Energy Institute — énergie (CORRIGÉ juin 2026)
│       ├── zee.py                Marine Regions — ZEE
│       ├── manuel.py             Parser générique CSV manuels (USGS minéraux, etc.)
│       ├── comtrade.py           DÉSACTIVÉ (pas de clé Premium)
│       ├── wits.py               Tentative ratée, à supprimer
│       ├── etudiants.py / opri.py  UNESCO OPRI — désactivé
│       └── uploads/              CSV semi-auto (SIPRI, Energy Institute .xlsx)
│
├── uploads/manuel/               CSV manuels (USGS MCS, etc.)
└── .github/workflows/etl.yml     Scheduler (timeout 360min) + download DB R2 en préambule
```

---

## SECRETS GITHUB ACTIONS

| Secret | Usage |
|---|---|
| `R2_ACCOUNT_ID` | Compte R2 |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_KEY` | Clés R2 |
| `R2_BUCKET` | `geopol-db` |
| `R2_PUBLIC_URL` | URL publique R2 |

---

## ÉTAT DE LA DB (réf. fin de session juin 2026)

- **Taille** : ~273 Mo (après filtre de seuils ; était ~576 Mo avant)
- **Seuils taille** (`build_db.py`) : warning `DB_SIZE_LIMIT_MB=450`, erreur `DB_SIZE_ALERT_MB=480` (`sys.exit(1)`)
- **Période** : 2020 → 2050 (projections WEO incluses). `ANNEE_DEBUT` configurable via `etl_config.json`
- **Lignes flux** : ~1,39 M (était 2,24 M avant filtre)
- **Lignes identite** : ~33 k + ressources

| Source | Indicateurs | Lignes (ordre) | Table |
|---|---|---|---|
| Banque Mondiale | population, PIB, etc. | ~10 k | identite |
| OWID | age_median, etc. | ~3,7 k | identite |
| **IMF IMTS** | import_commercial, export_commercial | **~234 k** (réparé) | flux |
| Banque Mondiale IDS | dette_exterieure (subcat_1) | ~248 k | flux |
| UNHCR | refugies | ~785 k → filtré (≥50) | flux |
| (manuel) | etudiants_international | ~804 k → filtré (≥25) | flux |
| resourcetrade.earth | commerce_ressources (USD) | ~331 k → filtré (≥500k) | flux |
| (manuel) | migrants | ~273 k | flux |
| SIPRI | transferts_armement / export_armement | ~2,1 k ×2 | flux |
| Construits | densite, balance_commerciale | ~6 k | identite |
| IMF WEO | pib_usd, population (projections) | ~12 k | identite |
| Energy Institute | energie_production/reserves (+_share) | ~2,3 k (corrigé, 87 pays) | identite |
| USGS MCS (via manuel) | mineraux_production/reserves (+_share) | ~1,7 k (corrigé, 62 pays) | identite |
| Marine Regions | zee | ~0 (parser renvoie 0, à investiguer) | identite |

---

## FILTRE DE SEUILS (`build_db.py`, juin 2026)

Dict `SEUILS_FLUX` en tête de `build_db.py`, appliqué par `filtre_seuils()` **entre `purge_hors_bornes()` et `build_zones()`** (après que `construits` a calculé ses totaux sur données complètes, avant le VACUUM). Non destructif : ré-appliqué à chaque run sur données rechargées.

```python
SEUILS_FLUX = {
    "refugies":               {"type": "absolu", "valeur": 50},      # personnes, médiane 26
    "etudiants_international": {"type": "absolu", "valeur": 25},      # personnes, médiane 16
    "commerce_ressources":    {"type": "absolu", "valeur": 500_000}, # USD, médiane 481k
}
```
- Indicateurs absents du dict = non filtrés (dette, armement, migrants, diplo, import/export_commercial conservés).
- Type `relatif` (seuil bilatéral "part chez A ET chez B") = squelette prévu, non implémenté.
- Calibrage via diagnostic de distribution (méthode : mesurer la distribution réelle avant de fixer un seuil). Seuil = en effectifs pour les flux en personnes, en valeur pour le monétaire — **le seuil dépend de l'unité, pas de l'indicateur.**

---

## INDEX.HTML — STRUCTURE ACTUELLE (5 onglets, refonte terminée)

Top bar transverse : bouton ⌕ Rechercher (sujet), slider année (`state.year`), bouton **ℹ️ À propos**, badge DB.

**Écran de chargement (juin 2026) :** progression réelle (Mo / débit / ETA via streaming `res.body.getReader()` + `Content-Length`), messages d'erreur explicites selon le blocage (HTTP / réseau / base corrompue → bascule mode démo), + flyer d'accueil (familles de données, croisement, volume/influence, temporalité, absence≠zéro).

**Panneau À propos (ℹ️) :** open-source/expérimental, types de données, lecture volume/influence (exemple France-Sénégal), lecture des absences (manquant/zéro/filtré), temporalité+projections, sources, date dernière maj (depuis status.json). Valeurs pays/années calculées dynamiquement (`fillAboutDynamic`).

### Onglet Synthèse
Portrait d'identité. Cartes valeurs clés + sparklines + rang. Panorama 2 colonnes à deux dénominateurs (« qui pèse pour le sujet » = part dans le sujet ; « pour qui le sujet pèse » = poids du sujet chez chaque partenaire). Bloc « Atouts en ressources » (énergie/minéraux/commerce ressources, seuil notabilité paramétrable).

### Onglet Puissance
1 sujet, 1 indicateur. Nav indicateurs gauche (sticky, catégories pliables). Radar percentilé, courbe (projections WEO en pointillés via `subcategory='projection'`), carte D3 choroplèthe. Bloc « Composition par type » pour les 4 indicateurs ressources (bar chart par sub1). *Le slot compareB a été retiré → déplacé vers Comparaisons.*

### Onglet Relations
1 sujet, N partenaires. Nav indicateurs gauche avec libellés contextuels par sens (`FLOW_DIRECTIONS` : dette to=Créanciers/from=Débiteurs, armement to=Fournisseurs/from=Bénéficiaires, etc.). Mode Volume / Influence. Composition (treemap/barres) + Évolution + Carte. *Le mode bilatéral a été retiré → déplacé vers Comparaisons.*

### Onglet Croisé
1 sujet, N indicateurs. Grille de tuiles macro, 3 vizs par tuile (🗺 Carte / ▦ Treemap / 📈 Aires). Mode Volume/Influence, filtre zone, préselections thématiques, période globale + override par tuile (Σ cumul / x̄ moyenne), hover sync entre tuiles. Sync URL : `tab`, `cs`, `cm`, `cz`, `cvs`.

### Onglet Comparaisons (bilatérales)
2 sujets A↔B. Profil de flux 2 colonnes + tornado de puissance (barres miroir normalisées). B = pays ou zone. Sparklines des parts, flèches de tendance.

### Conventions JS app
- Helpers : **`escAttr`** (PAS `escapeHtml`), `safeExec`, `escapeSql`, `sqlList`, `fmtNumber`, `fmtWithUnit`, `scaleSuffix`, `fmtMo`
- Cache : `cache.identite`, `cache.flux`, `cache.world` + caches flux dédiés
- `state.db` (SQLite), `state.year`, `state.subject`, `state.config`, `state.yearBounds`
- Table pays : `COUNTRY_REF` (ISO3 → name/flag/continent/num). Apostrophes échappées en guillemets doubles : `name:"Côte d'Ivoire"`
- Validation : extraire le `<script>` applicatif, `node --check` avant livraison

---

## ADMIN.HTML — STRUCTURE ACTUELLE (6 onglets)

`db` (global) = DB SQLite chargée depuis R2 au boot (`loadDbFromR2`) ou via badge "Changer". Système nav : `nav-btn` + `showPanel(id)` + `panel-{id}`. `showPanel` est **chaîné** (plusieurs `_originalShowPanel*` en cascade ; ajouter un onglet = nouveau maillon en fin). Helpers GitHub : `ghReadFile`, `ghWriteFile` (base64 UTF-8), `ghFetch`, `ghTriggerWorkflow`, `ghListRuns`. PAT en `localStorage` (`geopol_admin_pat`).

1. **Suivi ETL** — statut sources (status.json), durée/lignes/erreurs, bouton run manuel, historique runs, auto-refresh.
2. **Imports** — 3 sous-onglets (Auto récap / Semi-auto drag&drop vers `etl/sources/uploads/` / Manuel assisté IA vers `uploads/manuel/`, support `.csv.gz`).
3. **Pilotage DB** — KPIs, curseurs années → `etl_config.json`, toggles indicateurs → `config.json`, bouton commit + relance.
4. **Couverture** — matrice couverture par indicateur, filtres, drill-down pays manquants + export CSV.
5. **🔍 Console SQL** (juin 2026) — interroge `db` en **lecture seule** (garde-fou `sqlIsReadOnly` : SELECT/WITH only, bloque écritures + requêtes multiples). Textarea + Ctrl+Entrée, résultat en tableau, export CSV, ~9 requêtes pré-enregistrées (`SQL_PRESETS` : poids par indicateur, années distinctes, distribution, subcategory, dbstat...). Hook `_originalShowPanelSql`.
6. **🩺 Santé données** (juin 2026) — batterie de contrôles de cohérence non bloquants (vert/orange/rouge), 4 familles : **Couverture** (indicateurs à <5 pays), **Plausibilité** (valeurs négatives ; sauts ×10/÷10 entre années), **Structure** (clé PK identite, NULL résiduels), **Cohérence croisée** (production vs _share synchronisés, parts ~100%, doublons connus). `SANTE_CHECKS[]`, `runSante()`, hook `_originalShowPanelSante`. Réflexe : lancer après chaque run (recharger la base d'abord).

---

## CONVENTIONS À RESPECTER

**Python :**
- UTF-8, logs avec emojis (✅ ❌ ⚠️ ⏭️)
- Règle **transparence > complétude** : donnée absente → pas d'insertion, jamais d'interpolation
- `INSERT OR REPLACE` pour les révisions ; subcategory vide = `''` (jamais `None`) dans `identite`
- Chaque parser retourne le nombre de lignes via `run()`
- `migrate.run()` tourne en PREMIER (avant les parsers) dans `run_etl.py`

**JS (app + admin) :** vanilla, variables CSS pour le thème (`--bg`, `--green`, `--orange`, `--terra`), IBM Plex Mono+Sans / Fraunces titres.

**Schéma data :** `country_iso3` MAJUSCULES 3 lettres ; `year` INTEGER ; `value` REAL jamais 0 par défaut ; `source` = nom propre. Unités : énergie/minéraux en `kt`, commerce en `USD`.

**Ordre `build_db.run()` :** taille init → `purge_hors_bornes` (year < ANNEE_DEBUT seulement, borne basse) → `filtre_seuils` → `build_zones` → `optimize_db` (VACUUM + index) → contrôle taille → upload R2 → status.json. ⚠️ Pas de purge borne haute (préserve projections WEO).

**Workflow d'édition :**
- Aucune modification sans aval explicite ; signaler les fichiers impactés
- Petites étapes validées ; tester syntaxe avant livraison
- `raw.githubusercontent.com` accessible en `curl` pour récupérer les fichiers réels

---

## CLÉS LOCALSTORAGE

| Clé | Usage |
|---|---|
| `geopol_admin_pat` | PAT GitHub (admin) — **lié au navigateur/poste** (re-saisir si changement de machine) |
| `geopol_admin_ignored_orphans` | Indicateurs orphelins ignorés |
| `geopol_pins_synthese` / `geopol_pins_radar` | Épinglages Synthèse / axes radar |
| `geopol_pins_flux_partner_v3` / `geopol_pins_flux_influence_v3` | Entrées flux Synthèse |
| `geopol_res_threshold` | Seuil notabilité ressources |
| `geopol_cross_selected` / `geopol_cross_view_types` / `geopol_cross_tile_periods` | État onglet Croisé |

---

## DÉCISIONS ARCHITECTURALES IMPORTANTES

1. **DB lecture seule depuis le navigateur** : admin lit la DB R2 en mémoire (sql.js), ne la modifie pas. Modifications via GitHub Actions uniquement.
2. **Pas de clé R2 dans le navigateur** : commits via API GitHub (PAT).
3. **`config.json` = toggle d'affichage** : désactiver un indicateur le cache dans l'app, n'arrête pas la collecte ETL.
4. **DB persistante entre runs** (téléchargée depuis R2 en préambule) → changement de schéma = migration explicite (`migrate.py`).
5. **`manuel.py` tourne en dernier** dans le pipeline : en cas de collision, le manuel gagne.
6. **Purge borne basse seulement** (`purge_hors_bornes`) : préserve projections WEO (jusqu'à 2050).
7. **IMF IMTS remplace Comtrade** (juin 2026) : endpoint SDMX 3.0 `api.imf.org/.../IMTS/~/{REPORTER}.MG_CIF_USD.*.A` (wildcard `*` partenaire OBLIGATOIRE), format CSV, filtre `c[TIME_PERIOD]=ge:{year}` indispensable. Piège SCALE=6 mais OBS_VALUE déjà en USD bruts → NE PAS multiplier. Garde-fou : exception si 0 ligne avec reporters présents. Subcategory_1='total'.
8. **Filtre de seuils** (juin 2026) : allège la table flux ; seuils par unité (effectif/monétaire), pas par indicateur.
9. **Migration clé identite + subcategory `''`** (juin 2026) : voir section SCHÉMA SQL.
10. **Bug Energy Institute corrigé** (juin 2026) : le fichier EI répète l'en-tête d'année sur plusieurs colonnes (volume, puis "Growth rate", puis "Share") → le parser gardait la dernière (la part) au lieu du volume. Fix dans `parse_series_sheet` : ne garder que la PREMIÈRE colonne par année.

---

## PROCHAINS CHANTIERS (conçus, non implémentés)

### Exploration indicateur-centrée (priorité suivante)
Idée : partir de l'**indicateur** (pas du pays) pour voir les grands équilibres mondiaux d'un flux. Inspiré de l'Atlas of Economic Complexity (Harvard) — bascule de perspective façon `view=products` / `view=markets`.

**Décisions de conception déjà prises :**
- **Intégrer dans l'onglet Relations** comme une bascule "pays-centré ↔ indicateur-centré" (plutôt qu'un onglet séparé), pour réutiliser carte/temporel/sélecteurs existants.
- **Écran unique adaptatif** avec notion de **profondeur** (0 = structure mondiale ; 1/2/3 = subcategory). Affordance : l'interface signale si on peut creuser ou non. "Structure mondiale d'abord" = vue par défaut.
- La **forme dépend de la structure de la donnée** (à piloter via une table de métadonnées par indicateur) :
  - flux plats (commerce IMF 'total', refugies, etudiants, migrants) → classement + carte, pas de dépliage
  - hiérarchique → treemap façon Atlas
  - parallèle (dette : sub1=type créancier, sub2 non hiérarchique ~107 valeurs) → tableau croisé
- **"Qui produit quoi"** sur les ressources (énergie/minéraux, données d'IDENTITÉ avec subcategory, désormais saines) : classement de pays par ressource + carte de densité + `_share` (concentration). Carte choroplèthe (pas réseau de couloirs, ce sont des stocks pas des flux).

**Carte des subcategory (mesurée juin 2026, table flux) :**
| indicateur | sub1 | sub2 | sub3 | nature |
|---|---|---|---|---|
| export/transferts_armement | 141 | 1037 | 161 | profond (types d'équipements) |
| dette_exterieure | 4 | 107 | 0 | parallèle (type créancier × créancier) |
| commerce_ressources | 6 | 0 | 0 | 1 niveau |
| representation_diplomatique | 4 | 0 | 0 | 1 niveau |
| import/export_commercial | 1 ('total') | 0 | 0 | plat |
| refugies/etudiants/migrants | 0 | 0 | 0 | plat |
Ressources (identite) : energie_production = 4 types, mineraux_production = 19 types.

**Prérequis avant code :** regarder comment l'onglet Relations est construit dans `index.html` pour greffer la bascule sans casser l'existant ; définir si tous les flux ont un sens émetteur→récepteur clair.

### Autres pistes en réserve
- **Déduplication doublons** commerce + armement (~119 k lignes, ~20 Mo) — touche l'app, non prioritaire.
- **Config admin des seuils** : transformer `SEUILS_FLUX` (codé en dur) en `seuils_config.json` éditable depuis l'admin. Jugé non prioritaire (les seuils bougent rarement).
- **Contrôle de régression dans Santé données** : comparer le nb de lignes par indicateur au run précédent (via historique status.json) pour détecter les chutes brutales.
- **ZEE renvoie 0 lignes** : parser `zee.py` à investiguer.
- **WITS** : parser à supprimer (tentative ratée).

---

## LIMITES CONNUES

- **Comtrade** désactivé (code commenté, parser conservé)
- **Parsers semi-auto non codés** : UNDESA, Lowy, UNESCO
- **migrants** : 2 années seulement (2020, 2024 — données quinquennales ONU), peu de bruit, non filtré
- **representation_diplomatique** : 2 années (2021, 2023)
- **Export d'une vue** : pas d'export image/PDF
- **Mobile** : pas prioritaire

---

## SI TU REPRENDS, COMMENCE PAR

1. **Demander à l'utilisateur ce qu'il veut faire.**
2. **Récupérer les fichiers réels** via `curl` sur `raw.githubusercontent.com/ahk1515/geopol/refs/heads/main/<chemin>` (ne pas coder à partir de ce prompt seul, qui peut être daté).
3. **Confirmer la compréhension avant de coder.** Vulgariser. Avancer par étapes validées.
4. **Mesurer avant d'agir** quand il s'agit de données (utiliser la console SQL admin, ou un diagnostic temporaire).
5. **Tester** (syntaxe + cas limites) avant livraison. Signaler les fichiers impactés.

*Fin du prompt de reprise. L'utilisateur va te dire sur quoi travailler.*
