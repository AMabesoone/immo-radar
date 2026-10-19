"""Connecteur immobilier.notaires.fr : API JSON publique du Conseil superieur du notariat.

Filtre par departement (le filtre commune n'est pas honore), puis on ne garde que les communes
cibles via le code INSEE. Volume faible, mais biens de succession et prix justes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..models import Listing
from .http import get_json, polite_pause, session

log = logging.getLogger(__name__)

API = "https://www.immobilier.notaires.fr/pub-services/inotr-www-annonces/v1/annonces"
TYPE_MAP = {"flat": "APP", "house": "MAI", "building": "IMM"}
TYPE_BACK = {"APP": "flat", "MAI": "house", "IMM": "building"}
TITRE_FR = {"APP": "Appartement", "MAI": "Maison", "IMM": "Immeuble"}


def normalize(a: dict[str, Any], zone: str, categorie: str) -> Listing | None:
    try:
        prix = float(a.get("prixTotal") or a.get("prixAffiche") or 0)
        surface = float(a.get("surface") or 0)
    except (TypeError, ValueError):
        return None
    if prix <= 0 or surface <= 0 or a.get("viager") == "OUI":
        return None
    if a.get("typeBien") not in TYPE_BACK:  # l'API ne respecte pas le filtre typeBien : terrains, locaux, garages
        return None
    desc = (a.get("descriptionFr") or "").strip()
    return Listing(
        id=f"notaires:{a.get('annonceId') or a.get('id')}",
        source="notaires",
        url=a.get("urlDetailAnnonceFr") or "",
        titre=f"{TITRE_FR.get(a.get('typeBien'), 'Bien')} {a.get('nbPieces') or ''} pieces a {a.get('communeNom') or ''} (notaire)".replace("  ", " "),
        description=desc,
        prix=prix,
        surface=surface,
        pieces=int(a.get("nbPieces") or 1),
        type_bien=TYPE_BACK.get(a.get("typeBien"), "flat"),
        ville=a.get("communeNom") or "",
        code_postal=str(a.get("codePostal") or ""),
        categorie_ville=categorie,
        zone_recherche=zone,
        neuf=a.get("ancienNeuf") == "NEUF",
        prix_a_baisse=a.get("variation") == "BAISSE",
        date_publication=a.get("dateCreation") or "",
        date_modification=a.get("dateMaj") or "",
        photos=int(a.get("nbPhoto") or 0),
        pro=True,
        extra={"emoluments": a.get("emoluments"), "insee": a.get("inseeCommune"), "judiciaire": a.get("origineJudiciaire"),
               "vente_interactive": a.get("typeAdjudication")},
    )


def fetch_departement(dep: str, communes_insee: dict[str, tuple[str, str]], cfg_r: dict[str, Any]) -> list[Listing]:
    """communes_insee : {code_insee: (zone, categorie)} des villes cibles du departement."""
    s = session()
    out: list[Listing] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(cfg_r.get("jours_max_publication", 45)) * 3)  # les biens notaires restent longtemps
    for type_bien in cfg_r.get("types_bien", ["flat"]):
        code = TYPE_MAP.get(type_bien)
        if not code:
            continue
        page = 1
        while page <= 10:
            params = {"page": page, "parPage": 50, "perimetre": 0, "typeTransaction": "VENTE", "typeBien": code, "departements": dep,
                      "prixMin": cfg_r.get("prix_min", 0), "prixMax": cfg_r.get("prix_max", 10**7)}
            try:
                data = get_json(s, API, params=params)
            except Exception as exc:
                log.warning("Notaires dep %s : %s", dep, exc)
                break
            ads = data.get("annonceResumeDto") or []
            for a in ads:
                insee = str(a.get("inseeCommune") or "")
                if insee not in communes_insee:
                    continue
                try:
                    if a.get("dateMaj") and datetime.fromisoformat(a["dateMaj"].replace("Z", "+00:00")) < cutoff:
                        continue
                except ValueError:
                    pass
                zone, cat = communes_insee[insee]
                if TYPE_BACK.get(a.get("typeBien")) not in cfg_r.get("types_bien", ["flat"]):
                    continue
                lst = normalize(a, zone, cat)
                if lst:
                    out.append(lst)
            if page >= int(data.get("nbPages") or 1):
                break
            page += 1
            polite_pause(0.5, 1.2)
    log.info("Notaires dep %s : %d annonces dans les communes cibles", dep, len(out))
    return out


def fetch_all(cfg_r: dict[str, Any], resolver) -> Iterable[Listing]:
    """resolver(zone) -> (code_insee, nom, population) ; regroupe les villes par departement."""
    par_dep: dict[str, dict[str, tuple[str, str]]] = {}
    for ville in cfg_r.get("villes", []):
        insee, _, _ = resolver(ville["zone"])
        if not insee:
            continue
        dep = insee[:3] if insee.startswith("97") else insee[:2]
        par_dep.setdefault(dep, {})[insee] = (ville["zone"], ville.get("categorie", "ville_moyenne"))
        # Paris / Lyon / Marseille : les annonces portent le code de l'arrondissement
        if insee in {"75056", "69123", "13055"}:
            prefix = {"75056": "751", "69123": "6938", "13055": "132"}[insee]
            for i in range(1, 21):
                par_dep[dep][f"{prefix}{i:02d}" if prefix != "6938" else f"{prefix}{i}"] = (ville["zone"], ville.get("categorie", "metropole"))
    for dep, communes in par_dep.items():
        try:
            yield from fetch_departement(dep, communes, cfg_r)
        except Exception as exc:
            log.exception("Echec notaires pour le departement %s : %s", dep, exc)
