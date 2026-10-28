"""Connecteur Bien'ici : point d'acces JSON public utilise par le site (realEstateAds.json).

Bien'ici agrege la majorite des annonces d'agences en France (reseau des professionnels),
sans protection anti-bot agressive sur ce point d'acces. On reste poli : pagination lente,
pas plus de quelques centaines d'annonces par ville et par semaine.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..models import Listing
from .http import get_json, polite_pause, session

log = logging.getLogger(__name__)

SUGGEST_URL = "https://res.bienici.com/suggest.json"
SEARCH_URL = "https://www.bienici.com/realEstateAds.json"
PAGE_SIZE = 60

TYPE_MAP = {"flat": "appartement", "house": "maison", "loft": "loft", "building": "immeuble"}


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def resolve_zone(s, zone: str) -> dict[str, Any] | None:
    """Retourne la premiere suggestion de type ville / arrondissement pour `zone`."""
    data = get_json(s, SUGGEST_URL, params={"q": zone})
    for item in data:
        if item.get("type") in {"city", "arrondissement", "department"} and item.get("zoneIds"):
            return item
    return data[0] if data else None


def _filters(zone_ids: list[str], cfg_r: dict[str, Any], page: int) -> dict[str, Any]:
    return {
        "size": PAGE_SIZE,
        "from": (page - 1) * PAGE_SIZE,
        "showAllModels": False,
        "filterType": "buy",
        "propertyType": cfg_r.get("types_bien", ["flat"]),
        "minPrice": cfg_r.get("prix_min", 0),
        "maxPrice": cfg_r.get("prix_max", 500000),
        "minArea": cfg_r.get("surface_min", 9),
        "minRooms": cfg_r.get("pieces_min", 1),
        "page": page,
        "sortBy": "publicationDate",
        "sortOrder": "desc",
        "onTheMarket": [True],
        "zoneIdsByTypes": {"zoneIds": zone_ids},
    }


def _ad_url(ad: dict[str, Any]) -> str:
    type_slug = TYPE_MAP.get(ad.get("propertyType", "flat"), "appartement")
    pieces = int(ad.get("roomsQuantity") or 1)
    pieces_slug = f"{pieces}piece{'s' if pieces > 1 else ''}"
    return f"https://www.bienici.com/annonce/vente/{_slug(ad.get('city') or 'france')}/{type_slug}/{pieces_slug}/{ad['id']}"


def _bool(v: Any) -> bool:
    return bool(v) if v is not None else False


def normalize(ad: dict[str, Any], zone: str, categorie: str) -> Listing | None:
    try:
        prix = float(ad.get("price") or 0)
        surface = float(ad.get("surfaceArea") or 0)
    except (TypeError, ValueError):
        return None
    if prix <= 0 or surface <= 0:
        return None
    desc = (ad.get("description") or "").strip()
    low = desc.lower()
    loue = bool(re.search(r"\b(loué|loue|occupé|bail en cours|locataire en place)\b", low))
    loyer_actuel = None
    m = re.search(r"(?:loyer|loué|loue)[^0-9]{0,30}([0-9][0-9\s.,]{2,7})\s*(?:€|eur)", low)
    if m:
        try:
            loyer_actuel = float(re.sub(r"[^0-9]", "", m.group(1)))
            if not 150 <= loyer_actuel <= 10000:
                loyer_actuel = None
        except ValueError:
            loyer_actuel = None
    return Listing(
        id=f"bienici:{ad['id']}",
        source="bienici",
        url=_ad_url(ad),
        titre=(ad.get("title") or "").strip(),
        description=desc,
        prix=prix,
        surface=surface,
        pieces=int(ad.get("roomsQuantity") or 1),
        type_bien=ad.get("propertyType") or "flat",
        ville=ad.get("city") or "",
        code_postal=str(ad.get("postalCode") or ""),
        categorie_ville=categorie,
        zone_recherche=zone,
        dpe=ad.get("energyClassification") or None,
        ges=ad.get("greenhouseGazClassification") or None,
        annee_construction=ad.get("yearOfConstruction"),
        etage=ad.get("floor"),
        charges_copro_annuelles=ad.get("annualCondominiumFees"),
        taxe_fonciere=ad.get("propertyTax") or ad.get("landTax"),
        copro_en_procedure=_bool(ad.get("isCondominiumInProcedure")),
        en_copropriete=ad.get("isInCondominium"),
        nb_lots_copro=ad.get("condominiumPartsQuantity"),
        prix_a_baisse=_bool(ad.get("priceHasDecreased")),
        date_publication=ad.get("publicationDate") or "",
        date_modification=ad.get("modificationDate") or "",
        photos=len(ad.get("photos") or []),
        pro=_bool(ad.get("adCreatedByPro")),
        exclusivite=_bool(ad.get("isExclusiveSaleMandate")),
        neuf=_bool(ad.get("newProperty")),
        loue_actuellement=loue,
        loyer_actuel=loyer_actuel if loue else None,
        extra={"reference": ad.get("reference"), "agency_fee_pct": ad.get("agencyFeePercentage"),
               "fees_charged_to": ad.get("feesChargedTo"), "heating": ad.get("heating")},
    )


def fetch_city(zone: str, categorie: str, cfg_r: dict[str, Any], code_postal: str = "") -> list[Listing]:
    s = session()
    sugg = resolve_zone(s, f"{zone} {code_postal}".strip())
    if code_postal and sugg and code_postal not in (sugg.get("postalCodes") or [code_postal]):
        log.warning("Zone %s : la suggestion Bien'ici %s ne porte pas le code postal %s", zone, sugg.get("name"), code_postal)
    if not sugg:
        log.warning("Zone introuvable sur Bien'ici : %s", zone)
        return []
    zone_ids = sugg["zoneIds"]
    max_ads = int(cfg_r.get("max_annonces_par_ville", 120))
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(cfg_r.get("jours_max_publication", 45)))
    out: list[Listing] = []
    page = 1
    while len(out) < max_ads:
        data = get_json(s, SEARCH_URL, params={"filters": json.dumps(_filters(zone_ids, cfg_r, page))})
        ads = data.get("realEstateAds") or []
        if not ads:
            break
        for ad in ads:
            pub = ad.get("publicationDate") or ""
            try:
                if pub and datetime.fromisoformat(pub.replace("Z", "+00:00")) < cutoff:
                    continue
            except ValueError:
                pass
            lst = normalize(ad, zone, categorie)
            if lst:
                out.append(lst)
        total = int(data.get("total") or 0)
        if page * PAGE_SIZE >= total:
            break
        page += 1
        polite_pause()
    log.info("Bien'ici %s : %d annonces retenues (total marche %s)", zone, len(out), data.get("total") if ads else "?")
    return out[:max_ads]


def fetch_all(cfg_r: dict[str, Any]) -> Iterable[Listing]:
    for ville in cfg_r.get("villes", []):
        try:
            yield from fetch_city(ville["zone"], ville.get("categorie", "ville_moyenne"), cfg_r, str(ville.get("cp") or ""))
        except Exception as exc:  # une ville en echec ne doit pas bloquer la semaine
            log.exception("Echec Bien'ici pour %s : %s", ville.get("zone"), exc)
        polite_pause(1.5, 3.0)
