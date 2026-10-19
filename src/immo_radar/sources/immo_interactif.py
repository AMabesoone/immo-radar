"""Ventes notariales interactives (encheres en ligne des notaires) : api.immo-interactif.fr.

L'API publique utilisee par le site renvoie les ventes en cours et a venir avec type, commune,
code postal, surface, nombre de pieces, premiere offre possible et date d'ouverture des offres.
La premiere offre est un prix d'appel (souvent 10 a 30 % sous le marche) ; le prix final se
rapproche du marche. L'analyse applique un coefficient et plafonne par la valeur DVF.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from ..models import Listing
from .http import polite_pause, session

log = logging.getLogger(__name__)

API = "https://api.immo-interactif.fr/public/property-ads/search"
TYPE_BACK = {"APP": "flat", "MAI": "house", "IMM": "building"}
TITRE = {"APP": "Appartement", "MAI": "Maison", "IMM": "Immeuble"}


def normalize(a: dict[str, Any], zone: str, categorie: str) -> Listing | None:
    tb = TYPE_BACK.get(a.get("propertyType"))
    try:
        prix = float(a.get("firstOfferAmount") or 0)
        surface = float(a.get("area") or 0)
    except (TypeError, ValueError):
        return None
    if not tb or prix <= 0 or surface < 9:
        return None
    ville = (a.get("localityName") or "").title()
    return Listing(
        id=f"vni:{a.get('reference') or a.get('urlSeo')}",
        source="immo_interactif",
        url="https://www.immo-interactif.fr/" + (a.get("urlSeo") or ""),
        titre=f"{TITRE.get(a.get('propertyType'), 'Bien')} {a.get('nbRooms') or ''} pieces en vente interactive, {ville}".replace("  ", " "),
        description=a.get("address") or "",
        prix=prix,
        surface=surface,
        pieces=int(a.get("nbRooms") or 1),
        type_bien=tb,
        ville=ville,
        code_postal=str(a.get("postalCode") or ""),
        categorie_ville=categorie,
        zone_recherche=zone,
        date_publication=a.get("offerStartDate") or "",
        pro=True,
        mode_vente="vente_interactive",
        mise_a_prix=prix,
        date_vente=(a.get("offerStartDate") or "")[:10],
        extra={"statut": a.get("vniStatus"), "reference": a.get("reference")},
    )


def fetch_all(cfg_r: dict[str, Any], departements_cibles: dict[str, tuple[str, str]]) -> Iterable[Listing]:
    """departements_cibles : {code_departement: (zone, categorie)} ; on garde les biens de ces departements."""
    s = session()
    s.headers.update({"Origin": "https://www.immo-interactif.fr", "Referer": "https://www.immo-interactif.fr/", "Content-Type": "application/json"})
    offset, limit, total = 0, 50, 0
    while offset < 1000:
        try:
            r = s.post(API, params={"offset": offset, "limit": limit}, json={"statuses": ["IN_PROGRESS", "INCOMING"], "order": "START_DATE_ASC"}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            log.warning("immo-interactif : %s", exc)
            break
        items = data.get("items") or []
        if not items:
            break
        for a in items:
            cp = str(a.get("postalCode") or "")
            dep = cp[:3] if cp.startswith("97") else cp[:2]
            if dep not in departements_cibles:
                continue
            zone, cat = departements_cibles[dep]
            ville_norm = (a.get("localityName") or "").lower().split()[0] if a.get("localityName") else ""
            if ville_norm != zone.lower().split()[0]:
                cat = "a_determiner"  # commune du departement hors ville cible : categorie par population
            prix = a.get("firstOfferAmount") or 0
            if not (float(cfg_r.get("prix_min", 0)) * 0.5 <= prix <= float(cfg_r.get("prix_max", 1e9))):
                continue
            lst = normalize(a, zone, cat)
            if lst:
                total += 1
                yield lst
        if len(items) < limit:
            break
        offset += limit
        polite_pause(0.5, 1.0)
    log.info("immo-interactif : %d ventes interactives dans les departements cibles", total)
