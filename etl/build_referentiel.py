"""
Génération du référentiel pays GÉOPOL
Combine le fichier Excel existant + données organisations connues
"""

import pandas as pd
import json
import re

# -------------------------------------------------------------
# DONNÉES ORGANISATIONS
# Statuts : membre, observateur, candidat, associé, allié, signataire, ratifié, suspendu
# -------------------------------------------------------------

ORGANISATIONS = {

    # ALLIANCES MILITAIRES
    "OTAN": {
        "nom": "Organisation du Traité de l'Atlantique Nord",
        "membres": ["ALB","BEL","BGR","CAN","HRV","CZE","DNK","EST","FIN","FRA","DEU","GRC","HUN","ISL","ITA","LVA","LTU","LUX","MNE","NLD","MKD","NOR","POL","PRT","ROU","SVK","SVN","ESP","SWE","TUR","GBR","USA"],
        "observateurs": [],
        "candidats": ["UKR","GEO"],
    },
    "OTSC": {
        "nom": "Organisation du Traité de Sécurité Collective",
        "membres": ["ARM","BLR","KAZ","KGZ","RUS","TJK"],
        "observateurs": [],
    },
    "OCS": {
        "nom": "Organisation de Coopération de Shanghai",
        "membres": ["CHN","IND","IRN","KAZ","KGZ","PAK","RUS","TJK","UZB","BLR"],
        "observateurs": ["AFG","MNG","TUR","AZE","ARM","KHM","NPL","SAU","EGY","QAT","ARE","MDV","KWT","UKR","BHR"],
        "candidats": [],
        "associes": ["TUR"],
    },
    "ANZUS": {
        "nom": "Alliance Australie-Nouvelle-Zélande-États-Unis",
        "membres": ["AUS","NZL","USA"],
    },
    "Five Eyes": {
        "nom": "Alliance Five Eyes",
        "membres": ["AUS","CAN","GBR","NZL","USA"],
    },
    "QUAD": {
        "nom": "Dialogue de Sécurité Quadrilatéral",
        "membres": ["AUS","IND","JPN","USA"],
    },
    "AUKUS": {
        "nom": "Alliance AUKUS",
        "membres": ["AUS","GBR","USA"],
    },

    # ORGANISATIONS POLITIQUES GLOBALES
    "G7": {
        "nom": "Groupe des 7",
        "membres": ["CAN","FRA","DEU","ITA","JPN","GBR","USA"],
        "observateurs": ["EUX"],  # UE — observateur institutionnel
    },
    "G20": {
        "nom": "Groupe des 20",
        "membres": ["ARG","AUS","BRA","CAN","CHN","FRA","DEU","IND","IDN","ITA","JPN","KOR","MEX","RUS","SAU","ZAF","TUR","GBR","USA"],
        "observateurs": ["EUX"],
    },
    "Commonwealth": {
        "nom": "Commonwealth des Nations",
        "membres": ["ATG","AUS","BHS","BGD","BRB","BLZ","BWA","BRN","CMR","CAN","CYP","DMA","FJI","GMB","GHA","GRD","GUY","IND","JAM","KEN","KIR","LSO","MWI","MYS","MDV","MLT","MUS","MOZ","NAM","NRU","NZL","NGA","PAK","PNG","RWA","KNA","LCA","VCT","WSM","SLE","SGP","SLB","ZAF","LKA","SWZ","TZA","TON","TTO","TUV","UGA","GBR","VUT","ZMB"],
        "observateurs": ["DZA","BGD","BDI","CMR","RWA","TGO","YEM"],
    },
    "Francophonie": {
        "nom": "Organisation Internationale de la Francophonie",
        "membres": ["ALB","AND","ARM","BEL","BEN","BGR","BFA","BDI","CPV","KHM","CMR","CAF","TCD","COM","COD","COG","CIV","DJI","DMA","EGY","GNQ","FRA","GAB","GRC","GIN","GNB","HTI","LAO","LBN","LUX","MKD","MDG","MLI","MRT","MUS","MDA","MCO","MAR","MOZ","NER","ROU","RWA","STP","SEN","SYC","TGO","TUN","VUT","VNM"],
        "observateurs": ["ARG","AUT","CAN","CYP","CZE","GEO","HUN","IRL","KOR","MEX","MNE","POL","QAT","SVK","SVN","THA","UAE","URY","UKR"],
        "associes": ["GHA","KOS","LVA","MNE","SVK"],
    },
    "CELAC": {
        "nom": "Communauté des États d'Amérique Latine et des Caraïbes",
        "membres": ["ATG","ARG","BHS","BRB","BLZ","BOL","BRA","CHL","COL","CRI","CUB","DMA","DOM","ECU","SLV","GRD","GTM","GUY","HTI","HND","JAM","MEX","NIC","PAN","PRY","PER","KNA","LCA","VCT","SUR","TTO","URY","VEN"],
    },

    # ORGANISATIONS EUROPÉENNES / EURASIENNES
    "UE": {
        "nom": "Union Européenne",
        "membres": ["AUT","BEL","BGR","HRV","CYP","CZE","DNK","EST","FIN","FRA","DEU","GRC","HUN","IRL","ITA","LVA","LTU","LUX","MLT","NLD","POL","PRT","ROU","SVK","SVN","ESP","SWE"],
        "candidats": ["ALB","MKD","MNE","SRB","TUR","UKR","MDA","GEO","BIH","XKX"],
    },
    "CEI": {
        "nom": "Communauté des États Indépendants",
        "membres": ["ARM","AZE","BLR","KAZ","KGZ","MDA","RUS","TJK","UZB"],
        "observateurs": ["AFG","MNG"],
        "associes": ["TKM","UKR"],
    },
    "Conseil Europe": {
        "nom": "Conseil de l'Europe",
        "membres": ["ALB","AND","ARM","AUT","AZE","BEL","BIH","BGR","HRV","CYP","CZE","DNK","EST","FIN","FRA","GEO","DEU","GRC","HUN","ISL","IRL","ITA","LVA","LIE","LTU","LUX","MLT","MDA","MCO","MNE","NLD","MKD","NOR","POL","PRT","ROU","SMR","SRB","SVK","SVN","ESP","SWE","CHE","TUR","UKR","GBR"],
        "observateurs": ["CAN","ISR","JPN","MEX","USA"],
    },

    # ORGANISATIONS AFRICAINES
    "UA": {
        "nom": "Union Africaine",
        "membres": ["DZA","AGO","BEN","BWA","BFA","BDI","CPV","CMR","CAF","TCD","COM","COD","COG","CIV","DJI","EGY","GNQ","ERI","SWZ","ETH","GAB","GMB","GHA","GIN","GNB","KEN","LSO","LBR","LBY","MDG","MWI","MLI","MRT","MUS","MAR","MOZ","NAM","NER","NGA","RWA","STP","SEN","SLE","SOM","ZAF","SSD","SDN","TZA","TGO","TUN","UGA","ZMB","ZWE","SYC"],
        "suspendus": ["BFA","GIN","MLI","SDN","TCD","GAB","NER"],
    },
    "CEDEAO": {
        "nom": "Communauté Économique des États de l'Afrique de l'Ouest",
        "membres": ["BEN","BFA","CPV","CIV","GMB","GHA","GIN","GNB","LBR","MLI","MRT","NER","NGA","SEN","SLE","TGO"],
        "suspendus": ["BFA","GIN","MLI","NER"],
    },
    "CEEAC": {
        "nom": "Communauté Économique des États de l'Afrique Centrale",
        "membres": ["AGO","BDI","CMR","CAF","TCD","COD","COG","GAB","GNQ","RWA","STP"],
    },
    "IGAD": {
        "nom": "Autorité Intergouvernementale pour le Développement",
        "membres": ["DJI","ERI","ETH","KEN","SOM","SSD","SDN","UGA"],
        "observateurs": ["EGY","ITA","EUR","USA","GBR","CHN","FRA"],
    },
    "SADC": {
        "nom": "Communauté de Développement de l'Afrique Australe",
        "membres": ["AGO","BWA","COM","COD","SWZ","LSO","MDG","MWI","MUS","MOZ","NAM","SYC","ZAF","TZA","ZMB","ZWE"],
    },
    "EAC": {
        "nom": "Communauté de l'Afrique de l'Est",
        "membres": ["BDI","COD","KEN","RWA","SOM","SSD","TZA","UGA"],
        "observateurs": ["COM","ERI","ETH","MDG"],
    },
    "COI": {
        "nom": "Commission de l'Océan Indien",
        "membres": ["COM","FRA","MDG","MUS","MYT","SYC","REU"],
        "observateurs": ["MDV","MOZ","TZA","IND","EUX"],
    },
    "UMA": {
        "nom": "Union du Maghreb Arabe",
        "membres": ["DZA","LBY","MAR","MRT","TUN"],
    },
    "CEN-SAD": {
        "nom": "Communauté des États Sahélo-Sahariens",
        "membres": ["BEN","BFA","CAF","TCD","COM","CIV","DJI","EGY","ERI","GMB","GHA","GIN","GNB","LBY","LBR","MLI","MAR","MRT","NER","NGA","SEN","SLE","SOM","SDN","TGO","TUN"],
    },
    "COMESA": {
        "nom": "Marché Commun de l'Afrique Orientale et Australe",
        "membres": ["BDI","COM","COD","DJI","EGY","ERI","ETH","KEN","LBY","MDG","MWI","MUS","RWA","SYC","SOM","SDN","SWZ","TUN","UGA","ZMB","ZWE"],
    },

    # ORGANISATIONS AMÉRICAINES
    "OEA": {
        "nom": "Organisation des États Américains",
        "membres": ["ATG","ARG","BHS","BRB","BLZ","BOL","BRA","CAN","CHL","COL","CRI","CUB","DMA","DOM","ECU","SLV","GRD","GTM","GUY","HTI","HND","JAM","MEX","NIC","PAN","PRY","PER","KNA","LCA","VCT","SUR","TTO","USA","URY","VEN"],
        "suspendus": ["CUB"],
        "observateurs": ["ARG","BRA","CHL","COL"],
    },
    "MERCOSUR": {
        "nom": "Marché Commun du Sud",
        "membres": ["ARG","BRA","PRY","URY"],
        "associes": ["BOL","CHL","COL","ECU","GUY","PER","SUR"],
        "observateurs": ["NZL","MEX"],
        "suspendus": ["VEN"],
    },
    "ALBA": {
        "nom": "Alliance Bolivarienne pour les Peuples de Notre Amérique",
        "membres": ["ATG","BOL","CUB","DMA","GRD","NIC","KNA","LCA","VCT","VEN"],
    },
    "CARICOM": {
        "nom": "Communauté des Caraïbes",
        "membres": ["ATG","BHS","BRB","BLZ","DMA","GRD","GUY","HTI","JAM","MNT","KNA","LCA","SUR","TTO","VCT"],
        "observateurs": ["ABW","BMU","BES","CYM","CUW","HTI","MEX","PAN","TCA","VEN"],
    },
    "ACEUM": {
        "nom": "Accord Canada-États-Unis-Mexique",
        "membres": ["CAN","MEX","USA"],
    },

    # ORGANISATIONS ASIE / PACIFIQUE
    "ASEAN": {
        "nom": "Association des Nations de l'Asie du Sud-Est",
        "membres": ["BRN","KHM","IDN","LAO","MYS","MMR","PHL","SGP","THA","VNM"],
        "observateurs": ["PNG","TLS"],
        "candidats": ["TLS"],
    },
    "APEC": {
        "nom": "Coopération Économique pour l'Asie-Pacifique",
        "membres": ["AUS","BRN","CAN","CHL","CHN","HKG","IDN","JPN","KOR","MYS","MEX","NZL","PNG","PER","PHL","RUS","SGP","TWN","THA","USA","VNM"],
    },
    "SAARC": {
        "nom": "Association de l'Asie du Sud pour la Coopération Régionale",
        "membres": ["AFG","BGD","BTN","IND","MDV","NPL","PAK","LKA"],
        "observateurs": ["AUS","CHN","EUR","IRN","JPN","KOR","MUS","MMR","USA"],
    },
    "PIF": {
        "nom": "Forum des Îles du Pacifique",
        "membres": ["AUS","COK","FJI","FSM","KIR","MHL","NRU","NZL","NIU","PLW","PNG","WSM","SLB","TON","TUV","VUT"],
        "observateurs": ["ARM","CHN","CUB","FRA","IND","IDN","ITA","JPN","KOR","MYS","MAR","PHL","ESP","THA","TLS","GBR","USA"],
    },
    "RCEP": {
        "nom": "Partenariat Régional Économique Global",
        "membres": ["AUS","BRN","KHM","CHN","IDN","JPN","KOR","LAO","MYS","MMR","NZL","PHL","SGP","THA","VNM"],
    },
    "BRICS": {
        "nom": "BRICS",
        "membres": ["BRA","RUS","IND","CHN","ZAF","EGY","ETH","IRN","ARE","SAU"],
        "partenaires": ["BLR","BOL","CUB","KAZ","MYS","NGA","THA","UGA","UZB","VNM"],
    },

    # LIGUE ARABE
    "LA": {
        "nom": "Ligue Arabe",
        "membres": ["DZA","BHR","COM","DJI","EGY","IRQ","JOR","KWT","LBN","LBY","MRT","MAR","OMN","PSE","QAT","SAU","SOM","SDN","SYR","TUN","ARE","YEM"],
        "suspendus": ["SYR"],
    },

    # ORGANISATIONS ÉCONOMIQUES / FINANCIÈRES
    "OCDE": {
        "nom": "Organisation de Coopération et de Développement Économiques",
        "membres": ["AUS","AUT","BEL","CAN","CHL","COL","CRI","CZE","DNK","EST","FIN","FRA","DEU","GRC","HUN","ISL","IRL","ISR","ITA","JPN","KOR","LVA","LTU","LUX","MEX","NLD","NZL","NOR","POL","PRT","SVK","SVN","ESP","SWE","CHE","TUR","GBR","USA"],
        "candidats": ["ARG","BRA","BGR","CHN","HRV","IND","IDN","PER","ROU","SAU","THA","VNM"],
    },
    "OMC": {
        "nom": "Organisation Mondiale du Commerce",
        "membres": ["AFG","ALB","AGO","ATG","ARG","ARM","AUS","AUT","BHS","BHR","BGD","BRB","BEL","BLZ","BEN","BOL","BWA","BRA","BRN","BGR","BFA","BDI","CPV","KHM","CMR","CAN","CAF","TCD","CHL","CHN","COL","COD","COG","CRI","CIV","HRV","CUB","CYP","CZE","DNK","DJI","DMA","DOM","ECU","EGY","SLV","EST","SWZ","ETH","FJI","FIN","FRA","GAB","GMB","DEU","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HKG","HUN","ISL","IND","IDN","IRL","ISR","ITA","JAM","JPN","JOR","KEN","KOR","KWT","KGZ","LAO","LVA","LSO","LBR","LIE","LTU","LUX","MAC","MDG","MWI","MYS","MDV","MLI","MLT","MRT","MUS","MEX","MDA","MNG","MNE","MAR","MOZ","MMR","NAM","NPL","NLD","NZL","NIC","NER","NGA","NOR","OMN","PAK","PAN","PNG","PRY","PER","PHL","POL","PRT","QAT","ROU","RUS","RWA","KNA","LCA","VCT","WSM","SAU","SEN","SLE","SGP","SVK","SVN","SLB","ZAF","ESP","LKA","SUR","SWE","CHE","TWN","TJK","TZA","THA","TGO","TON","TTO","TUN","TUR","UGA","UKR","ARE","GBR","USA","URY","VUT","VEN","VNM","YEM","ZMB","ZWE"],
        "observateurs": ["DZA","AND","AZE","BLR","BHT","BIH","COM","CUB","ETH","IRN","IRQ","LBN","LBY","LBR","MDV","MNG","SRB","SYR","UZB","VEN","YEM"],
    },
    "AIIB": {
        "nom": "Banque Asiatique d'Investissement pour les Infrastructures",
        "membres": ["AFG","ALB","AUS","AUT","AZE","BGD","BLR","BEL","BHT","BOL","BIH","BRA","BRN","KHM","CMR","CAN","CHN","CYP","CZE","DNK","EGY","ETH","FIN","FRA","GEO","DEU","GHA","GRC","HUN","IND","IDN","IRN","IRL","ISR","ITA","JOR","KAZ","KEN","KOR","KGZ","LAO","LVA","LBN","LBR","LTU","LUX","MDG","MYS","MDV","MLT","MRT","MUS","MON","MNG","MNE","MAR","MMR","NPL","NLD","NZL","NGA","NOR","OMN","PAK","PHL","POL","PRT","QAT","ROU","RUS","SAU","SRB","SGP","SVK","ZAF","ESP","LKA","SWE","CHE","TJK","THA","TUR","ARE","GBR","URY","UZB","VNM","YEM"],
    },
    "GAFI": {
        "nom": "Groupe d'Action Financière",
        "membres": ["ARG","AUS","AUT","BEL","BRA","CAN","CHN","DNK","EST","FIN","FRA","DEU","GRC","HKG","HUN","ISL","IND","IRL","ISR","ITA","JPN","KOR","LVA","LTU","LUX","MYS","MEX","NLD","NZL","NOR","POL","PRT","RUS","SAU","SGP","ZAF","ESP","SWE","CHE","TUR","GBR","USA"],
        "observateurs": [],
    },
    "BRI": {
        "nom": "Initiative Ceinture et Route",
        "signataires": ["AFG","ALB","AGO","ATG","ARG","ARM","AZE","BGD","BLR","BEL","BLZ","BEN","BOL","BIH","BWA","BRN","BGR","BFA","KHM","CMR","CAF","CHL","CHN","COL","COD","COG","CRI","CIV","CUB","CYP","CZE","DJI","DOM","ECU","EGY","SLV","SWZ","ETH","FJI","GAB","GMB","GEO","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HUN","IDN","IRN","IRQ","ITA","JAM","JOR","KAZ","KEN","KGZ","LAO","LBN","LBR","MDG","MWI","MYS","MDV","MLI","MLT","MRT","MUS","MDA","MNG","MNE","MAR","MOZ","MMR","NPL","NIC","NER","NGA","OMN","PAK","PAN","PNG","PRY","PER","PHL","POL","PRT","ROU","RUS","RWA","SAU","SEN","SLE","SRB","LKA","SUR","SYR","TJK","TZA","THA","TGO","TTO","TUN","TUR","UGA","ARE","URY","UZB","VNM","YEM","ZMB","ZWE"],
    },

    # ÉNERGIE / RESSOURCES
    "OPEP": {
        "nom": "Organisation des Pays Exportateurs de Pétrole",
        "membres": ["DZA","COG","GAB","GNQ","IRN","IRQ","KWT","LBY","NGA","SAU","ARE","VEN"],
        "suspendus": [],
    },
    "OPEP+": {
        "nom": "Alliance OPEP+",
        "allies": ["AZE","BHR","BRN","KAZ","MYS","MEX","OMN","RUS","SDN","SSD"],
    },
    "GECF": {
        "nom": "Forum des Pays Exportateurs de Gaz",
        "membres": ["DZA","AGO","BOL","EGY","GNQ","IRN","LBY","MOZ","NGA","QAT","RUS","TTO","ARE","VEN"],
        "observateurs": ["AZE","IRQ","KAZ","NOR","OMN","PER"],
    },
    "IEA": {
        "nom": "Agence Internationale de l'Énergie",
        "membres": ["AUS","AUT","BEL","CAN","CZE","DNK","EST","FIN","FRA","DEU","GRC","HUN","IRL","ITA","JPN","KOR","LVA","LTU","LUX","MEX","NLD","NZL","NOR","POL","PRT","SVK","ESP","SWE","CHE","TUR","GBR","USA"],
        "associes": ["ARG","BRA","CHN","IND","IDN","MAR","SGP","ZAF","THA"],
    },

    # TRAITÉS DÉSARMEMENT
    "TNP": {
        "nom": "Traité sur la Non-Prolifération des Armes Nucléaires",
        "ratifies": ["AFG","ALB","AGO","ATG","ARG","ARM","AUS","AUT","AZE","BHS","BHR","BGD","BRB","BLR","BEL","BLZ","BEN","BOL","BIH","BWA","BRA","BRN","BGR","BFA","BDI","CPV","KHM","CMR","CAN","CAF","TCD","CHL","CHN","COL","COM","COD","COG","CRI","CIV","HRV","CUB","CYP","CZE","DNK","DJI","DMA","DOM","ECU","EGY","SLV","GNQ","EST","SWZ","ETH","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HUN","ISL","IND","IDN","IRN","IRL","ISR","ITA","JAM","JPN","JOR","KAZ","KEN","KIR","KOR","KWT","KGZ","LAO","LVA","LBN","LSO","LBR","LBY","LIE","LTU","LUX","MDG","MWI","MYS","MDV","MLI","MLT","MHL","MRT","MUS","MEX","FSM","MDA","MCO","MNG","MNE","MAR","MOZ","MMR","NAM","NRU","NPL","NLD","NZL","NIC","NER","NGA","NOR","OMN","PAK","PLW","PAN","PNG","PRY","PER","PHL","POL","PRT","QAT","ROU","RUS","RWA","KNA","LCA","VCT","WSM","SAU","SEN","SRB","SLE","SGP","SVK","SVN","SLB","ZAF","ESP","LKA","SDN","SUR","SWE","CHE","TJK","TZA","THA","TLS","TGO","TON","TTO","TUN","TUR","TKM","TUV","UGA","UKR","ARE","GBR","USA","URY","UZB","VUT","VEN","VNM","YEM","ZMB","ZWE"],
        "non_signataires": ["IND","ISR","PAK","SSD"],
        "retrait": ["PRK"],
    },
    "CWC": {
        "nom": "Convention sur les Armes Chimiques",
        "ratifies": ["AFG","ALB","AGO","ATG","ARG","ARM","AUS","AUT","AZE","BHS","BHR","BGD","BRB","BLR","BEL","BLZ","BEN","BOL","BIH","BWA","BRA","BRN","BGR","BFA","BDI","CPV","KHM","CMR","CAN","CAF","TCD","CHL","CHN","COL","COM","COD","COG","CRI","CIV","HRV","CUB","CYP","CZE","DNK","DJI","DMA","DOM","ECU","EGY","SLV","GNQ","EST","SWZ","ETH","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HUN","ISL","IND","IDN","IRL","ISR","ITA","JAM","JPN","JOR","KAZ","KEN","KOR","KWT","KGZ","LAO","LVA","LBN","LSO","LBR","LBY","LIE","LTU","LUX","MDG","MWI","MYS","MDV","MLI","MLT","MRT","MUS","MEX","MDA","MCO","MNG","MNE","MAR","MOZ","MMR","NAM","NPL","NLD","NZL","NIC","NER","NGA","NOR","OMN","PAK","PAN","PNG","PRY","PER","PHL","POL","PRT","QAT","ROU","RUS","RWA","KNA","LCA","VCT","WSM","SAU","SEN","SRB","SLE","SGP","SVK","SVN","SLB","ZAF","ESP","LKA","SDN","SWE","CHE","TJK","TZA","THA","TGO","TTO","TUN","TUR","TKM","UGA","UKR","ARE","GBR","USA","URY","UZB","VUT","VEN","VNM","ZMB","ZWE"],
        "non_signataires": ["EGY","PRK","SSD"],
    },
    "ATT": {
        "nom": "Traité sur le Commerce des Armes",
        "ratifies": ["ALB","AND","ARG","AUS","AUT","BHS","BRB","BEL","BLZ","BEN","BOL","BIH","BWA","BRA","BGR","BFA","BDI","CPV","CMR","CAN","CAF","TCD","CHL","COL","COM","CRI","HRV","CYP","CZE","DNK","DOM","ECU","SLV","EST","SWZ","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HUN","ISL","IRL","ITA","JAM","JPN","JOR","KEN","KOR","LVA","LBN","LSO","LBR","LIE","LTU","LUX","MDG","MWI","MLI","MLT","MRT","MUS","MEX","MDA","MCO","MNE","MAR","MOZ","NAM","NLD","NZL","NIC","NER","NGA","NOR","PAN","PNG","PRY","PER","PHL","POL","PRT","ROU","RWA","KNA","LCA","VCT","WSM","SEN","SRB","SLE","SVK","SVN","ZAF","ESP","LKA","SWE","CHE","TZA","TGO","TTO","TUN","TUR","UGA","GBR","URY","VUT","ZMB"],
        "signataires": ["USA","CHN","RUS","IND","PAK","ISR","EGY","SAU","IRN","SYR"],
    },
    "CPI": {
        "nom": "Cour Pénale Internationale",
        "ratifies": ["AFG","ALB","AND","ATG","ARG","ARM","AUS","AUT","BHS","BGD","BRB","BEL","BLZ","BEN","BOL","BIH","BWA","BRA","BGR","BFA","BDI","CPV","KHM","CAN","CAF","TCD","CHL","COL","COM","COD","COG","CRI","HRV","CYP","CZE","DNK","DJI","DMA","ECU","EST","SWZ","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA","GRC","GRD","GTM","GIN","GUY","HTI","HND","HUN","ISL","IRL","ITA","JPN","JOR","KEN","KOR","LVA","LSO","LBR","LIE","LTU","LUX","MDG","MWI","MDV","MLI","MLT","MHL","MRT","MUS","MEX","MDA","MNG","MNE","NAM","NLD","NZL","NER","NGA","NOR","PAN","PRY","PER","PHL","POL","PRT","ROU","SAO","SEN","SRB","SLE","SVK","SVN","ZAF","ESP","LKA","SWE","CHE","TJK","TZA","TLS","TGO","TTO","TUN","UGA","GBR","URY","VNM","ZMB"],
        "signataires": ["USA","RUS","ISR","SDN","SYR"],
        "retrait": ["BUR","GMB","ZAF","PHL"],
    },
    "Paris": {
        "nom": "Accord de Paris sur le Climat",
        "ratifies": ["AFG","ALB","DZA","AND","AGO","ATG","ARG","ARM","AUS","AUT","AZE","BHS","BHR","BGD","BRB","BLR","BEL","BLZ","BEN","BOL","BIH","BWA","BRA","BRN","BGR","BFA","BDI","CPV","KHM","CMR","CAN","CAF","TCD","CHL","CHN","COL","COM","COD","COG","CRI","CIV","HRV","CUB","CYP","CZE","DNK","DJI","DMA","DOM","ECU","EGY","SLV","GNQ","ERI","EST","SWZ","ETH","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HUN","ISL","IND","IDN","IRN","IRL","ISR","ITA","JAM","JPN","JOR","KAZ","KEN","KIR","KOR","KWT","KGZ","LAO","LVA","LBN","LSO","LBR","LBY","LIE","LTU","LUX","MDG","MWI","MYS","MDV","MLI","MLT","MHL","MRT","MUS","MEX","FSM","MDA","MCO","MNG","MNE","MAR","MOZ","MMR","NAM","NRU","NPL","NLD","NZL","NIC","NER","NGA","NOR","OMN","PAK","PLW","PAN","PNG","PRY","PER","PHL","POL","PRT","QAT","ROU","RUS","RWA","KNA","LCA","VCT","WSM","SAU","SEN","SRB","SLE","SGP","SVK","SVN","SLB","ZAF","ESP","LKA","SDN","SUR","SWE","CHE","SYR","TJK","TZA","THA","TLS","TGO","TON","TTO","TUN","TUR","TKM","TUV","UGA","UKR","ARE","GBR","USA","URY","UZB","VUT","VEN","VNM","YEM","ZMB","ZWE"],
    },
    "CNUDM": {
        "nom": "Convention des Nations Unies sur le Droit de la Mer",
        "ratifies": ["ALB","DZA","AGO","ATG","ARG","ARM","AUS","AUT","BHS","BHR","BGD","BRB","BLR","BEL","BLZ","BEN","BOL","BIH","BWA","BRA","BRN","BGR","BFA","BDI","CPV","KHM","CMR","CAN","CAF","TCD","CHL","CHN","COM","COD","COG","CRI","CIV","HRV","CUB","CYP","CZE","DNK","DJI","DMA","DOM","ECU","EGY","SLV","GNQ","ERI","EST","SWZ","ETH","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA","GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HUN","ISL","IND","IDN","IRL","ITA","JAM","JPN","JOR","KEN","KIR","KOR","KWT","LAO","LVA","LBN","LSO","LBR","LBY","LIE","LTU","LUX","MDG","MWI","MYS","MDV","MLI","MLT","MHL","MRT","MUS","MEX","FSM","MDA","MCO","MNG","MNE","MAR","MOZ","MMR","NAM","NRU","NPL","NLD","NZL","NIC","NER","NGA","NOR","OMN","PAK","PLW","PAN","PNG","PRY","PER","PHL","POL","PRT","QAT","ROU","RUS","RWA","KNA","LCA","VCT","WSM","SAU","SEN","SRB","SLE","SGP","SVK","SVN","SLB","ZAF","ESP","LKA","SDN","SUR","SWE","CHE","TJK","TZA","THA","TLS","TGO","TON","TTO","TUN","TUR","TKM","TUV","UGA","UKR","ARE","GBR","URY","UZB","VUT","VNM","YEM","ZMB","ZWE"],
        "non_signataires": ["USA","ISR","PRK","IRN","TUR","VEN","SYR"],
    },
}

