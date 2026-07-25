"""Extrait les champs utiles (prix, kilométrage, année, châssis, cellule,
type de carrosserie) à partir du texte brut d'une annonce, copié-collé par
l'utilisateur depuis son navigateur. Aucune requête réseau ici.

L'extraction générique (prix/km/date) reprend la logique déjà validée sur
le prototype auto (car-report-prototype/parser/ad_text_parser.py) : labels
structurés en priorité, scan libre du texte entier en dernier recours
seulement, pour éviter d'attraper une date d'entretien au lieu de la date
de mise en circulation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedAd:
    price_eur: int | None = None
    mileage_km: int | None = None
    registration_year: int | None = None
    registration_month: int | None = None
    detected_chassis: str | None = None
    detected_cellule: str | None = None
    detected_body_type: str | None = None
    # "professionnel", "particulier", ou None si non détecté dans le texte collé.
    seller_type: str | None = None
    # Numéro SIRET (14 chiffres) du vendeur professionnel, si présent dans le texte collé.
    seller_siret: str | None = None
    # "full" (châssis + cellule connus), "partial" (châssis connu, cellule non
    # couverte), "unsupported" (châssis non reconnu — rien de spécifique à dire).
    support_level: str = "unsupported"
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)


# --- Extraction générique (portée telle quelle depuis le prototype auto) ---

_NUM_CHARS = "    .,"

_PRICE_RE = re.compile(
    r"(\d[\d" + re.escape(_NUM_CHARS) + r"]{2,})\s*(?:€|eur\b)", re.IGNORECASE
)
_MILEAGE_RE = re.compile(
    r"(\d[\d" + re.escape(_NUM_CHARS) + r"]{2,})\s*km\b", re.IGNORECASE
)
_MILEAGE_LABEL_RE = re.compile(
    r"kilom[ée]trage\s*:?\s*\n?\s*(\d[\d" + re.escape(_NUM_CHARS) + r"]{2,})\s*km",
    re.IGNORECASE,
)

_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}
_MONTH_ALT = "|".join(_MONTHS_FR)

_DATE_VALUE_ALT = (
    r"(\d{1,2}/\d{1,2}/(?:19|20)\d{2}|\d{1,2}/(?:19|20)\d{2}|"
    r"(?:" + _MONTH_ALT + r")\s+(?:19|20)\d{2}|(?:19|20)\d{2})"
)

# Priorité 1 : labels les plus précis/fiables ("mise en circulation" donne
# souvent le mois en plus de l'année, contrairement à "année modèle").
_REGISTRATION_LABEL_PRECISE_RE = re.compile(
    r"(?:mise en circulation|premi[eè]re immatriculation)\s*:?\s*\n?\s*(?:le\s*)?"
    + _DATE_VALUE_ALT,
    re.IGNORECASE,
)
# Priorité 2 : labels plus grossiers, utilisés seulement si le label précis
# est absent du texte collé.
_REGISTRATION_LABEL_FALLBACK_RE = re.compile(
    r"(?:1[eè]re? main|ann[ée]e mod[eè]le|ann[ée]e)\s*:?\s*\n?\s*(?:le\s*)?"
    + _DATE_VALUE_ALT,
    re.IGNORECASE,
)
_BREADCRUMB_YEAR_RE = re.compile(r"·\s*((?:19|20)\d{2})\s*·")
_LOOSE_MMYYYY_RE = re.compile(r"\b(0?[1-9]|1[0-2])\s*/\s*((?:19|20)\d{2})\b")
_LOOSE_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _clean_number(raw: str) -> int:
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits)


def _parse_date_token(token: str) -> tuple[int | None, int]:
    token = token.strip()
    month_name_match = re.match(
        r"(" + _MONTH_ALT + r")\s+((?:19|20)\d{2})", token, re.IGNORECASE
    )
    if month_name_match:
        return _MONTHS_FR[month_name_match.group(1).lower()], int(month_name_match.group(2))

    parts = token.split("/")
    if len(parts) == 3:  # DD/MM/YYYY
        return int(parts[1]), int(parts[2])
    if len(parts) == 2:  # MM/YYYY
        return int(parts[0]), int(parts[1])
    return None, int(token)  # YYYY seul


def _extract_registration(text: str, ad: ParsedAd) -> None:
    precise_match = _REGISTRATION_LABEL_PRECISE_RE.search(text)
    if precise_match:
        ad.registration_month, ad.registration_year = _parse_date_token(precise_match.group(1))
        return

    fallback_match = _REGISTRATION_LABEL_FALLBACK_RE.search(text)
    if fallback_match:
        ad.registration_month, ad.registration_year = _parse_date_token(fallback_match.group(1))
        return

    breadcrumb_match = _BREADCRUMB_YEAR_RE.search(text)
    if breadcrumb_match:
        ad.registration_year = int(breadcrumb_match.group(1))
        return

    loose_date = _LOOSE_MMYYYY_RE.search(text)
    if loose_date:
        ad.registration_month = int(loose_date.group(1))
        ad.registration_year = int(loose_date.group(2))
        ad.warnings.append(
            "Année/mois de mise en circulation déduits d'une date isolée dans le texte "
            "(aucun label 'Mise en circulation' trouvé) : à vérifier, ça peut être une "
            "autre date (entretien, contrôle technique...)."
        )
        return

    loose_year = _LOOSE_YEAR_RE.search(text)
    if loose_year:
        ad.registration_year = int(loose_year.group(0))
        ad.warnings.append(
            "Année de mise en circulation déduite d'une valeur isolée dans le texte : à vérifier."
        )
        return

    ad.warnings.append("Année de mise en circulation introuvable dans le texte collé.")


def _extract_mileage(text: str, ad: ParsedAd) -> None:
    label_match = _MILEAGE_LABEL_RE.search(text)
    if label_match:
        ad.mileage_km = _clean_number(label_match.group(1))
        return

    generic_match = _MILEAGE_RE.search(text)
    if generic_match:
        ad.mileage_km = _clean_number(generic_match.group(1))
        return

    ad.warnings.append("Kilométrage introuvable dans le texte collé.")


# --- Détection spécifique camping-car/van ---

# Châssis couverts par ce prototype. Fiat Ducato / Citroën Jumper / Peugeot
# Boxer partagent la même plateforme (Sevel) et les mêmes moteurs : même
# base de connaissance, mais le nom réellement détecté est conservé pour
# l'affichage (voir CHASSIS_KNOWLEDGE_MAP dans report/report_generator.py).
_CHASSIS_PATTERNS = [
    ("Fiat Ducato", re.compile(r"\bfiat\s*ducato\b|\bducato\b", re.IGNORECASE)),
    # Sur Leboncoin, le vendeur nomme souvent juste la marque du porteur
    # ("Porteur Citroën 2.2L") sans citer "Jumper"/"Boxer" — contrairement au
    # Ducato, le nom seul de la marque ne suffit pas (Citroën/Peugeot font
    # d'autres véhicules), donc on ne matche ce fallback qu'accompagné d'un
    # mot de contexte "porteur/châssis/base" propre aux annonces camping-car.
    # Sans ambiguïté dans ce contexte : Jumper/Boxer sont les seuls châssis
    # van que ces deux marques proposent pour l'aménagement camping-car.
    (
        "Citroën Jumper",
        re.compile(
            r"\bcitro[eë]n\s*jumper\b"
            r"|\b(?:porteur|ch[aâ]ssis|base)\s+citro[eë]n\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Peugeot Boxer",
        re.compile(
            r"\bpeugeot\s*boxer\b"
            r"|\b(?:porteur|ch[aâ]ssis|base)\s+peugeot\b",
            re.IGNORECASE,
        ),
    ),
    ("Ford Transit", re.compile(r"\bford\s*transit\b", re.IGNORECASE)),
    ("Renault Master", re.compile(r"\brenault\s*master\b", re.IGNORECASE)),
]
_OTHER_CHASSIS_KEYWORDS = ["iveco daily", "mercedes sprinter", "volkswagen crafter"]

# Marques de cellule couvertes par ce prototype (réputation vérifiée via
# recherche rapide seulement — voir knowledge/cellule/*.json pour le détail
# et les limites de confiance de ces données).
_CELLULE_RE = {
    "CI": re.compile(r"\bC\.?I\.?\b(?!\w)", re.IGNORECASE),
    "Rapido": re.compile(r"\brapido\b", re.IGNORECASE),
    "Hymer": re.compile(r"\bhymer\b", re.IGNORECASE),
    "Carthago": re.compile(r"\bcarthago\b", re.IGNORECASE),
    "Frankia": re.compile(r"\bfrankia\b", re.IGNORECASE),
    "Knaus": re.compile(r"\bknaus\b", re.IGNORECASE),
    "Dethleffs": re.compile(r"\bdethleffs\b", re.IGNORECASE),
    "Bürstner": re.compile(r"\bb[üu]rstner\b", re.IGNORECASE),
    "Pilote": re.compile(r"\bpilote\b", re.IGNORECASE),
    "Chausson": re.compile(r"\bchausson\b", re.IGNORECASE),
    "Challenger": re.compile(r"\bchallenger\b", re.IGNORECASE),
    "Adria": re.compile(r"\badria\b", re.IGNORECASE),
    "Laika": re.compile(r"\blaika\b", re.IGNORECASE),
    "Benimar": re.compile(r"\bbenimar\b", re.IGNORECASE),
    "Etrusco": re.compile(r"\betrusco\b", re.IGNORECASE),
}
# Marques identifiées mais encore hors scope — juste pour un message d'info
# utile, pas pour générer du contenu.
_OTHER_CELLULE_KEYWORDS = [
    "weinsberg", "mac'louis", "mclouis", "sunlight", "itineo", "autostar",
    "lmc", "font-vendôme", "font vendome", "notin", "eura mobil", "roller team",
]

_BODY_TYPE_KEYWORDS = {
    "fourgon aménagé": "Fourgon aménagé / Van",
    "fourgon amenage": "Fourgon aménagé / Van",
    "van aménagé": "Fourgon aménagé / Van",
    "capucine": "Capucine",
    "profilé": "Profilé",
    "profile": "Profilé",
    "intégral": "Intégral",
    "integral": "Intégral",
}

# Détection du type de vendeur : uniquement des signaux forts et univoques.
# Un mot isolé comme "professionnel" est trop ambigu (peut apparaître dans
# "entretien fait en garage professionnel" sans rapport avec le statut du
# vendeur) — on ne se fie qu'au numéro SIRET (jamais mentionné par un
# particulier) et aux formulations explicites de statut de vendeur.
_SELLER_PRO_RE = re.compile(
    r"\bn[°o]?\s*siret\b|\bsiret\s*:?\s*\d{9}|"
    r"\bvendeur\s+professionnel\b|\bannonceur\s+professionnel\b",
    re.IGNORECASE,
)
_SELLER_PARTICULIER_RE = re.compile(
    r"\bvendeur\s+particulier\b|\bvendu\s+par\s+un\s+particulier\b|"
    r"\bannonce\s+de\s+particulier\b",
    re.IGNORECASE,
)
# Capture le numéro SIRET lui-même (14 chiffres, parfois espacés) pour
# permettre une recherche entreprise en direct — distinct de _SELLER_PRO_RE
# qui détecte juste la présence du mot.
_SIRET_CAPTURE_RE = re.compile(r"\bsiret\s*:?\s*((?:\d[\s]?){14})", re.IGNORECASE)

# Châssis/cellules réellement couverts par une base de connaissance —
# doit rester synchronisé avec les clés utilisées dans report_generator.py.
_SUPPORTED_CHASSIS = {"Fiat Ducato", "Citroën Jumper", "Peugeot Boxer", "Ford Transit", "Renault Master"}
_SUPPORTED_CELLULES = set(_CELLULE_RE.keys())


def _detect_chassis(text: str, ad: ParsedAd) -> None:
    for name, pattern in _CHASSIS_PATTERNS:
        if pattern.search(text):
            ad.detected_chassis = name
            return
    lower = text.lower()
    for kw in _OTHER_CHASSIS_KEYWORDS:
        if kw in lower:
            ad.detected_chassis = kw.title()
            return


def _detect_cellule(text: str, lower: str, ad: ParsedAd) -> None:
    for name, pattern in _CELLULE_RE.items():
        if pattern.search(text):
            ad.detected_cellule = name
            return
    for kw in _OTHER_CELLULE_KEYWORDS:
        if kw in lower:
            ad.detected_cellule = kw.title()
            return


def _detect_body_type(lower: str, ad: ParsedAd) -> None:
    for kw, label in _BODY_TYPE_KEYWORDS.items():
        if kw in lower:
            ad.detected_body_type = label
            return


def _detect_seller_type(text: str, ad: ParsedAd) -> None:
    if _SELLER_PRO_RE.search(text):
        ad.seller_type = "professionnel"
        siret_match = _SIRET_CAPTURE_RE.search(text)
        if siret_match:
            ad.seller_siret = re.sub(r"\s", "", siret_match.group(1))
    elif _SELLER_PARTICULIER_RE.search(text):
        ad.seller_type = "particulier"
    else:
        ad.seller_type = None
        ad.warnings.append(
            "Type de vendeur (professionnel ou particulier) non détecté dans le texte "
            "collé : à vérifier sur l'annonce d'origine (badge \"Pro\"/n° SIRET, ou nom "
            "d'un particulier) — les protections légales de l'acheteur diffèrent "
            "significativement selon le cas."
        )


def parse_ad_text(text: str) -> ParsedAd:
    ad = ParsedAd(raw_text=text)
    lower = text.lower()

    price_match = _PRICE_RE.search(text)
    if price_match:
        ad.price_eur = _clean_number(price_match.group(1))
    else:
        ad.warnings.append("Prix introuvable dans le texte collé.")

    _extract_mileage(text, ad)
    _extract_registration(text, ad)
    _detect_chassis(text, ad)
    _detect_cellule(text, lower, ad)
    _detect_body_type(lower, ad)
    _detect_seller_type(text, ad)

    chassis_known = ad.detected_chassis in _SUPPORTED_CHASSIS
    cellule_known = ad.detected_cellule in _SUPPORTED_CELLULES

    if chassis_known and cellule_known:
        ad.support_level = "full"
    elif chassis_known:
        ad.support_level = "partial"
        ad.warnings.append(
            f"Cellule {'non reconnue' if not ad.detected_cellule else ad.detected_cellule + ' non couverte par ce prototype'} : "
            "le rapport ci-dessous se limite aux données du châssis (mécanique, prix non évaluable, "
            "pas de réputation étanchéité disponible pour cette marque de cellule)."
        )
    else:
        ad.support_level = "unsupported"
        missing = []
        if not ad.detected_chassis:
            missing.append("châssis non reconnu")
        else:
            missing.append(f"châssis {ad.detected_chassis} (hors scope de ce prototype)")
        if ad.detected_cellule:
            missing.append(f"cellule {ad.detected_cellule}")
        ad.warnings.append(
            "Châssis non reconnu parmi ceux couverts (Fiat Ducato/Citroën Jumper/Peugeot Boxer, "
            "Ford Transit, Renault Master) : " + " ; ".join(missing) + ". Aucun rapport n'est "
            "généré, faute de base mécanique à laquelle rattacher un avis."
        )

    return ad
