# GÉOPOL — Tâches à faire

## Admin.html — Vision complète

### Onglet 1 — Suivi ETL
- [ ] Statut de chaque source (date dernière MAJ, nb lignes, succès/échec)
- [ ] Logs des runs GitHub Actions
- [ ] Déclenchement manuel d'un run

### Onglet 2 — Imports
- [ ] **Automatique** (API + script Python)
  - Activation/désactivation par source
  - Configuration fréquence
- [ ] **Semi-automatique** (CSV + parser Python)
  - Dépôt de fichier dans admin
  - Parser dédié par source (SIPRI, Energy Institute, UNDESA, Lowy...)
  - Mise à jour régulière (annuelle, biennale)
- [ ] **Manuel assisté IA** (données ponctuelles)
  - Template CSV standard à fournir à l'IA
  - Import du fichier formaté
  - Pas de parser dédié — format cible standardisé

### Onglet 3 — Pilotage DB
- [ ] Curseur antériorité par indicateur (contrôle avant import via etl_config.json)
- [ ] Nettoyage DB après import (DELETE ciblé par indicateur/année)
  - Couper l'antériorité (ex: garder seulement 2000→2024)
  - Couper les projections (supprimer années futures)
  - Supprimer un indicateur entier
- [ ] Affichage taille actuelle DB + estimation après modification
- [ ] Bouton "Appliquer + Redéployer sur R2"
- [ ] Note : opération irréversible sur DB locale — relancer pipeline pour récupérer

### Onglet 4 — Couverture
- [ ] Matrice indicateur × nb pays × années couvertes × % couverture
- [ ] Au clic : liste des pays manquants par indicateur
- [ ] Objectif : identifier les trous et évaluer la fiabilité de la DB

---

## ETL — Sources manquantes

### Automatiques
- [ ] Comtrade — créer compte sur comtradeplus.un.org + ajouter clé dans secrets GitHub

### Semi-automatiques (fichiers à récupérer)
- [ ] SIPRI — armement export/import bilatéral (Excel annuel)
- [ ] Energy Institute — hydrocarbures (Excel annuel)
- [ ] UNDESA — migrants (fichier biennal)
- [ ] Lowy Institute — représentations diplomatiques (fichier annuel)
- [ ] ZEE — Flanders Marine (données statiques)
- [ ] UNESCO étudiants — inspecter OPRI.zip avant de coder

### Manuels assistés IA
- [ ] Définir template CSV standard (aligné schéma identite/flux)
- [ ] Alignement ONU, bases militaires, langue commune, représentations nationales

---

## Index.html
- [ ] Versionner l'URL du fetch DB de manière plus propre (numéro de version fixe plutôt que Date.now())

## Notice
- [ ] Compléter le PDF avec les procédures ETL
- [ ] Ajouter procédure de vidage cache navigateur
- [ ] Documenter les trois types d'import