# Membres permanents CS ONU
P5 = {"CHN", "FRA", "RUS", "GBR", "USA"}

# Puissances nucléaires déclarées (TNP)
NUCLEAIRE_DECLARE = {"CHN", "FRA", "RUS", "GBR", "USA"}

# Puissances nucléaires non déclarées / non-TNP
NUCLEAIRE_NON_DECLARE = {"IND", "PAK", "PRK", "ISR"}

# -------------------------------------------------------------
# GÉNÉRATION DU RÉFÉRENTIEL
# -------------------------------------------------------------

def parse_orgs_from_excel(org_str):
    """Parse le champ organisation du fichier Excel."""
    orgs = {}
    if not org_str or str(org_str) in ('0', 'nan'):
        return orgs

    ORG_LABELS = {
        'OTAN': 'OTAN', 'UE': 'UE', 'OCDE': 'OCDE', 'G7': 'G7',
        'BRICS': 'BRICS', 'OCS': 'OCS', 'OTSC': 'OTSC', 'OPEP': 'OPEP',
        'ASEAN': 'ASEAN', 'ANZUS': 'ANZUS', 'LA': 'LA',
        'MERCOSUR': 'MERCOSUR', 'UNASUR': 'UNASUR', 'ACEUM': 'ACEUM',
        'ACAEUM': 'ACAEUM',
    }
    STATUT = {'1': 'membre', '2': 'observateur', '3': 'candidat', '4': 'associé', '5': 'allié'}

    for token in str(org_str).split():
        match = re.match(r'^([A-Z0-9]+?)(\d)(\+?)$', token)
        if match:
            code = match.group(1)
            statut_num = match.group(2)
            suspended = match.group(3) == '+'
            label = ORG_LABELS.get(code, code)
            statut = STATUT.get(statut_num, 'membre')
            if suspended:
                statut += '_suspendu'
            orgs[label] = statut
    return orgs


