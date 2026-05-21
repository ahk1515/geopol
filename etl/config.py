# =============================================================
# GÉOPOL — Configuration centrale de l'ETL
# Ce fichier est lu par tous les scripts ETL.
# Les paramètres marqués ADMIN peuvent être modifiés depuis admin.html
# =============================================================

import json
import os

# -------------------------------------------------------------
# PARAMÈTRES GÉNÉRAUX (ADMIN)
# -------------------------------------------------------------
ANNEE_DEBUT = 2000       # Année de départ de l'historique
ANNEE_FIN   = 2024       # Année de fin (incluse)
PAYS        = "tous"     # "tous" ou liste ISO3 ex: ["FRA","DEU","USA"]

# -------------------------------------------------------------
# CHEMINS
# -------------------------------------------------------------
DIR_ETL     = os.path.dirname(os.path.abspath(__file__))
DIR_ROOT    = os.path.dirname(DIR_ETL)
PATH_DB     = os.path.join(DIR_ROOT, "geopolitique.db")
PATH_STATUS = os.path.join(DIR_ROOT, "status.json")
PATH_CONFIG = os.path.join(DIR_ROOT, "etl_config.json")

# -------------------------------------------------------------
# CHARGEMENT CONFIG ADMIN (si etl_config.json existe)
# Permet à admin.html de surcharger les valeurs par défaut
# -------------------------------------------------------------
def load_admin_config():
    if os.path.exists(PATH_CONFIG):
        with open(PATH_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        global ANNEE_DEBUT, ANNEE_FIN, PAYS
        ANNEE_DEBUT = cfg.get("annee_debut", ANNEE_DEBUT)
        ANNEE_FIN   = cfg.get("annee_fin",   ANNEE_FIN)
        PAYS        = cfg.get("pays",         PAYS)

load_admin_config()

# -------------------------------------------------------------
# INDICATEURS BANQUE MONDIALE
# format : { indicator_interne : code_WB }
# -------------------------------------------------------------
INDICATORS_WB = {
    "population":          "SP.POP.TOTL",
    "fecondite":           "SP.DYN.TFRT.IN",
    "pib_usd":             "NY.GDP.MKTP.CD",
    "pib_par_hab":         "NY.GDP.PCAP.CD",
    "reserve_change_or":   "FI.RES.TOTL.CD",
    "ide_in":              "BX.KLT.DINV.CD.WD",
    "ide_out":             "BM.KLT.DINV.WD.CD",
    "terres_arables":      "AG.LND.ARBL.HA",
    "land_area":           "AG.LND.TOTL.K2",
    "budget_defense_pib":  "MS.MIL.XPND.GD.ZS",
    "depense_rd_pib":      "GB.XPD.RSDV.GD.ZS",
    "brevets_deposes":     "IP.PAT.RESD",
}

# Métadonnées associées : unité, unité d'affichage, agrégation
WB_META = {
    "population":          {"unit": "hab",       "unit_display": "M hab",    "aggregation": "sum"},
    "fecondite":           {"unit": "enfants/femme", "unit_display": "enfants/femme", "aggregation": "mean"},
    "pib_usd":             {"unit": "USD",        "unit_display": "Mrd USD",  "aggregation": "sum"},
    "pib_par_hab":         {"unit": "USD",        "unit_display": "USD",      "aggregation": "mean"},
    "reserve_change_or":   {"unit": "USD",        "unit_display": "Mrd USD",  "aggregation": "sum"},
    "ide_in":              {"unit": "USD",        "unit_display": "Mrd USD",  "aggregation": "sum"},
    "ide_out":             {"unit": "USD",        "unit_display": "Mrd USD",  "aggregation": "sum"},
    "terres_arables":      {"unit": "ha",         "unit_display": "M ha",     "aggregation": "sum"},
    "land_area":           {"unit": "km2",        "unit_display": "km²",      "aggregation": "sum"},
    "budget_defense_pib":  {"unit": "%",          "unit_display": "%",        "aggregation": "mean"},
    "depense_rd_pib":      {"unit": "%",          "unit_display": "%",        "aggregation": "mean"},
    "brevets_deposes":     {"unit": "brevets",    "unit_display": "brevets",  "aggregation": "sum"},
}

# -------------------------------------------------------------
# INDICATEURS OWID
# format : { indicator_interne : nom_colonne_dans_csv_owid }
# -------------------------------------------------------------
INDICATORS_OWID = {
    "age_median":          "median_age",
    "volume_armee":        "armed_forces_personnel",
    "violent_death":       "death_rate_from_conflict",
    "idps_securitaire":    "internally_displaced_conflict",
    "idps_climatique":     "internally_displaced_disasters",
}

OWID_META = {
    "age_median":          {"unit": "ans",       "unit_display": "ans",      "aggregation": "mean"},
    "volume_armee":        {"unit": "personnes", "unit_display": "personnes","aggregation": "sum"},
    "violent_death":       {"unit": "personnes", "unit_display": "personnes","aggregation": "sum"},
    "idps_securitaire":    {"unit": "personnes", "unit_display": "personnes","aggregation": "sum"},
    "idps_climatique":     {"unit": "personnes", "unit_display": "personnes","aggregation": "sum"},
}

# -------------------------------------------------------------
# INDICATEURS CONSTRUITS
# Calculés après tous les imports
# format : { indicator_interne : { formule, dépendances, table, unit... } }
# -------------------------------------------------------------
INDICATORS_CONSTRUITS = {
    "export_pct_pib": {
        "label":        "Export % PIB",
        "table":        "flux",
        "numerateur":   "export_commercial",
        "denominateur": "pib_usd",
        "operation":    "ratio_pct",
        "unit":         "%",
        "unit_display": "%",
    },
    "import_pct_pib": {
        "label":        "Import % PIB",
        "table":        "flux",
        "numerateur":   "import_commercial",
        "denominateur": "pib_usd",
        "operation":    "ratio_pct",
        "unit":         "%",
        "unit_display": "%",
    },
    "balance_commerciale": {
        "label":        "Balance commerciale",
        "table":        "flux",
        "composantes":  ["export_commercial", "import_commercial"],
        "operation":    "difference",
        "unit":         "USD",
        "unit_display": "Mrd USD",
    },
    "dette_pct_pib": {
        "label":        "Dette % PIB",
        "table":        "identite",
        "numerateur":   "dette_exterieure",
        "denominateur": "pib_usd",
        "operation":    "ratio_pct",
        "unit":         "%",
        "unit_display": "%",
    },
    "densite": {
        "label":        "Densité",
        "table":        "identite",
        "numerateur":   "population",
        "denominateur": "land_area",
        "operation":    "ratio",
        "unit":         "hab/km²",
        "unit_display": "hab/km²",
    },
}

# -------------------------------------------------------------
# SOURCES MANUELLES (référence pour admin.html)
# -------------------------------------------------------------
SOURCES_MANUELLES = [
    {"id": "sipri",        "label": "SIPRI — Armement",              "frequence": "annuelle"},
    {"id": "energy",       "label": "Energy Institute — Hydrocarbures","frequence": "annuelle"},
    {"id": "undesa",       "label": "UNDESA — Migrants",             "frequence": "biennale"},
    {"id": "lowy",         "label": "Lowy Institute — Représentations","frequence": "annuelle"},
    {"id": "zee",          "label": "Flanders Marine — ZEE",         "frequence": "statique"},
    {"id": "universitaire","label": "Données universitaires",        "frequence": "ponctuel"},
]
