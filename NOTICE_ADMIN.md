# GÉOPOL — Notice de l'administrateur

> Comment utiliser `admin.html` pour piloter la base GÉOPOL, suivre le pipeline, ajouter des indicateurs et résoudre les pannes courantes.
> Document destiné à l'usage personnel — à conserver dans le repo `geopol`.

---

## Table des matières

1. [Vue d'ensemble du système](#1-vue-densemble-du-système)
2. [Première utilisation](#2-première-utilisation)
3. [Navigation dans l'admin](#3-navigation-dans-ladmin)
4. [Onglet Suivi ETL](#4-onglet-suivi-etl)
5. [Onglet Pilotage DB](#5-onglet-pilotage-db)
6. [Onglet Couverture](#6-onglet-couverture)
7. [Onglet Imports](#7-onglet-imports)
8. [Outils legacy (Import CSV local, Journal, Stats, Migrations)](#8-outils-legacy)
9. [Ajouter un indicateur — procédures](#9-ajouter-un-indicateur--procédures)
10. [Dépannage](#10-dépannage)
11. [Annexe — Anatomie du système](#11-annexe--anatomie-du-système)
12. [Annexe — Prompts IA prêts à l'emploi](#12-annexe--prompts-ia-prêts-à-lemploi)

---

## 1. Vue d'ensemble du système

GÉOPOL est composé de **trois éléments** qui communiquent entre eux :

| Élément | Rôle | Où ça vit |
|---|---|---|
| **App web** (`index.html`) | Affiche les données géopolitiques | https://ahk1515.github.io/geopol |
| **Base de données** (`geopolitique.db`) | Stocke toutes les données (SQLite) | Cloudflare R2 (URL publique) |
| **Pipeline ETL** (`run_etl.py` + modules) | Récupère les données, construit et publie la DB | GitHub Actions (tourne tous les lundis à 3h UTC) |

**`admin.html`** est l'interface qui te permet de piloter tout ça sans toucher au code :
- Voir l'état du pipeline et lancer un run
- Changer les bornes d'années
- Activer/désactiver l'affichage d'indicateurs
- Voir où il manque des données
- Déposer des fichiers (CSV manuels, exports SIPRI...)

L'admin **ne modifie jamais la DB directement**. Il modifie des fichiers de configuration sur GitHub, puis déclenche le pipeline qui, lui, refait la DB.

> **Demande à une IA d'approfondir cette section :**
> > Lis le fichier NOTICE_ADMIN.md du projet GÉOPOL et explique-moi en détail l'architecture du système : qui communique avec qui, dans quel sens, et pourquoi cette séparation a été choisie. Vulgarise pour quelqu'un qui n'est pas développeur.

---

## 2. Première utilisation

### 2.1 Accéder à l'admin

L'admin est servi par GitHub Pages comme le reste de l'app :
**https://ahk1515.github.io/geopol/admin.html**

⚠️ **N'ouvre jamais admin.html en local par double-clic** (URL `file:///`). Les navigateurs bloquent les requêtes réseau dans ce contexte, et rien ne fonctionnera.

### 2.2 Créer ton Personal Access Token (PAT) GitHub

Le PAT est requis pour toutes les actions qui modifient le repo (déclencher un run, commiter une config, uploader un CSV). Il est créé une seule fois.

**Étapes** :

1. https://github.com → ton avatar → **Settings**
2. Menu de gauche, tout en bas → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
4. Configurer :
   - **Token name** : `geopol-admin`
   - **Expiration** : 90 jours (ou plus)
   - **Repository access** : "Only select repositories" → choisir `ahk1515/geopol`
   - **Repository permissions** : descendre et changer :
     - **Actions** → "Read and write"
     - **Contents** → "Read and write"
     - (`Metadata: Read-only` est ajouté automatiquement, ne pas y toucher)
5. **Generate token** en bas de page
6. **Copier le token immédiatement** (commence par `github_pat_…`) — il ne sera plus jamais affiché

### 2.3 Connecter le PAT dans l'admin

1. Sur admin.html, clic sur le badge **"Non connecté"** en haut à droite
2. Coller le token dans le champ
3. **Connecter**
4. Le badge passe au vert "GitHub connecté"

**Le token est stocké uniquement dans le `localStorage` de ton navigateur**, sur cet ordinateur. Si tu changes de machine, il faudra le recoller.

### 2.4 Vérifications de bon fonctionnement

Au chargement, tu dois voir :
- Badge DB en haut milieu : **"geopolitique.db · ~160 Mo"** en vert (chargement depuis R2)
- Badge auth : **"GitHub connecté"** en vert
- Onglet **Suivi ETL** ouvert par défaut, avec les 6 sources qui apparaissent

Si quelque chose cloche → voir [§10 Dépannage](#10-dépannage).

> **Demande à une IA d'approfondir cette section :**
> > Lis NOTICE_ADMIN.md de GÉOPOL et guide-moi pas à pas, en mode dialogue, pour créer mon PAT GitHub et le connecter dans admin.html. Pose-moi des questions à chaque étape pour vérifier que je suis bien.

---

## 3. Navigation dans l'admin

L'admin a **deux groupes** d'onglets dans la barre latérale gauche :

### Pilotage (les 4 onglets principaux)
| Onglet | À quoi ça sert |
|---|---|
| 📡 **Suivi ETL** | Voir l'état du pipeline, déclencher un run |
| 📥 **Imports** | Vue des sources auto, dépôt CSV semi-auto, manuel IA |
| ⚙️ **Pilotage DB** | Bornes années, toggles indicateurs |
| 🌐 **Couverture** | Matrice de qualité des données, drill-down |

### Outils (legacy, mode debug)
| Onglet | À quoi ça sert |
|---|---|
| 📄 Import CSV local | Importer un CSV dans une DB locale (test) |
| 📋 Journal | Historique des imports locaux |
| 📊 Statistiques | Stats sur la DB locale |
| 🔧 Migrations | Évolutions du schéma SQL |

Les outils legacy fonctionnent sur une DB chargée en local (bouton "Changer" dans le header). Ils ne servent quasi jamais dans l'usage courant — l'admin moderne (les 4 onglets du haut) suffit.

### Le header

| Élément | Action |
|---|---|
| **Logo GÉOPOL** | Indication visuelle |
| Badge **auth** (à droite) | Cliquer pour gérer la connexion PAT |
| Badge **DB** (au milieu) | Cliquer pour charger un .db local (override R2) |
| Bouton **⬇ Exporter .db** | Télécharger la DB en cours sur ton disque |

---

## 4. Onglet Suivi ETL

L'onglet par défaut. Vue d'ensemble de la santé du pipeline.

### 4.1 Ce que tu vois

**Bannière en haut (si un run est en cours)** : indication "Pipeline en cours d'exécution" avec un lien direct vers GitHub Actions.

**4 vignettes de synthèse** :
- Taille DB actuelle
- Lignes au total
- Sources OK / total
- Date du dernier run

**Bandeau d'action** :
- Bouton vert **▶ Déclencher un run manuel** (nécessite PAT)
- Lien **↗ Actions GitHub** vers la page workflow

**Tableau "Sources — dernier run"** : chaque source listée avec son statut, sa durée, ses lignes insérées, ses erreurs éventuelles.

**Historique des 5 derniers runs** : qui les a lancés, quand, succès/échec, durée.

**Footer discret** : compteur de quota API GitHub restant.

### 4.2 Déclencher un run manuel

**Quand ?**
- Tu viens de modifier `etl_config.json` ou un CSV manuel et tu veux voir le résultat tout de suite
- Une source a échoué et tu veux retenter
- Tu mets à jour le code d'un parser Python et veux le tester

**Comment ?**
1. Bouton vert **▶ Déclencher un run manuel**
2. Confirmer dans le popup
3. Attendre ~60 secondes que le run apparaisse dans l'historique
4. L'admin se rafraîchit automatiquement toutes les 30s tant que le run tourne
5. Quand statut = "succès", c'est terminé

**Durée typique** : 5 à 10 minutes pour un run complet.

⚠️ Un run = re-télécharge **toutes les sources** et reconstruit la DB. Ce n'est pas un "patch" d'une seule source.

### 4.3 Comprendre les statuts

| Icône | Statut | Signification |
|---|---|---|
| ⏳ | queued | En file d'attente GitHub |
| 🔄 | in_progress | En cours d'exécution |
| ✓ | success | Réussi |
| ✕ | failure | Échec — voir les logs GitHub |
| ⊘ | cancelled | Annulé |

En cas d'échec : clic sur le lien **↗** de la ligne → ouvre les logs détaillés sur GitHub Actions.

> **Demande à une IA d'approfondir cette section :**
> > Lis la section "Onglet Suivi ETL" de NOTICE_ADMIN.md de GÉOPOL. Réexplique-moi ce qu'est le pipeline ETL, ce qui se passe quand je déclenche un run, et comment interpréter les statuts. Sois pédagogue et imagé.

---

## 5. Onglet Pilotage DB

Modifier la configuration du pipeline et de l'app.

### 5.1 Les 3 vignettes de synthèse

| Vignette | Sens |
|---|---|
| **Bornes config actuelle** | Ce qui est dans `etl_config.json` sur GitHub |
| **Période réelle DB** | Ce qui est effectivement dans la DB R2 |
| **Estimation après modif** | Taille estimée si tu commits les modifs en cours |

Si les deux premières divergent (cas après modif sans run), une alerte orange apparaît : "Relance le pipeline pour synchroniser".

### 5.2 Curseurs des bornes années

Deux curseurs : début et fin. Plage **1980 → 2050** (couvre passé et projections).

**Pour modifier** :
1. Faire glisser le curseur
2. La bannière orange "Modifications non commitées" apparaît
3. Bouton **⬆ Commit + (option) relance pipeline** devient actif

**Effet** :
- `etl_config.json` est commité avec les nouvelles bornes
- Le prochain run du pipeline (auto lundi ou manuel) utilisera ces bornes
- La DB sera **reconstruite** avec uniquement les données dans ces bornes
- Réversible : il suffit de remettre les bornes initiales et relancer

⚠️ **Couper l'antériorité (passer début de 2000 à 2010)** = au prochain run, la DB perd les données 2000-2009. Pour les récupérer plus tard : remettre 2000 et relancer.

### 5.3 Toggle "Tous les pays"

Pour l'instant, on ou off. La sélection fine pays par pays sera ajoutée si besoin.

### 5.4 Toggles indicateurs (config.json)

Liste des 31 indicateurs groupés par catégorie (démographie, économie, militaire, etc.). Chaque ligne :
- Toggle on/off
- Label, code, unité
- Badge `identite` ou `flux`

**Activer / désactiver un indicateur** :
1. Clic sur le switch
2. La bannière "Modifications non commitées" apparaît
3. Commit comme pour les bornes années

**Effet** : l'indicateur **n'apparaît plus dans l'app** `index.html` (menu déroulant), mais **les données restent dans la DB**. C'est un toggle d'affichage, pas de stockage.

Pour vraiment arrêter de collecter un indicateur (ne plus le récupérer depuis l'API), il faudrait modifier `etl/config.py` (`INDICATORS_WB`, `INDICATORS_OWID`, etc.). C'est rare et délicat — voir [§9.4](#94-désactiver-une-source-définitivement).

### 5.5 Workflow complet d'une modification

1. Tu modifies (curseur ou toggle)
2. Tu cliques **Commit + (option) relance pipeline**
3. Confirmation avec message de commit synthétique
4. Commit envoyé à GitHub (visible immédiatement sur github.com)
5. Popup "Relancer le pipeline maintenant ?"
   - **Oui** → run lancé, attente 5-10 min, DB mise à jour
   - **Non** → la modif sera prise en compte au prochain run auto (lundi 3h UTC)

> **Demande à une IA d'approfondir cette section :**
> > Lis la section "Onglet Pilotage DB" de NOTICE_ADMIN.md de GÉOPOL. Explique-moi la différence entre changer les bornes années (etl_config.json) et activer/désactiver un indicateur (config.json). Pourquoi sont-ils dans deux fichiers différents ?

---

## 6. Onglet Couverture

Identifier les trous dans les données.

### 6.1 Lecture du tableau

Une ligne par indicateur. Colonnes :

| Colonne | Sens |
|---|---|
| **Indicateur** | Nom et code |
| **Pays** | Nombre de pays avec ≥ 1 donnée / pays du périmètre |
| **Années** | Plage temporelle couverte |
| **Couverture** | Barre + 2 métriques : % pays et % cellules (ou densité bilatérale pour flux) |
| **Lignes** | Volume brut dans la DB |

**Codes couleur** de la barre :
- Vert : couverture > 70%
- Orange : 40-70%
- Rouge : < 40%

Les indicateurs **inactifs** (toggle off dans config.json) sont atténués mais affichés.

### 6.2 Filtres

| Filtre | Effet |
|---|---|
| **Catégorie** | Démographie, économie, militaire... |
| **Table** | `identite` ou `flux` |
| **Zone** | Tous pays / continent / organisation (OTAN, UE, BRICS...) |
| **Recherche** | Par nom ou code |

⚠️ **Le filtre "Zone" change le dénominateur** : si tu sélectionnes OTAN, la couverture se calcule sur les ~32 pays OTAN, pas sur les 217 pays totaux. C'est utile pour évaluer la fiabilité régionale d'un indicateur.

### 6.3 Drill-down (clic sur une ligne)

Modal qui montre :
- **Pays manquants** (étiquettes rouges, groupés par continent)
- **Pays présents** (étiquettes grises)
- Bouton **⬇ Exporter en CSV**

Le CSV exporté contient :
```
indicator,country_iso3,status
brevets_deposes,FRA,present
brevets_deposes,VEN,absent
...
```

**Usage typique** :
1. Tu repères un indicateur mal couvert (ex: alignement_onu, 12% de couverture)
2. Tu cliques → tu vois les 200+ pays manquants
3. Tu exportes le CSV
4. Tu colles ce CSV dans une conversation IA avec un prompt du type : "Pour chacun de ces 200 pays, trouve la donnée alignement_onu 2024 dans les votes ONU et formate-la au format GÉOPOL"
5. Tu déposes le CSV résultat dans l'onglet **Imports → Manuel assisté IA**

> **Demande à une IA d'approfondir cette section :**
> > Lis la section "Onglet Couverture" de NOTICE_ADMIN.md de GÉOPOL. Explique-moi comment utiliser cet onglet pour identifier les données manquantes prioritaires, et propose-moi une méthode pour décider quelles données aller chercher en premier.

---

## 7. Onglet Imports

Le centre de gestion des trois mécanismes d'import.

### 7.1 Sous-onglet "Automatique"

Vue récapitulative en lecture seule. Pas d'action ici — c'est juste un résumé de ce que fait le pipeline tous les lundis.

Pour déclencher un run → voir [§4.2](#42-déclencher-un-run-manuel).

### 7.2 Sous-onglet "Semi-automatique"

Pour les sources qui ne se téléchargent pas via API : SIPRI, Energy Institute, UNDESA, Lowy, ZEE, UNESCO.

**Workflow** :
1. Tu télécharges manuellement le fichier depuis la source (ex: SIPRI Trade Register CSV depuis sipri.org)
2. Tu le déposes dans la zone correspondante (drag & drop ou clic)
3. Le fichier est commité dans `etl/sources/uploads/<nom_attendu>`
4. Au prochain run du pipeline, le parser Python le lit et l'intègre à la DB

**Limites actuelles** :
- Seul **SIPRI** a un parser Python fonctionnel (`sipri.py`)
- Les autres sources peuvent être déposées mais ne seront pas traitées tant que leur parser n'est pas codé
- Limite de taille : **25 Mo par fichier** (limite GitHub API)

### 7.3 Sous-onglet "Manuel assisté IA"

Pour les données qu'aucune API ni source CSV publique ne fournit (ex: alignement diplomatique, bases militaires, projections...).

**Les deux prompts** sont affichés en haut, copiables d'un clic :
- **Prompt identite** : pour indicateurs par pays (`country_iso3, indicator, year, value, unit, source, subcategory`)
- **Prompt flux** : pour indicateurs bilatéraux (`country_from, country_to, indicator, year, value, unit, source, subcategory_1, subcategory_2, subcategory_3`)

**Workflow** :
1. Copier le prompt approprié (identite ou flux)
2. L'envoyer à une IA (ChatGPT, Claude, Gemini) en y joignant ton fichier source (PDF, Excel, page web copiée)
3. L'IA renvoie un CSV au format GÉOPOL
4. Tu déposes ce CSV dans la dropzone
5. L'admin **valide le format** côté navigateur (ISO3, années, valeurs numériques)
6. L'admin **détecte les conflits** avec la DB existante (combien de lignes vont écraser des données automatiques)
7. Tu commits via le modal
8. Le fichier est dans `uploads/manuel/YYYYMMDD_HHMMSS_<nom>.csv`
9. Au prochain run, `manuel.py` lit le fichier et insère les données

**Risque de conflit — règle d'or** :
- Si tu ajoutes des projections (années > 2024) sur un indicateur existant (ex: `pib_usd` 2025-2030) → **aucun risque**, les années ne se chevauchent pas
- Si tu écris sur des années déjà couvertes (ex: `pib_usd` 2020 alors que la Banque Mondiale l'a déjà) → **collision**, le dernier exécuté gagne (ici, ton manuel écrase la BM car `manuel.py` tourne après dans `run_etl.py`)
- En cas de doute : utiliser un nom d'indicateur dédié (ex: `pib_usd_dgtresor` au lieu de `pib_usd`)

> **Demande à une IA d'approfondir cette section :**
> > Lis la section "Onglet Imports" de NOTICE_ADMIN.md de GÉOPOL. Explique-moi les trois mécanismes d'import et donne-moi un exemple concret pour chacun. Explique aussi pourquoi le manuel IA peut écraser des données et comment l'éviter.

---

## 8. Outils legacy

Onglets historiques de la première version d'admin. Restent disponibles pour le debug local.

### 8.1 Import CSV local

Charger un CSV directement dans une DB SQLite chargée en local (bouton "Changer" dans le header).
Utilité actuelle : tester un parsing avant de déposer le fichier en semi-auto.

### 8.2 Journal

Historique des imports faits via l'onglet Import CSV local. Vide si tu n'utilises pas l'import local.

### 8.3 Statistiques

Compteurs basiques sur la DB chargée. Vide en mode R2 (pas de table journal_imports).

### 8.4 Migrations

Évolutions du schéma SQL (création de tables, ajout de colonnes). À ne toucher que si tu sais ce que tu fais.

**Tu peux ignorer ces 4 onglets dans l'usage courant.**

---

## 9. Ajouter un indicateur — procédures

### 9.1 Vue d'ensemble : trois types d'ajout

| Type | Source | Effort | Procédure |
|---|---|---|---|
| **Automatique** | API publique (Banque Mondiale, OWID, etc.) | Modif Python | [§9.2](#92-ajouter-un-indicateur-automatique) |
| **Semi-automatique** | CSV annuel téléchargeable manuellement | Modif Python + dépôt CSV | [§9.3](#93-ajouter-une-source-semi-automatique) |
| **Manuel assisté IA** | Donnée ponctuelle ou prospective | Aucune modif Python | [§9.5](#95-ajouter-une-donnée-manuelle-assistée-ia) |

### 9.2 Ajouter un indicateur automatique

**Quand l'utiliser :** une API publique fournit la donnée et tu veux l'inclure dans le pipeline automatique.

**Exemples** : tu veux ajouter "espérance de vie" (Banque Mondiale) ou "indice de démocratie" (OWID).

**Étapes globales :**
1. Identifier la source et le code de l'indicateur (ex: `SP.DYN.LE00.IN` pour la Banque Mondiale)
2. Modifier `etl/config.py` pour ajouter l'indicateur au dictionnaire approprié
3. (Si nouvelle source) créer un nouveau parser dans `etl/sources/`
4. Modifier `run_etl.py` pour intégrer la nouvelle source au PIPELINE
5. Ajouter l'indicateur à `config.json` pour qu'il apparaisse dans l'app
6. Commiter et relancer le pipeline

**Le plus simple : utiliser le prompt en [§12.1](#121-prompt-pour-ajouter-un-indicateur-automatique)** qui te génère le code prêt à coller.

### 9.3 Ajouter une source semi-automatique

**Quand l'utiliser :** la donnée existe sous forme de CSV/Excel téléchargeable annuellement (pas d'API).

**Exemples** : Energy Institute (hydrocarbures), UNDESA migrants.

**Étapes globales :**
1. Télécharger le fichier source manuellement
2. Créer un parser Python dans `etl/sources/<source>.py` (modèle : `sipri.py`)
3. Ajouter la source à `etl/sources/SOURCES_MANUELLES` dans `config.py`
4. Ajouter le parser au PIPELINE dans `run_etl.py`
5. Ajouter la source à la liste `SOURCES_SEMI` dans `admin.html` (pour l'affichage)
6. Déposer le fichier via l'onglet **Imports → Semi-automatique**
7. Relancer le pipeline

**Le plus simple : utiliser le prompt en [§12.2](#122-prompt-pour-ajouter-un-parser-semi-automatique)** qui te génère le parser complet.

### 9.4 Désactiver une source définitivement

Si tu veux qu'une source automatique **arrête d'être récupérée** (et pas juste cacher dans l'app) :

1. Éditer `run_etl.py`
2. Commenter le bloc correspondant dans la liste `PIPELINE`
3. Commiter
4. Au prochain run, la source ne tournera plus

Les données déjà présentes restent dans la DB jusqu'au prochain VACUUM (ou tu modifies les bornes années pour les exclure).

### 9.5 Ajouter une donnée manuelle assistée IA

**C'est le cas le plus simple — aucune modification Python.**

**Workflow détaillé :**

1. **Identifier la donnée à collecter**
   - Vérifier dans l'onglet **Couverture** quels pays/années manquent
   - Exporter le CSV des pays manquants si utile

2. **Trouver la source**
   - PDF officiel (ONU, FMI, gouvernement)
   - Site web institutionnel
   - Page Wikipedia avec tableau (à vérifier soigneusement)

3. **Faire transformer par une IA**
   - Onglet **Imports → Manuel assisté IA** → copier le prompt approprié
   - Coller dans ChatGPT / Claude / autre
   - Y joindre le PDF ou les données brutes
   - L'IA renvoie un CSV au bon format

4. **Vérifier le CSV avant dépôt**
   - Ouvrir dans un éditeur de texte
   - Vérifier l'en-tête (7 colonnes pour identite, 10 pour flux)
   - Vérifier quelques lignes au hasard

5. **Déposer dans admin**
   - Drag & drop dans la dropzone
   - Lire attentivement le modal de validation :
     - Format détecté ?
     - Combien de lignes valides ?
     - Combien de conflits avec données existantes ?
   - Si OK → **Commit sur GitHub**

6. **Lancer le run**
   - Aller sur Suivi ETL → Déclencher un run manuel
   - Attendre la fin
   - Vérifier dans Couverture que la couverture de l'indicateur a augmenté

> **Demande à une IA d'approfondir cette section :**
> > Lis la section "Ajouter un indicateur" de NOTICE_ADMIN.md de GÉOPOL. Guide-moi pas à pas, en dialogue, pour ajouter un nouvel indicateur. Demande-moi d'abord quel type d'ajout je veux faire (auto / semi / manuel), puis adapte tes instructions.

---

## 10. Dépannage

### 10.1 Le badge DB affiche "Échec chargement R2"

**Cause typique** : tu as ouvert admin.html en `file:///` (double-clic local).
**Solution** : utiliser https://ahk1515.github.io/geopol/admin.html

**Cause moins fréquente** : R2 indisponible (très rare).
**Solution** : recharger la page après quelques minutes.

### 10.2 Le badge auth refuse mon PAT

**Cause** : token mal copié, permissions manquantes, ou expiration.
**Solution** :
1. Vérifier sur https://github.com/settings/tokens que le PAT est actif
2. Vérifier les permissions : Actions = R/W, Contents = R/W
3. Regénérer un PAT et le recoller

### 10.3 Un commit reste bloqué sur "Commit en cours…"

**Cause typique** : F12 → Console montre une erreur 401/403 → permissions insuffisantes.
**Solution** : vérifier les permissions du PAT.

**Cause typique** : F12 → Console montre une erreur 422 → conflit (par exemple SHA obsolète).
**Solution** : recharger admin (Ctrl+R) et retenter.

**Si bloqué sans message d'erreur** : recharger (Ctrl+Shift+R pour vider le cache).

### 10.4 Le run pipeline échoue (statut ✕)

**Cause typique** : modification récente du code Python avec un bug.
**Solution** :
1. Clic sur le ↗ de la ligne du run dans l'historique → ouvre GitHub Actions
2. Cliquer sur le job en échec → voir les logs
3. Identifier la ligne d'erreur

**Cause fréquente après modif** : import manquant dans `run_etl.py`.
Exemple : tu as supprimé `manuel.py` mais l'import est resté → l'orchestrateur plante.

### 10.5 L'onglet Couverture montre 0% partout

**Cause** : la DB n'est pas chargée en mémoire.
**Solution** : retourner sur Suivi ETL et attendre que le badge DB passe au vert.

### 10.6 Le tableau des sources est vide

**Cause** : `status.json` n'est pas accessible sur R2.
**Solution** : vérifier https://pub-710d496c94c74cb3837b8229bc8f4410.r2.dev/status.json directement dans le navigateur — il doit s'afficher du JSON.

### 10.7 Comment révoquer un PAT en urgence

Si tu penses que ton PAT a fuité :
1. https://github.com/settings/tokens
2. Trouver le token `geopol-admin`
3. **Delete** ou **Revoke**

L'admin se bloquera côté actions (les lectures publiques fonctionneront toujours). Tu pourras créer un nouveau PAT et le recoller.

> **Demande à une IA d'approfondir cette section :**
> > Lis la section "Dépannage" de NOTICE_ADMIN.md de GÉOPOL. J'ai un problème spécifique : [DÉCRIRE LE PROBLÈME]. Aide-moi à diagnostiquer en me posant des questions précises et en me proposant des actions.

---

## 11. Annexe — Anatomie du système

### 11.1 Flux des données

```
       ┌─────────────────────┐
       │    Sources externes  │
       │  WB · OWID · UNHCR  │
       │     · SIPRI · ...    │
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
   │  ↑ lit status.json + DB depuis R2│
   │  ↓ commits sur GitHub via PAT    │
   │  ↓ déclenche workflow_dispatch   │
   └─────────────────────────────────┘
```

### 11.2 Fichiers clés du repo

| Fichier | Rôle | Modifié par |
|---|---|---|
| `admin.html` | UI d'administration | Manuellement / Claude |
| `index.html` | App publique | Manuellement / Claude |
| `config.json` | Indicateurs affichés (label, unité, actif) | Admin (toggles) |
| `etl_config.json` | Bornes années, pays | Admin (curseurs) |
| `referentiel.json` | Pays, organisations, attributs | Manuellement |
| `run_etl.py` | Orchestrateur ETL | Manuellement |
| `etl/config.py` | Config technique ETL (codes API, etc.) | Manuellement |
| `etl/sources/*.py` | Parsers par source | Manuellement |
| `etl/sources/uploads/` | Dépôt CSV semi-auto | Admin (upload) |
| `uploads/manuel/` | Dépôt CSV manuel IA | Admin (upload) |
| `.github/workflows/etl.yml` | Définition GitHub Actions | Manuellement |

### 11.3 Sentinelles dans la table `flux`

Pour les flux non-bilatéraux entre pays :

| Sentinelle | Sens |
|---|---|
| `__multilateral__` | Créditeur institutionnel (FMI, Banque Mondiale...) |
| `__private__` | Créditeur privé |
| `__intra__` | Flux interne à un groupe (mode groupe dans l'app) |

### 11.4 Schéma SQL

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

---

## 12. Annexe — Prompts IA prêts à l'emploi

### 12.1 Prompt pour ajouter un indicateur automatique

Copier-coller dans une conversation IA, en remplaçant les `[CROCHETS]` :

```
Je travaille sur le projet GÉOPOL (https://github.com/ahk1515/geopol),
une application de visualisation géopolitique avec :
- Pipeline ETL Python qui tourne sur GitHub Actions
- DB SQLite stockée sur Cloudflare R2
- App web qui lit la DB via sql.js

Je veux ajouter un nouvel indicateur automatique :
- Nom interne (snake_case) : [ex: esperance_vie]
- Label affiché : [ex: Espérance de vie à la naissance]
- Source : [ex: Banque Mondiale]
- Code source : [ex: SP.DYN.LE00.IN pour la Banque Mondiale]
- Catégorie : [ex: demographie]
- Unité brute : [ex: ans]
- Unité d'affichage : [ex: ans]
- Agrégation pour mode groupe : [ex: mean] (sum ou mean)
- Table : [identite ou flux]

L'architecture actuelle utilise :
- etl/config.py : dictionnaires INDICATORS_WB, INDICATORS_OWID, INDICATORS_CONSTRUITS, et leurs META associés
- etl/sources/banque_mondiale.py et etl/sources/owid.py : parsers existants qui itèrent sur ces dictionnaires
- config.json : liste des indicateurs affichés dans l'app (avec un champ "actif")

Génère-moi :
1. Le bloc à ajouter dans etl/config.py (dans INDICATORS_WB ou INDICATORS_OWID, et dans le META associé)
2. Le bloc JSON à ajouter dans config.json (en respectant le format des autres entrées)
3. Les instructions pour vérifier que ça fonctionne (lancement local optionnel, déclenchement du pipeline depuis admin)

Ne propose PAS de modifier d'autres fichiers (run_etl.py, parsers existants) sauf si strictement nécessaire — l'indicateur doit s'intégrer automatiquement dans les boucles existantes.

Sois précis sur où coller chaque bloc (numéro de ligne approximatif ou contexte).
```

### 12.2 Prompt pour ajouter un parser semi-automatique

Quand tu as un nouveau fichier CSV/Excel récurrent (annuel) qui n'a pas d'API.

```
Je travaille sur le projet GÉOPOL (https://github.com/ahk1515/geopol).

Je veux ajouter un parser pour une nouvelle source semi-automatique :
- Nom de la source : [ex: Energy Institute]
- ID technique (snake_case) : [ex: energy]
- Fichier d'entrée attendu : [ex: energy-data.xlsx]
- Emplacement attendu : etl/sources/uploads/[nom]
- Indicateurs à extraire :
  * [ex: production_petrole, unit=barils/jour, table=identite]
  * [ex: production_gaz, unit=mtep, table=identite]
  * [ajouter autant que nécessaire]
- Format du fichier source : [DÉCRIRE LE FORMAT — colonnes attendues, en-tête à quelle ligne, encodage]
- Particularités : [ex: les noms de pays sont en anglais SIPRI-like, à mapper en ISO3]

L'architecture actuelle :
- Les parsers sont dans etl/sources/*.py
- Modèle de référence à suivre : etl/sources/sipri.py (semi-auto, le plus proche)
  - Lit un fichier depuis etl/sources/uploads/
  - Parse en respectant la règle "valeur absente → on n'insère pas"
  - Utilise INSERT OR REPLACE pour gérer les révisions
  - Source = nom propre de la source (ex: "Energy Institute")
  - Retourne le nombre de lignes insérées via une fonction run()
- run_etl.py contient une liste PIPELINE qui orchestre les sources
- etl/config.py définit ANNEE_DEBUT et ANNEE_FIN

Schéma de la table identite :
  country_iso3 TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT, subcategory TEXT,
  PRIMARY KEY (country_iso3, indicator, year)

Schéma de la table flux :
  country_from TEXT, country_to TEXT, indicator TEXT, year INTEGER,
  value REAL, unit TEXT, source TEXT,
  subcategory_1 TEXT, subcategory_2 TEXT, subcategory_3 TEXT,
  PRIMARY KEY (country_from, country_to, indicator, year, subcategory_1)

Pour les pays sans correspondance ISO3, ignorer la ligne (transparence > complétude).
Pour openpyxl/pandas/xlrd, indique la dépendance à ajouter à requirements.txt si nécessaire.

Génère-moi :
1. Le fichier complet etl/sources/[id].py prêt à coller dans le repo
2. L'ajout à faire dans run_etl.py (5 lignes dans PIPELINE)
3. L'ajout à faire dans la constante SOURCES_SEMI d'admin.html
4. Les ajouts éventuels à config.json pour les nouveaux indicateurs
5. Le test minimal pour vérifier que le parser tourne (avec un fichier d'exemple à 3-5 lignes)

Sois rigoureux : pas d'interpolation, pas d'estimation, pas de valeur par défaut quand la source dit vide. Toute ligne ignorée doit être affichée dans les logs.
```

### 12.3 Prompt pour formatter un CSV manuel (variante des prompts intégrés à admin)

Si les prompts par défaut dans admin ne suffisent pas, utiliser cette variante adaptée :

```
Tu es un expert en transformation de données géopolitiques pour GÉOPOL.

Mission : transformer la donnée que je vais te fournir en CSV au format GÉOPOL strict.

CONTEXTE :
- L'indicateur visé : [NOM_INDICATEUR snake_case, ex: alignement_onu]
- La table cible : [identite OU flux]
- L'unité brute : [ex: %, personnes, USD]
- Le nom de source à inscrire dans la colonne source : [ex: ONU - Vote Assembly 2024]
- L'année concernée : [ex: 2024]

DONNÉE SOURCE :
[COLLER ICI le PDF, le tableau, le texte brut, ou les liens]

FORMAT CIBLE (table identite, 7 colonnes) :
country_iso3,indicator,year,value,unit,source,subcategory

FORMAT CIBLE (table flux, 10 colonnes) :
country_from,country_to,indicator,year,value,unit,source,subcategory_1,subcategory_2,subcategory_3

RÈGLES INVIOLABLES :
1. country_iso3 / country_from / country_to : ISO 3166-1 alpha-3 en MAJUSCULES (FRA, DEU, USA, etc.)
   → Si tu ne trouves pas le code ISO3 d'un pays, signale-le et ignore la ligne
   → Pour les institutions non-étatiques (FMI, Banque Mondiale...), utiliser la sentinelle __multilateral__
   → Pour les acteurs privés, utiliser __private__
2. year : entier 4 chiffres. Exclure < 1980 et > 2050.
3. value : numérique pur. Aucun séparateur de milliers, point décimal anglo-saxon.
   → Si la valeur est absente, manquante, "n/a", "—" : NE PAS INCLURE LA LIGNE
   → Jamais d'interpolation, jamais d'estimation, jamais de 0 par défaut
4. Tous les autres champs : suivre exactement les paramètres ci-dessus
5. Encodage UTF-8 sans BOM

LIVRABLES ATTENDUS :
1. Le CSV final, complet, prêt à copier dans un fichier .csv
2. Une liste séparée des lignes ignorées avec la raison (pays inconnu, valeur manquante, etc.)
3. Une statistique : nb lignes valides, nb lignes ignorées, % de couverture si applicable

Ne mets RIEN d'autre dans le CSV (pas de commentaires, pas d'en-tête additionnelle).
Le premier ligne du CSV doit être l'en-tête, le reste les données.
```

### 12.4 Prompt pour comprendre une partie de cette notice

À utiliser si une section de la notice te semble trop courte ou pas claire :

```
Je consulte le fichier NOTICE_ADMIN.md du projet GÉOPOL.
Le fichier complet est disponible ici : [coller l'URL GitHub raw OU coller le contenu de la notice]

J'aimerais que tu me réexpliques en détail la section "[NOM DE LA SECTION]" en mode pédagogique :
- Vulgarise pour quelqu'un qui n'est pas développeur
- Donne des exemples concrets pour chaque concept
- Anticipe les questions que je vais me poser
- Termine par un mini-quiz (3 questions) pour vérifier que j'ai compris

Si certaines parties dépendent d'autres sections, fais des renvois et explique brièvement
les dépendances. N'invente pas de fonctionnalités qui ne sont pas dans la notice.
```

### 12.5 Prompt pour diagnostiquer un problème

```
J'utilise admin.html du projet GÉOPOL. J'ai un problème :

[DESCRIPTION DU SYMPTÔME — précise ce que tu vois, ce que tu attendais, à quel moment]

Console F12 :
[COLLER les erreurs visibles dans la console JavaScript]

Onglet Network :
[Indiquer les statuts HTTP des requêtes vers api.github.com et r2.dev]

J'ai vérifié :
- [Liste ce que tu as déjà essayé]

Voici la section dépannage de la notice : [coller la section §10 du document]

Aide-moi à diagnostiquer en :
1. Identifiant 2-3 hypothèses probables
2. Me proposant pour chacune une vérification précise à faire
3. Me donnant la solution une fois la cause identifiée

Sois méthodique et ne saute pas d'étape.
```

---

## Maintenance de cette notice

Cette notice est un document vivant. Elle doit être mise à jour quand :
- Une nouvelle fonctionnalité est ajoutée à admin.html
- Une nouvelle source est intégrée au pipeline
- Une procédure change (ex: nouveau type de PAT GitHub)
- Un bug récurrent est identifié et résolu

**Dernière mise à jour** : version initiale post-Étape 4 (admin complet).

---

*Fin de notice. Bonne administration de GÉOPOL.*
