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
  - Dépôt de fichier dans admin → upload sur R2 dossier `uploads/`
  - GitHub Actions détecte et télécharge le fichier depuis R2
  - Parser dédié par source (SIPRI, Energy Institute, UNDESA, Lowy...)
  - Mise à jour régulière (annuelle, biennale)
  - Sources prêtes : SIPRI (sipri.py validé — 6675 lignes)
- [ ] **Manuel assisté IA** (données ponctuelles)
  - Template CSV standard à fournir à l'IA (prompts_transformation_csv.md)
  - Import du fichier formaté via admin → R2 → GitHub Actions
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

### Semi-automatiques (parsers prêts ou à coder)
- [x] SIPRI — parser sipri.py validé (6675 lignes) — en attente intégration admin
- [ ] Energy Institute — hydrocarbures (Excel annuel) — parser à coder
- [ ] UNDESA — migrants (fichier biennal) — parser à coder
- [ ] Lowy Institute — représentations diplomatiques — parser à coder
- [ ] ZEE — Flanders Marine (données statiques) — parser à coder
- [ ] UNESCO étudiants — inspecter OPRI.zip avant de coder

### Manuels assistés IA
- [x] Template CSV standard défini (prompts_transformation_csv.md)
- [ ] Alignement ONU, bases militaires, langue commune, représentations nationales

---

## Architecture semi-automatique (à implémenter dans admin)
- Dépôt fichier dans admin → upload R2 dossier `uploads/`
- GitHub Actions télécharge depuis R2 avant parsing
- Un parser Python dédié par source dans `etl/sources/`

---

## Index.html
- [ ] Versionner l'URL du fetch DB de manière plus propre

## Notice
- [ ] Compléter le PDF avec les procédures ETL
- [ ] Ajouter procédure de vidage cache navigateur
- [ ] Documenter les trois types d'import