def build_referentiel(excel_path):
    df = pd.read_excel(excel_path)
    referentiel = {}

    # Étape 1 — base depuis Excel
    for _, row in df.iterrows():
        iso3 = str(row.get('ISO 3', '')).strip()
        if not iso3 or iso3 == 'nan' or len(iso3) != 3:
            continue

        def clean(v):
            s = str(v).strip()
            return '' if s in ('nan', '#N/A', '0') else s

        referentiel[iso3] = {
            "iso2":      clean(row.get('ISO 2', '')),
            "nom":       clean(row.get('PAYS', '')),
            "continent": clean(row.get('Continent', '')),
            "region":    clean(row.get('Région', '')),
            "organisations": parse_orgs_from_excel(row.get('organisation', '0')),
            "attributs": {
                "membre_permanent_cs_onu": iso3 in P5,
                "puissance_nucleaire_declaree": iso3 in NUCLEAIRE_DECLARE,
                "puissance_nucleaire": iso3 in NUCLEAIRE_DECLARE | NUCLEAIRE_NON_DECLARE,
            },
            "noms_sources": {
                "sipri":  clean(row.get('SIPRI ARMEMENT', '')),
                "unhcr":  clean(row.get('UNHCR REFUGIES', '')),
                "undesa": clean(row.get('UNDESA Migrants', '')),
                "dette":  clean(row.get('LISTE DETTE', '')),
            }
        }

    # Étape 2 — enrichissement depuis ORGANISATIONS
    for org_code, org_data in ORGANISATIONS.items():
        for statut_key, iso3_list in org_data.items():
            if statut_key == 'nom':
                continue
            # Mapping clé → statut
            statut_map = {
                'membres': 'membre', 'observateurs': 'observateur',
                'candidats': 'candidat', 'associes': 'associé',
                'allies': 'allié', 'partenaires': 'partenaire',
                'signataires': 'signataire', 'ratifies': 'ratifié',
                'suspendus': 'suspendu', 'retrait': 'retrait',
                'non_signataires': 'non_signataire',
            }
            statut = statut_map.get(statut_key, statut_key)
            for iso3 in iso3_list:
                if iso3 not in referentiel:
                    # Pays absent du fichier Excel — on l'ajoute minimalement
                    referentiel[iso3] = {
                        "iso2": "", "nom": iso3, "continent": "",
                        "region": "", "organisations": {},
                        "attributs": {
                            "membre_permanent_cs_onu": iso3 in P5,
                            "puissance_nucleaire_declaree": iso3 in NUCLEAIRE_DECLARE,
                            "puissance_nucleaire": iso3 in NUCLEAIRE_DECLARE | NUCLEAIRE_NON_DECLARE,
                        },
                        "noms_sources": {"sipri":"","unhcr":"","undesa":"","dette":""}
                    }
                # Ne pas écraser un statut existant plus précis
                existing = referentiel[iso3]["organisations"].get(org_code)
                if not existing or existing == 'membre':
                    referentiel[iso3]["organisations"][org_code] = statut

    return referentiel


if __name__ == "__main__":
    ref = build_referentiel('/mnt/user-data/uploads/reference_pays.xlsx')
    print(f"Pays générés : {len(ref)}")
    print("\nExemple FRA:")
    print(json.dumps(ref.get('FRA', {}), ensure_ascii=False, indent=2))
    print("\nExemple RUS:")
    print(json.dumps(ref.get('RUS', {}), ensure_ascii=False, indent=2))
    print("\nExemple IND:")
    print(json.dumps(ref.get('IND', {}), ensure_ascii=False, indent=2))

    with open('/mnt/user-data/outputs/referentiel.json', 'w', encoding='utf-8') as f:
        json.dump(ref, f, ensure_ascii=False, indent=2)
    print(f"\nFichier généré : {len(ref)} pays")
