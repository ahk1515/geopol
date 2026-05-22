# GÉOPOL — Prompts de transformation CSV

## Utilisation
Ces prompts sont destinés à transformer n'importe quel fichier CSV source
vers le format cible de la DB GÉOPOL, avant import dans admin.
Fournir le prompt + le fichier CSV à l'IA de ton choix.

---

## PROMPT 1 — Table `identite`
*(indicateurs par pays, sans notion de flux bilatéral)*

```
Tu es un expert en transformation de données géopolitiques.
Je te fournis un fichier CSV source. Tu dois le transformer vers
le format cible suivant, sans inventer de données manquantes.

FORMAT CIBLE (CSV, séparateur virgule, encodage UTF-8) :
country_iso3,indicator,year,value,unit,source,subcategory

RÈGLES STRICTES :
1. country_iso3 : code ISO 3166-1 alpha-3 en majuscules (ex: FRA, DEU, USA)
   → Si le pays est absent de la norme ISO3, laisse la ligne vide et signale-le
2. indicator : nom snake_case en minuscules, sans accents (ex: population, pib_usd)
   → Utilise ce nom exact : [INDIQUE ICI LE NOM D'INDICATEUR GÉOPOL]
3. year : année en entier 4 chiffres (ex: 2023)
   → Exclure les années avant 2000 et après 2024
4. value : valeur numérique pure, sans unité, sans séparateur de milliers
   → Si la valeur est absente ou non numérique → ne pas inclure la ligne
5. unit : unité brute de la donnée (ex: USD, hab, %, ans)
6. source : nom exact de la source (ex: SIPRI, Energy Institute)
7. subcategory : sous-catégorie si pertinent, sinon laisser vide

IMPORTANT :
- Ne jamais interpoler ou estimer une valeur manquante
- Ne jamais arrondir sans me le signaler
- Signaler toutes les lignes ignorées et pourquoi
- Produire uniquement le CSV final, sans commentaires dans le fichier

Voici le fichier source :
[COLLE ICI TON FICHIER CSV]
```

---

## PROMPT 2 — Table `flux`
*(indicateurs bilatéraux entre deux pays)*

```
Tu es un expert en transformation de données géopolitiques.
Je te fournis un fichier CSV source. Tu dois le transformer vers
le format cible suivant, sans inventer de données manquantes.

FORMAT CIBLE (CSV, séparateur virgule, encodage UTF-8) :
country_from,country_to,indicator,year,value,unit,source,subcategory_1,subcategory_2,subcategory_3

RÈGLES STRICTES :
1. country_from : code ISO3 du pays source/exportateur/créditeur (ex: FRA)
   → Pour les institutions non-étatiques, utiliser __multilateral__ ou __private__
2. country_to : code ISO3 du pays destination/importateur/débiteur (ex: DEU)
3. indicator : nom snake_case exact — [INDIQUE ICI LE NOM D'INDICATEUR GÉOPOL]
   Valeurs possibles : export_armement, import_armement, refugies,
   etudiants_international, migrants, alignement_onu, base_militaire,
   dette_exterieure, import_commercial, export_commercial
4. year : année entière 4 chiffres
   → Exclure les années avant 2000 et après 2024
5. value : valeur numérique pure, sans unité ni séparateur de milliers
   → Si absente ou non numérique → ne pas inclure la ligne
6. unit : unité brute (ex: USD, personnes, SIPRI_TIV_M, %)
7. source : nom exact de la source
8. subcategory_1 : première sous-catégorie si pertinent (ex: section HS, type créditeur)
9. subcategory_2 : deuxième sous-catégorie si pertinent, sinon laisser vide
10. subcategory_3 : troisième sous-catégorie si pertinent, sinon laisser vide

IMPORTANT :
- Ne jamais interpoler ou estimer une valeur manquante
- Les deux pays doivent être en ISO3 valide — sinon ignorer la ligne
- Signaler toutes les lignes ignorées et pourquoi
- Produire uniquement le CSV final, sans commentaires dans le fichier

Voici le fichier source :
[COLLE ICI TON FICHIER CSV]
```

---

## Notes d'utilisation

- Remplace `[INDIQUE ICI LE NOM D'INDICATEUR GÉOPOL]` par le bon nom
  (voir config.json pour la liste complète)
- Remplace `[COLLE ICI TON FICHIER CSV]` par le contenu brut du fichier
- Vérifie toujours le résultat avant import dans admin
- En cas de doute sur un code ISO3, consulter :
  https://www.iban.com/country-codes
