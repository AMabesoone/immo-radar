"""Marche de la location courte duree : Inside Airbnb (Paris, Lyon, Bordeaux, Pays basque).

Pour chaque ville couverte, on telecharge listings.csv.gz, on garde les logements entiers actifs,
puis on agrege par quartier et par nombre de chambres : prix median par nuit (ADR) et taux
d'occupation estime selon le modele Inside Airbnb (avis des 12 derniers mois / taux d'avis 50 %
x duree moyenne de sejour, plafonne a 70 %).

Les agregats sont stockes dans data/cache/str_markets.json et rafraichis tous les 45 jours.
Pour les villes non couvertes, le pipeline retombe sur les hypotheses par categorie de ville.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import re
import statistics
import time
import unicodedata
from pathlib import Path

import requests

log = logging.getLogger(__name__)

INDEX_URL = "https://insideairbnb.com/get-the-data/"
TTL_S = 45 * 86400
REVIEW_RATE = 0.5
OCC_CAP = 0.70
SEJOUR_MOYEN_NUITS = 3.5

PARIS_ARR = {
    "louvre": "75101", "bourse": "75102", "temple": "75103", "hotel-de-ville": "75104", "pantheon": "75105",
    "luxembourg": "75106", "palais-bourbon": "75107", "elysee": "75108", "opera": "75109", "entrepot": "75110",
    "popincourt": "75111", "reuilly": "75112", "gobelins": "75113", "observatoire": "75114", "vaugirard": "75115",
    "passy": "75116", "batignolles-monceau": "75117", "buttes-montmartre": "75118", "buttes-chaumont": "75119",
    "menilmontant": "75120",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _zone_key(city: str, neighbourhood: str) -> str:
    n = _norm(neighbourhood)
    if city == "paris" and n in PARIS_ARR:
        return PARIS_ARR[n]
    m = re.match(r"(\d+)(?:er|e|eme)-arrondissement", n)
    if city == "lyon" and m:
        return f"6938{m.group(1)}"
    return f"{city}:{n}"


def _bedroom_bucket(v: str) -> str:
    try:
        b = int(float(v))
    except (TypeError, ValueError):
        return "1"
    return "0" if b == 0 else "1" if b == 1 else "2" if b == 2 else "3+"


class MarcheCourteDuree:
    def __init__(self, cache_dir: str | Path):
        self.path = Path(cache_dir) / "str_markets.json"
        self.data: dict = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def _discover(self) -> dict[str, str]:
        html = requests.get(INDEX_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).content.decode("utf-8", errors="ignore")
        urls = set(re.findall(r"https://data\.insideairbnb\.com/france/[^\"']+/listings\.csv\.gz", html))
        out: dict[str, str] = {}
        for u in urls:
            city = u.split("/france/")[1].split("/")[1]
            if city not in out or u > out[city]:
                out[city] = u
        return out

    def refresh(self, force: bool = False) -> None:
        if not force and self.data and time.time() - self.data.get("_ts", 0) < TTL_S:
            return
        try:
            cities = self._discover()
        except Exception as exc:
            log.warning("Inside Airbnb indisponible : %s", exc)
            return
        zones: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for city, url in cities.items():
            try:
                log.info("Inside Airbnb : %s", url)
                raw = requests.get(requests.utils.requote_uri(url), timeout=300, headers={"User-Agent": "Mozilla/5.0"}).content
                text = gzip.decompress(raw).decode("utf-8", errors="ignore")
            except Exception as exc:
                log.warning("Echec Inside Airbnb %s : %s", city, exc)
                continue
            for row in csv.DictReader(io.StringIO(text)):
                if row.get("room_type") != "Entire home/apt":
                    continue
                try:
                    price = float(re.sub(r"[^0-9.]", "", row.get("price") or ""))
                    reviews = float(row.get("number_of_reviews_ltm") or 0)
                    min_n = float(row.get("minimum_nights") or 1)
                except ValueError:
                    continue
                if not 20 <= price <= 1500 or reviews <= 0 or min_n > 30:
                    continue
                nuits = reviews / REVIEW_RATE * max(SEJOUR_MOYEN_NUITS, min_n)
                occ = min(nuits / 365.0, OCC_CAP)
                zk = _zone_key(city, row.get("neighbourhood_cleansed") or "")
                bk = _bedroom_bucket(row.get("bedrooms") or "")
                zones.setdefault(zk, {}).setdefault(bk, []).append((price, occ))
                zones.setdefault(f"{city}:*", {}).setdefault(bk, []).append((price, occ))
        agg: dict = {"_ts": time.time(), "zones": {}}
        for zk, buckets in zones.items():
            agg["zones"][zk] = {}
            for bk, vals in buckets.items():
                if len(vals) < 8:
                    continue
                occs = sorted(o for _, o in vals)
                # Mediane = hote occasionnel ; 3e quartile = logement gere professionnellement (pricing dynamique,
                # conciergerie), ce qui correspond a un investisseur. On retient le 3e quartile, borne a 35-70 %.
                p75 = occs[int(len(occs) * 0.75)]
                agg["zones"][zk][bk] = {
                    "adr": statistics.median(p for p, _ in vals),
                    "occupation": min(max(p75, 0.35), OCC_CAP),
                    "occupation_mediane": statistics.median(occs),
                    "n": len(vals),
                }
        self.data = agg
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(agg))

    def lookup(self, code_insee: str | None, ville: str, pieces: int) -> dict | None:
        zones = self.data.get("zones") or {}
        bk = "0" if pieces <= 1 else "1" if pieces == 2 else "2" if pieces == 3 else "3+"
        candidates = []
        if code_insee:
            candidates.append(code_insee)
        n = _norm(ville)
        for city in ("paris", "lyon", "bordeaux", "pays-basque"):
            candidates.append(f"{city}:{n}")
        if n.startswith("paris"):
            candidates.append("paris:*")
        if n.startswith("lyon"):
            candidates.append("lyon:*")
        if n.startswith("bordeaux"):
            candidates.append("bordeaux:*")
        for zk in candidates:
            z = zones.get(zk)
            if z and bk in z:
                res = dict(z[bk])
                res["zone"] = zk
                return res
        return None
