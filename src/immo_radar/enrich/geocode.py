"""Resolution code postal + ville -> code INSEE (api-adresse.data.gouv.fr), avec arrondissements PLM."""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from ..sources.http import get_json, session

log = logging.getLogger(__name__)
APIS = ["https://data.geopf.fr/geocodage/search", "https://api-adresse.data.gouv.fr/search/"]


def arrondissement_insee(code_postal: str) -> str | None:
    """Paris 750XX -> 751XX ; Lyon 6900X -> 6938X ; Marseille 130XX -> 132XX."""
    cp = (code_postal or "").strip()
    if re.fullmatch(r"750(0[1-9]|1\d|20)", cp):
        return "751" + cp[3:]
    if re.fullmatch(r"7511[6]", cp):
        return "75116"
    if re.fullmatch(r"6900[1-9]", cp):
        return "6938" + cp[4]
    if re.fullmatch(r"130(0[1-9]|1[0-6])", cp):
        return "132" + cp[3:]
    return None


def arrondissement_depuis_nom(ville: str) -> str | None:
    """'Lyon 3ème' -> 69383 ; 'Paris 15e' -> 75115 ; 'Marseille 11' -> 13211."""
    m = re.match(r"^\s*(paris|lyon|marseille)\s+(\d{1,2})\s*(?:er|e|eme|ème|e arrondissement|ème arrondissement)?\s*(?:arrondissement)?\s*$", (ville or "").lower())
    if not m:
        return None
    n = int(m.group(2))
    if m.group(1) == "paris" and 1 <= n <= 20:
        return f"751{n:02d}"
    if m.group(1) == "lyon" and 1 <= n <= 9:
        return f"6938{n}"
    if m.group(1) == "marseille" and 1 <= n <= 16:
        return f"132{n:02d}"
    return None


@lru_cache(maxsize=4096)
def resolve(code_postal: str, ville: str) -> tuple[str | None, str | None, int | None]:
    """Retourne (code_insee, nom_commune, population)."""
    arr = arrondissement_insee(code_postal) or arrondissement_depuis_nom(ville)
    if arr:
        return arr, ville, None
    s = session()
    q = f"{code_postal} {ville}".strip()
    for api in APIS:
        try:
            data = get_json(s, api, params={"q": q, "type": "municipality", "limit": 1}, retries=2)
            feats = data.get("features") or []
            if not feats and code_postal and ville:
                data = get_json(s, api, params={"q": ville, "postcode": code_postal, "type": "municipality", "limit": 1}, retries=2)
                feats = data.get("features") or []
            if feats:
                p = feats[0]["properties"]
                return p.get("citycode"), p.get("city") or p.get("name"), p.get("population")
        except Exception as exc:
            log.warning("Geocodage %s impossible pour %s : %s", api, q, exc)
    return None, ville, None


def resolve_zone(zone: str) -> tuple[str | None, str | None, int | None]:
    """Code INSEE d'une ville cible de la config (sans code postal)."""
    return resolve("", zone)
