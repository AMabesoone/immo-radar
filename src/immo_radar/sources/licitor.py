"""Ventes judiciaires immobilieres (biens saisis vendus aux encheres) : licitor.com.

Licitor publie les annonces legales des ventes aux encheres des tribunaux judiciaires. La page d'accueil
liste les prochaines audiences par tribunal ; chaque page d'audience liste les lots avec departement,
commune, nature du bien, surface, description, mise a prix et lien vers l'annonce complete
(cahier des conditions de vente, PV descriptif, avocat poursuivant).

On ne lit que les pages d'audience des tribunaux des villes cibles (quelques dizaines de requetes
par semaine), sans reproduire les descriptions : lien vers l'annonce d'origine.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from typing import Any, Iterable

from ..models import Listing
from .http import polite_pause, session

log = logging.getLogger(__name__)

HOME = "https://www.licitor.com/"
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}

RE_AUDIENCE = re.compile(r'href="(/ventes-judiciaires-immobilieres/(tj-[a-z0-9-]+)/([a-z]+-(\d{1,2})(?:er)?-([a-z]+)-(\d{4}))\.html)"')
RE_AD_URL = re.compile(r'<a class="Ad[^"]*" href="(?P<url>/annonce/[^"]+)"')
RE_FIELD = {
    "dep": re.compile(r'<span class="Number">([^<]*)</span>'),
    "city": re.compile(r'<span class="City">([^<]*)</span>'),
    "name": re.compile(r'<span class="Name">([^<]*)</span>'),
    "text": re.compile(r'<span class="Text">(.*?)</span>', re.S),
    "price": re.compile(r'<span class="PriceNumber">([^<]*)</span>'),
}
RE_SURFACE = re.compile(
    r"(?:\bde|d'une\s+surface\s+(?:habitable\s+)?de|superficie(?:\s+habitable)?\s*:?|surface(?:\s+(?:habitable|carrez|loi\s+carrez|totale|utile))?\s*(?:de|:)?|d'environ|environ)"
    r"\s*([0-9]{1,4}(?:[,.][0-9]{1,2})?)\s*m[²2]", re.I)
RE_PIECES = re.compile(r"\b(\d{1,2}|une?|deux|trois|quatre|cinq|six|sept|huit)\s*(?:pieces?|pièces?|chambres?)\b", re.I)
RE_PAGE_TOTAL = re.compile(r'PageTotal.*?/</span>\s*(\d+)', re.S)
NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8}
# surface par piece principale retenue quand l'annonce ne donne pas la surface (a verifier dans le PV descriptif)
SURFACE_PAR_PIECE = {"flat": 20.0, "house": 25.0, "building": 30.0}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _type_bien(name: str) -> str | None:
    n = slug(name)
    if "appartement" in n or "studio" in n or "duplex" in n or "logement" in n or "usage-d-habitation" in n and "local" in n:
        return "flat"
    if "maison" in n or "villa" in n or "pavillon" in n:
        return "house"
    if "immeuble" in n:
        return "building"
    return None  # terrains, locaux, parkings, caves


def _prix(text: str) -> float | None:
    digits = re.sub(r"[^0-9]", "", text or "")
    return float(digits) if digits else None


def audiences(html: str) -> list[tuple[str, str, date]]:
    """Retourne [(url, tribunal_slug, date_audience)] depuis la page d'accueil."""
    out = []
    for url, tj, _slug, jour, mois, annee in RE_AUDIENCE.findall(html):
        m = MOIS.get(mois)
        if not m:
            continue
        try:
            out.append((url, tj, date(int(annee), m, int(jour))))
        except ValueError:
            continue
    return sorted(set(out), key=lambda x: x[2])


def parse_audience(html: str, url_page: str, tj: str, date_audience: date) -> list[dict[str, Any]]:
    """Decoupe la liste par bloc <a class="Ad ...> ... </a> et extrait les champs de chaque lot."""
    ads = []
    blocs = re.split(r'(?=<a class="Ad[^"]*" href="/annonce/)', html)
    for bloc in blocs:
        m = RE_AD_URL.match(bloc)
        if not m:
            continue
        bloc = bloc.split("</a>", 1)[0]
        champs = {k: (rx.search(bloc).group(1) if rx.search(bloc) else "") for k, rx in RE_FIELD.items()}
        text = re.sub(r"<[^>]+>", " ", champs["text"])
        text = re.sub(r"\s+", " ", text).strip()
        surf = RE_SURFACE.search(text)
        ads.append({
            "url": "https://www.licitor.com" + m.group("url"),
            "dep": champs["dep"].strip(),
            "city": champs["city"].strip(),
            "name": champs["name"].strip(),
            "text": text,
            "surface": float(surf.group(1).replace(",", ".")) if surf else None,
            "mise_a_prix": _prix(champs["price"]),
            "tj": tj,
            "date_audience": date_audience,
            "page": url_page,
        })
    return ads


