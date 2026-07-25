"""Client minimal pour l'API ouverte RappelConso (DGCCRF, data.economie.gouv.fr).

Utilisé pour compléter la section "rappel constructeur" avec les campagnes
réellement publiées pour le châssis détecté, en plus du texte statique déjà
présent dans knowledge/chassis/*.json. Best-effort uniquement : l'API reste
interrogée par marque/modèle (pas par VIN), donc ça ne certifie jamais qu'un
véhicule précis est concerné — voir le message "important" déjà affiché.

Pas de dépendance externe (stdlib uniquement, urllib), pour rester cohérent
avec le reste du prototype.
"""

from __future__ import annotations

import json
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

_API_URL = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "rappelconso-v2-gtin-espaces/records"
)
_TIMEOUT_SECONDS = 4.0
_MAX_RESULTS = 5


@dataclass
class RecallItem:
    date_publication: str | None
    marque: str
    modele: str
    motif: str
    risque: str
    url: str


@dataclass
class RappelConsoResult:
    available: bool
    items: list[RecallItem]


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _format_date(iso_value: str | None) -> str | None:
    if not iso_value:
        return None
    try:
        return datetime.fromisoformat(iso_value).strftime("%d/%m/%Y")
    except ValueError:
        return iso_value


def fetch_recent_recalls(marque: str, modele: str, limit: int = _MAX_RESULTS) -> RappelConsoResult:
    """Interroge RappelConso pour une marque/modèle de châssis donné.

    Ne lève jamais d'exception : `available=False` signale un échec réseau
    ou une réponse inattendue de l'API, à distinguer d'une liste vide
    (l'API a répondu, mais aucun rappel trouvé pour ce modèle).
    """
    where = f'search(marque_produit,"{marque}") and search(modeles_ou_references,"{modele}")'
    params = {
        "where": where,
        "select": (
            "date_publication,marque_produit,modeles_ou_references,"
            "motif_rappel,risques_encourus,lien_vers_la_fiche_rappel"
        ),
        "order_by": "date_publication desc",
        "limit": str(limit),
    }
    url = f"{_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "rapport-vigilance-campingcar-prototype/1.0"}
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return RappelConsoResult(available=False, items=[])

    # L'API fait de la recherche plein texte (avec un radical), pas une
    # correspondance exacte : une requête "jumper" peut par exemple renvoyer
    # un résultat "Jumpy" (autre modèle Citroën). Filtre de sécurité côté
    # client avant affichage, pour ne jamais montrer le mauvais modèle.
    modele_needle = _normalize(modele)
    items: list[RecallItem] = []
    for record in payload.get("results", []):
        modele_value = record.get("modeles_ou_references") or ""
        if modele_needle not in _normalize(modele_value):
            continue
        items.append(
            RecallItem(
                date_publication=_format_date(record.get("date_publication")),
                marque=(record.get("marque_produit") or marque).title(),
                modele=modele_value,
                motif=record.get("motif_rappel") or "",
                risque=record.get("risques_encourus") or "",
                url=record.get("lien_vers_la_fiche_rappel") or "https://rappel.conso.gouv.fr/",
            )
        )

    return RappelConsoResult(available=True, items=items)
