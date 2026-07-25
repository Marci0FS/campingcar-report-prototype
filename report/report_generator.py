"""Combine les champs extraits d'une annonce avec les bases de connaissance
châssis + cellule pour produire un rapport texte lisible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from parser.ad_text_parser import ParsedAd
from report.entreprise import fetch_entreprise_info
from report.rappelconso import RappelConsoResult, fetch_recent_recalls

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

# Termes de recherche RappelConso par châssis détecté : le Ducato est vendu
# sous trois badges (Sevel) qui déposent chacun leurs propres campagnes de
# rappel séparément, donc la requête doit suivre le badge réellement détecté
# dans l'annonce plutôt que la clé de base de connaissance partagée.
_RAPPELCONSO_QUERY = {
    "Fiat Ducato": ("fiat", "ducato"),
    "Citroën Jumper": ("citroen", "jumper"),
    "Peugeot Boxer": ("peugeot", "boxer"),
    "Ford Transit": ("ford", "transit"),
    "Renault Master": ("renault", "master"),
}


def _fetch_live_recalls(detected_chassis: str | None) -> RappelConsoResult:
    query = _RAPPELCONSO_QUERY.get(detected_chassis)
    if query is None:
        return RappelConsoResult(available=False, items=[])
    marque, modele = query
    return fetch_recent_recalls(marque, modele)


# Les protections légales de l'acheteur diffèrent significativement selon le
# statut du vendeur (garantie légale de conformité obligatoire côté pro,
# aucune entre particuliers hors vice caché) — indépendant du châssis/de la
# cellule, donc calculé à part plutôt que rattaché à une base de connaissance.
_SELLER_TYPE_INFO = {
    "professionnel": {
        "label": "Vendeur professionnel",
        "level": "favorable",
        "detail": (
            "Un vendeur professionnel est tenu à la garantie légale de conformité "
            "(2 ans, applicable aux véhicules d'occasion) : en cas de défaut existant "
            "à la vente, vous pouvez demander réparation, remplacement ou remboursement "
            "sans avoir à prouver une faute du vendeur. Le droit de rétractation ne "
            "s'applique en revanche pas à un véhicule visité en personne (seulement en "
            "cas de vente à distance)."
        ),
    },
    "particulier": {
        "label": "Vendeur particulier",
        "level": "defavorable",
        "detail": (
            "Entre particuliers, aucune garantie légale de conformité ne s'applique : "
            "le véhicule est vendu « en l'état », sauf mention contraire écrite. "
            "Seul recours possible : les vices cachés (article 1641 du Code civil), à "
            "charge pour l'acheteur de prouver que le défaut existait avant la vente et "
            "était indétectable lors de l'achat — plus difficile et plus long qu'une "
            "garantie légale."
        ),
    },
}


def assess_seller(ad: ParsedAd) -> dict:
    template = _SELLER_TYPE_INFO.get(ad.seller_type)
    if template is None:
        return {
            "label": "Non détecté",
            "level": "neutre",
            "detail": (
                "Le texte collé ne permet pas de déterminer si le vendeur est un "
                "professionnel ou un particulier — à vérifier sur l'annonce d'origine "
                "(badge « Pro » / n° SIRET, ou nom d'un particulier). Les "
                "protections légales de l'acheteur diffèrent significativement selon le cas."
            ),
            "entreprise": None,
        }
    info = dict(template)  # copie : ne pas muter le gabarit partagé au niveau module
    if ad.seller_type == "professionnel" and ad.seller_siret:
        info["entreprise"] = fetch_entreprise_info(ad.seller_siret)
    else:
        info["entreprise"] = None
    return info


_PHYSICAL_CHECKLIST = [
    # -- Documents, avant même de toucher au véhicule --
    "Carte grise : vérifier que le numéro de série (VIN) inscrit en case E correspond "
    "bien à celui gravé sur le pare-brise et/ou la plaque constructeur — une différence "
    "est un signal d'alerte fort (véhicule maquillé ou volé).",
    "Certificat de situation administrative (ex-certificat de non-gage), daté de moins "
    "d'un mois : atteste l'absence d'opposition (gage, saisie) sur le véhicule.",
    "Contrôle technique en cours de validité daté de moins de 6 mois (obligation légale "
    "pour la vente entre particuliers) — lire le détail des points relevés, pas seulement le résultat global.",
    "Historique du véhicule sur HistoVec (service officiel gratuit, "
    "histovec.interieur.gouv.fr) : nécessite le numéro de formule de la carte grise "
    "fourni par le vendeur ; donne l'historique des contrôles techniques et du "
    "kilométrage relevé à chaque passage — utile pour détecter un compteur trafiqué.",
    # -- Extérieur / châssis --
    "Sous le châssis : rechercher des traces de rouille perforante (pas seulement "
    "superficielle) — un châssis fortement corrodé est un motif de rejet, indépendamment "
    "de l'état apparent de la cellule.",
    "Pneus : vérifier le code DOT (date de fabrication) sur le flanc — un remplacement "
    "est recommandé après 5 ans même si la sculpture semble correcte, le caoutchouc se "
    "dégradant avec le temps indépendamment de l'usure visible.",
    # -- Sous le capot / au démarrage --
    "Sous le capot : rechercher des traces de fuite d'huile ou de liquide de "
    "refroidissement — à l'inverse, un moteur anormalement propre peut aussi être un "
    "signal à interroger (nettoyage pour masquer un suintement).",
    "Au démarrage : tous les voyants du tableau de bord doivent s'allumer puis "
    "s'éteindre après quelques secondes — un voyant qui reste allumé (ou qui ne "
    "s'allume jamais) signale un défaut ou un capteur débranché.",
    "Comparer l'usure du volant, des pédales et du siège conducteur avec le "
    "kilométrage affiché — une usure très supérieure au kilométrage annoncé est un "
    "indice possible de compteur trafiqué.",
    "Date/kilométrage du dernier remplacement de la courroie de distribution du "
    "châssis (voir carnet d'entretien) — point de vigilance mécanique n°1 sur ce type de véhicule.",
    # -- Cellule / étanchéité --
    "Test d'humidité au compteur (hygromètre) sur les zones sensibles : plafond, "
    "coins, autour des lanterneaux et fenêtres — un taux souvent cité comme repère est "
    "sous 14 % (à titre indicatif, variable selon les appareils), au-delà considérez "
    "que c'est suspect ; idéalement fait par un professionnel agréé récemment "
    "(comptez 70-150€ si ce n'est pas déjà fait par le vendeur).",
    "Inspection visuelle des joints : lanterneaux, jonctions toit-parois, baies "
    "vitrées, passages d'antenne — chercher fissures, décollements, traces de moisissure.",
    "État du plancher : souplesse anormale, odeur d'humidité, taches — un plancher "
    "qui a pris l'eau peut se dégrader sans trace visible en surface au début.",
    # -- Équipements --
    "Fonctionnement du frigo (à absorption sur la plupart des modèles), du chauffage "
    "et de la batterie auxiliaire — pannes classiques sur ce type de véhicule, indépendantes de la marque.",
    "Installation gaz (cuisson, chauffage) : vérifier la conformité et l'absence "
    "d'odeur de fuite au niveau des bouteilles et du détendeur — point de sécurité, pas seulement de confort.",
    "Historique d'entretien complet (carnet, factures) — l'entretien individuel du "
    "véhicule compte souvent plus que la seule réputation de la marque.",
    # -- Essai routier, en dernier --
    "Essai routier si possible : freinage, embrayage, direction, passage des "
    "vitesses, bruits inhabituels (courroies, suspension) — la checklist statique ne "
    "remplace pas un test en conditions réelles.",
]


def _engines_for_year(engines: list[dict], registration_year: int | None) -> list[dict]:
    """Ne garde que les générations moteur dont le year_range couvre l'année
    de mise en circulation détectée, pour éviter d'afficher un avertissement
    propre à une autre génération (ex: chaîne de distribution fragile 2011-2015
    sur un véhicule 2018). Si l'année est inconnue, ou si aucune génération ne
    correspond, retombe sur la liste complète plutôt que de rester sans rien.
    """
    if registration_year is None:
        return engines
    matching = [
        e for e in engines
        if "year_range" not in e or e["year_range"][0] <= registration_year <= e["year_range"][1]
    ]
    return matching or engines


def load_chassis_knowledge(key: str) -> dict:
    path = KNOWLEDGE_DIR / "chassis" / f"{key}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_cellule_knowledge(key: str) -> dict:
    path = KNOWLEDGE_DIR / "cellule" / f"{key}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


_CELLULE_KEY_MAP = {
    "CI": "ci", "Rapido": "rapido", "Hymer": "hymer", "Carthago": "carthago",
    "Frankia": "frankia", "Knaus": "knaus", "Dethleffs": "dethleffs",
    "Bürstner": "burstner", "Pilote": "pilote", "Chausson": "chausson",
    "Challenger": "challenger", "Adria": "adria", "Laika": "laika",
    "Benimar": "benimar", "Etrusco": "etrusco",
}
# Fiat Ducato / Citroën Jumper / Peugeot Boxer partagent la même plateforme
# (Sevel) : même base de connaissance, nom affiché = celui détecté dans l'annonce.
_CHASSIS_KEY_MAP = {
    "Fiat Ducato": "fiat-ducato", "Citroën Jumper": "fiat-ducato", "Peugeot Boxer": "fiat-ducato",
    "Ford Transit": "ford-transit", "Renault Master": "renault-master",
}


@dataclass
class PriceAssessment:
    verdict: str
    detail: str


def assess_price(ad: ParsedAd, cellule_knowledge: dict | None) -> PriceAssessment:
    if cellule_knowledge is None:
        return PriceAssessment(
            verdict="Non évaluable",
            detail="Pas de fourchette de prix disponible : la marque de cellule n'est pas "
            "couverte par ce prototype, et une fourchette générique toutes marques confondues "
            "serait trop imprécise pour être utile.",
        )
    if ad.price_eur is None or ad.registration_year is None or not ad.detected_body_type:
        return PriceAssessment(
            verdict="Non évaluable",
            detail="Prix, année ou type de carrosserie manquants dans le texte collé.",
        )

    for band in cellule_knowledge["price_reference_eur"]["bands"]:
        if band["body_type"] != ad.detected_body_type:
            continue
        y_min, y_max = band["year_range"]
        if y_min <= ad.registration_year <= y_max:
            p_min, p_max = band["price_range_eur"]
            if ad.price_eur < p_min:
                return PriceAssessment(
                    "En dessous de la fourchette indicative",
                    f"Prix {ad.price_eur} € vs fourchette indicative {p_min}-{p_max} € "
                    f"pour un {ad.detected_body_type} {ad.registration_year} {cellule_knowledge['cellule']}. "
                    f"Un prix anormalement bas mérite une vigilance particulière.",
                )
            if ad.price_eur > p_max:
                return PriceAssessment(
                    "Au-dessus de la fourchette indicative",
                    f"Prix {ad.price_eur} € vs fourchette indicative {p_min}-{p_max} € "
                    f"pour un {ad.detected_body_type} {ad.registration_year} {cellule_knowledge['cellule']}.",
                )
            return PriceAssessment(
                "Dans la fourchette indicative",
                f"Prix {ad.price_eur} € cohérent avec la fourchette indicative "
                f"{p_min}-{p_max} € pour un {ad.detected_body_type} {ad.registration_year} "
                f"{cellule_knowledge['cellule']}.",
            )

    return PriceAssessment(
        "Non évaluable",
        f"Aucune fourchette de référence pour {ad.detected_body_type} {ad.registration_year}.",
    )


def _confidence_tag(confidence: str) -> str:
    return "documenté" if confidence == "documented" else "anecdotique, à vérifier"


def build_report(ad: ParsedAd) -> str:
    lines: list[str] = []

    if ad.support_level == "unsupported":
        lines.append("=== Châssis non reconnu par ce prototype ===\n")
        lines.append(
            f"Châssis détecté : {ad.detected_chassis or 'non identifié'}. "
            f"Cellule détectée : {ad.detected_cellule or 'non identifiée'}."
        )
        lines.append(
            "Ce prototype ne couvre que Fiat Ducato/Citroën Jumper/Peugeot Boxer, "
            "Ford Transit ou Renault Master comme châssis. Aucun rapport n'est généré, "
            "faute de base mécanique à laquelle rattacher un avis."
        )
        return "\n".join(lines)

    chassis = load_chassis_knowledge(_CHASSIS_KEY_MAP[ad.detected_chassis])
    cellule = load_cellule_knowledge(_CELLULE_KEY_MAP[ad.detected_cellule]) if ad.support_level == "full" else None

    title_cellule = f" / cellule {cellule['cellule']}" if cellule else " / cellule non couverte"
    lines.append(f"=== Rapport — {ad.detected_chassis}{title_cellule} ===\n")

    lines.append("-- Données extraites de l'annonce --")
    lines.append(f"Prix : {ad.price_eur} €" if ad.price_eur else "Prix : non détecté")
    lines.append(
        f"Kilométrage : {ad.mileage_km} km" if ad.mileage_km else "Kilométrage : non détecté"
    )
    if ad.registration_month and ad.registration_year:
        lines.append(f"Mise en circulation : {ad.registration_month:02d}/{ad.registration_year}")
    elif ad.registration_year:
        lines.append(f"Année : {ad.registration_year}")
    else:
        lines.append("Année : non détectée")
    lines.append(f"Type de carrosserie : {ad.detected_body_type or 'non détecté'}")
    if ad.warnings:
        for w in ad.warnings:
            lines.append(f"  ⚠ {w}")
    lines.append("")

    seller = assess_seller(ad)
    lines.append("-- Vendeur --")
    lines.append(f"{seller['label']} : {seller['detail']}")
    entreprise = seller.get("entreprise")
    if entreprise is not None:
        if not entreprise.available:
            lines.append("(Recherche entreprise indisponible pour le moment.)")
        elif entreprise.info is None:
            lines.append(f"Aucune entreprise trouvée pour le SIRET {ad.seller_siret}.")
        else:
            i = entreprise.info
            lines.append(
                f"{i.raison_sociale} — {i.adresse or 'adresse inconnue'} — "
                f"créée le {i.date_creation or '?'}"
                + (f" (~{i.anciennete_annees} an(s) d'activité)" if i.anciennete_annees is not None else "")
                + f" — statut {i.etat_administratif} "
                f"(source : recherche-entreprises.api.gouv.fr, SIRET {ad.seller_siret})"
            )
    lines.append("")

    price = assess_price(ad, cellule)
    lines.append("-- Cohérence prix / marché (indicatif) --")
    lines.append(f"{price.verdict} : {price.detail}")
    lines.append("")

    if cellule:
        lines.append("-- Réputation étanchéité de la cellule --")
        rep = cellule["etancheite_reputation"]
        lines.append(f"({_confidence_tag(rep['confidence'])}) {rep['summary']}")
        lines.append(f"Recommandation : {rep['recommendation']}")
    else:
        lines.append("-- Réputation étanchéité de la cellule --")
        lines.append(
            f"Non documenté : la marque de cellule "
            f"{'(' + ad.detected_cellule + ') ' if ad.detected_cellule else ''}"
            "n'est pas couverte par ce prototype. Vigilance recommandée par défaut "
            "(test d'humidité avant achat, voir checklist)."
        )
    lines.append("")

    lines.append("-- Rappel constructeur (châssis) --")
    recall = chassis["recall"]
    lines.append(recall["summary"])
    lines.append(f"⚠ {recall['important']}")
    lines.append(f"Vérifier ce véhicule précis ici : {recall['official_check_url']}")
    live_recalls = _fetch_live_recalls(ad.detected_chassis)
    if not live_recalls.available:
        lines.append("(Recherche en direct RappelConso indisponible pour le moment.)")
    elif not live_recalls.items:
        lines.append("Recherche en direct RappelConso : aucune campagne trouvée pour ce modèle à ce jour.")
    else:
        lines.append(f"Recherche en direct RappelConso ({len(live_recalls.items)} résultat(s)) :")
        for item in live_recalls.items:
            lines.append(f"  - [{item.date_publication}] {item.marque} — {item.modele} : {item.motif} ({item.url})")
    lines.append("")

    lines.append("-- Points de vigilance mécanique (châssis) --")
    for engine in _engines_for_year(chassis["engines"], ad.registration_year):
        lines.append(f"[{engine['name']}]")
        for issue in engine["known_issues"]:
            lines.append(f"  - ({_confidence_tag(issue['confidence'])}) {issue['description']}")
    lines.append("")

    lines.append("-- Défauts fréquents signalés --")
    all_defects = chassis["common_defects"] + (cellule["common_defects"] if cellule else [])
    for defect in all_defects:
        lines.append(f"  - ({_confidence_tag(defect['confidence'])}) {defect['description']}")
    lines.append("")

    lines.append("-- Entretien (châssis) --")
    maint = chassis["maintenance"]
    lines.append(maint["distribution"])
    costs = maint["revision_cost_eur_indicative"]
    lines.append(
        f"Coûts indicatifs : vidange {costs['vidange_simple'][0]}-{costs['vidange_simple'][1]} € | "
        f"révision complète {costs['revision_complete'][0]}-{costs['revision_complete'][1]} € | "
        f"distribution {costs['distribution'][0]}-{costs['distribution'][1]} €"
    )
    lines.append(f"({maint['note']})")
    lines.append("")

    lines.append("-- Checklist de vérification physique à faire sur place --")
    for i, item in enumerate(_PHYSICAL_CHECKLIST, start=1):
        lines.append(f"  {i}. {item}")

    return "\n".join(lines)


def _tag_confidence_items(items: list[dict]) -> list[dict]:
    return [{**item, "tag": _confidence_tag(item["confidence"])} for item in items]


_PRICE_VERDICT_LEVELS = {
    "Dans la fourchette indicative": "favorable",
    "En dessous de la fourchette indicative": "defavorable",
    "Au-dessus de la fourchette indicative": "defavorable",
    "Non évaluable": "neutre",
}


def build_report_context(ad: ParsedAd) -> dict:
    """Version structurée de build_report(), pour un rendu HTML section par
    section plutôt qu'un bloc de texte préformaté. N'affecte pas build_report()
    ni cli.py, qui restent inchangés.
    """
    if ad.support_level == "unsupported":
        return {
            "level": "unsupported",
            "detected_chassis": ad.detected_chassis,
            "detected_cellule": ad.detected_cellule,
        }

    chassis = load_chassis_knowledge(_CHASSIS_KEY_MAP[ad.detected_chassis])
    cellule = load_cellule_knowledge(_CELLULE_KEY_MAP[ad.detected_cellule]) if ad.support_level == "full" else None
    price = assess_price(ad, cellule)
    recall = chassis["recall"]

    engines = []
    for engine in _engines_for_year(chassis["engines"], ad.registration_year):
        engines.append({
            "name": engine["name"],
            "known_issues": _tag_confidence_items(engine["known_issues"]),
        })

    if cellule:
        rep = cellule["etancheite_reputation"]
        etancheite = {**rep, "tag": _confidence_tag(rep["confidence"])}
        cellule_name = cellule["cellule"]
        common_defects = chassis["common_defects"] + cellule["common_defects"]
    else:
        etancheite = {
            "level": "neutre",
            "tag": "non documenté",
            "summary": (
                f"La marque de cellule {ad.detected_cellule or 'détectée'} n'est pas couverte "
                "par ce prototype : aucune donnée de réputation étanchéité disponible."
            ),
            "recommendation": "Vigilance renforcée par défaut en l'absence de données : "
            "exiger un test d'humidité récent avant achat (voir checklist).",
        }
        cellule_name = ad.detected_cellule or "non identifiée"
        common_defects = chassis["common_defects"]

    return {
        "level": ad.support_level,
        "ad": ad,
        "chassis_name": ad.detected_chassis,
        "cellule_name": cellule_name,
        "seller": assess_seller(ad),
        "price": price,
        "price_level": _PRICE_VERDICT_LEVELS.get(price.verdict, "neutre"),
        "etancheite": etancheite,
        "recall": recall,
        "live_recalls": _fetch_live_recalls(ad.detected_chassis),
        "engines": engines,
        "common_defects": _tag_confidence_items(common_defects),
        "maintenance": chassis["maintenance"],
        "checklist": _PHYSICAL_CHECKLIST,
    }
