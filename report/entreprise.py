"""Client minimal pour l'API ouverte "Recherche d'entreprises"
(recherche-entreprises.api.gouv.fr — données Sirene/INSEE + RNE), utilisé
pour compléter la section "vendeur" quand un numéro SIRET est détecté dans
le texte collé d'une annonce professionnelle.

But : vérifier qu'une entreprise qui se présente comme vendeur professionnel
existe réellement, où et depuis quand — un contrôle anti-arnaque simple
avant d'acheter à un professionnel. Ne concerne que les vendeurs pro : un
particulier n'a pas de SIRET.

Pas de dépendance externe (stdlib uniquement, urllib), pour rester cohérent
avec le reste du prototype.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

_API_URL = "https://recherche-entreprises.api.gouv.fr/search"
_TIMEOUT_SECONDS = 4.0


@dataclass
class EntrepriseInfo:
    raison_sociale: str
    adresse: str | None
    date_creation: str | None
    anciennete_annees: int | None
    etat_administratif: str
    categorie_entreprise: str | None


@dataclass
class EntrepriseResult:
    available: bool
    info: EntrepriseInfo | None


def _format_date(iso_value: str | None) -> str | None:
    if not iso_value:
        return None
    try:
        return datetime.fromisoformat(iso_value).strftime("%d/%m/%Y")
    except ValueError:
        return iso_value


def _anciennete_annees(iso_value: str | None) -> int | None:
    if not iso_value:
        return None
    try:
        creation = datetime.fromisoformat(iso_value)
    except ValueError:
        return None
    return (datetime.now() - creation).days // 365


def fetch_entreprise_info(siret: str) -> EntrepriseResult:
    """Recherche une entreprise par son SIRET via l'API publique.

    Ne lève jamais d'exception : `available=False` signale un échec réseau
    ou une réponse inattendue, à distinguer de `info=None` (l'API a répondu
    mais n'a trouvé aucune entreprise pour ce SIRET).
    """
    params = {"q": siret}
    url = f"{_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "rapport-vigilance-campingcar-prototype/1.0"}
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return EntrepriseResult(available=False, info=None)

    results = payload.get("results") or []
    if not results:
        return EntrepriseResult(available=True, info=None)

    record = results[0]
    siege = record.get("siege") or {}
    date_creation = record.get("date_creation")
    etat = "active" if record.get("etat_administratif") == "A" else "fermée / radiée"

    info = EntrepriseInfo(
        raison_sociale=record.get("nom_complet") or record.get("nom_raison_sociale") or "Nom inconnu",
        adresse=siege.get("adresse"),
        date_creation=_format_date(date_creation),
        anciennete_annees=_anciennete_annees(date_creation),
        etat_administratif=etat,
        categorie_entreprise=record.get("categorie_entreprise"),
    )
    return EntrepriseResult(available=True, info=info)