def _pieces(text: str) -> int | None:
    """Nombre de pieces principales : 'deux pieces principales' -> 2 ; 'trois chambres' -> 4 (chambres + sejour)."""
    m = RE_PIECES.search(text)
    if not m:
        return None
    raw = m.group(1).lower()
    n = int(raw) if raw.isdigit() else NOMBRES.get(raw, 1)
    if "chambre" in m.group(0).lower():
        n += 1
    return max(n, 1)


def to_listing(ad: dict[str, Any], zone: str, categorie: str) -> Listing | None:
    tb = _type_bien(ad["name"])
    if not tb or not ad.get("mise_a_prix"):
        return None
    surface = ad.get("surface")
    pieces = _pieces(ad["text"])
    surface_estimee = False
    if not surface:
        # Licitor ne publie la surface que dans le PV descriptif : on l'estime par le nombre de pieces pour ne pas
        # perdre le lot, et on le signale (red flag + checklist). Sans pieces ni surface, le lot n'est pas analysable.
        if not pieces:
            return None
        surface = pieces * SURFACE_PAR_PIECE[tb]
        surface_estimee = True
    if surface < 9:
        return None
    low = ad["text"].lower()
    occupe = bool(re.search(r"occup|loué|loue|bail", low)) and not re.search(r"\blibre\b", low)
    if pieces is None:
        pieces = max(1, round(surface / 25))
    ref = ad["url"].rstrip(".html").split("/")[-1]
    description = ad["text"]
    if surface_estimee:
        description = f"Surface non communiquee dans l'annonce : estimee a {surface:.0f} m2 ({pieces} pieces), a verifier dans le PV descriptif. " + description
    return Listing(
        id=f"licitor:{ref}",
        source="licitor",
        url=ad["url"],
        titre=f"{ad['name']} aux encheres, {ad['city']} (TJ {ad['tj'][3:].replace('-', ' ').title()}, {ad['date_audience']:%d/%m/%Y})",
        description=description,
        prix=ad["mise_a_prix"],          # remplace par le prix d'adjudication attendu dans l'analyse
        surface=surface,
        pieces=pieces,
        type_bien=tb,
        ville=ad["city"],
        code_postal="",
        categorie_ville=categorie,
        zone_recherche=zone,
        date_publication=ad["date_audience"].isoformat(),
        pro=True,
        mode_vente="enchere_judiciaire",
        mise_a_prix=ad["mise_a_prix"],
        date_vente=ad["date_audience"].isoformat(),
        occupe=occupe,
        extra={"tribunal": ad["tj"], "departement": ad["dep"], "page_audience": ad["page"], "surface_estimee": surface_estimee},
    )


def fetch_audience(s, url: str, tj: str, d: date, max_pages: int = 10) -> list[dict[str, Any]]:
    """Lit toutes les pages d'une audience (?p=2, ?p=3... : les gros tribunaux comme Paris en ont plusieurs)."""
    ads: list[dict[str, Any]] = []
    page = s.get("https://www.licitor.com" + url, timeout=30)
    page.raise_for_status()
    ads += parse_audience(page.text, url, tj, d)
    m = RE_PAGE_TOTAL.search(page.text)
    total = min(int(m.group(1)), max_pages) if m else 1
    for p in range(2, total + 1):
        polite_pause(0.8, 1.6)
        suite = s.get(f"https://www.licitor.com{url}?p={p}", timeout=30)
        suite.raise_for_status()
        ads += parse_audience(suite.text, url, tj, d)
    vus: set[str] = set()
    uniques = []
    for ad in ads:  # un meme lot peut apparaitre sur deux pages consecutives
        cle = ad["url"] + "|" + ad["text"][:60]
        if cle not in vus:
            vus.add(cle)
            uniques.append(ad)
    return uniques


def fetch_all(cfg_r: dict[str, Any], cfg_sp: dict[str, Any]) -> Iterable[Listing]:
    s = session()
    try:
        r = s.get(HOME, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        log.warning("Licitor indisponible : %s", exc)
        return
    home = r.text
    today = date.today()
    cibles = {slug(v["zone"]): v for v in cfg_r.get("villes", [])}
    extra_tj = {slug(t): t for t in cfg_sp.get("tribunaux_supplementaires", [])}
    n_pages = 0
    for url, tj, d in audiences(home):
        if d < today:
            continue
        ville = tj[3:]
        cible = cibles.get(ville)
        if not cible and ville not in extra_tj:
            continue
        zone = cible["zone"] if cible else ville.replace("-", " ").title()
        categorie = cible.get("categorie", "ville_moyenne") if cible else "ville_moyenne"
        try:
            ads = fetch_audience(s, url, tj, d)
        except Exception as exc:
            log.warning("Licitor %s : %s", url, exc)
            continue
        n_pages += 1
        n = 0
        for ad in ads:
            # on garde la ville cible elle-meme et son agglomeration (meme departement) ; la categorie
            # est corrigee ensuite par la population reelle de la commune
            lst = to_listing(ad, zone, categorie if slug(ad["city"]).startswith(slug(zone)) else "a_determiner")
            if lst:
                n += 1
                yield lst
        log.info("Licitor %s %s : %d lots, %d retenus", tj, d, len(ads), n)
        polite_pause(1.0, 2.5)
    log.info("Licitor : %d pages d'audience lues", n_pages)
