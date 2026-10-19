"""Cessions immobilieres de l'Etat (Domaines / DGFiP) : cessions.immobilier-etat.gouv.fr.

Portail officiel des biens vendus par l'Etat (anciens logements de fonction, maisons forestieres,
immeubles). Les ventes se font par appel d'offres ou encheres ; le prix n'est pas toujours publie
(mise a prix dans la fiche, parfois absente). Les logements sont rares (quelques dizaines en France),
donc on prend toute la France : la categorie de ville est deduite de la population.
"""
from __future__ import annotations

import html as htmlmod
import logging
import re
from typing import Any, Iterable

from ..models import Listing
from .http import polite_pause, session

log = logging.getLogger(__name__)

BASE = "https://cessions.immobilier-etat.gouv.fr"
# Logements (2), Maisons (7), Appartements (8), Immeubles d'habitation (10)
LIST_URL = BASE + "/?field_bien_type_target_id_1%5B2%5D=2&field_bien_type_target_id_1%5B7%5D=7&field_bien_type_target_id_1%5B8%5D=8&field_bien_type_target_id_1%5B10%5D=10&page={page}"

RE_CARD = re.compile(r'<div id="bien-(?P<nid>\d+)"[^>]*data-titre="(?P<titre>[^"]*)"[^>]*data-localisation="(?P<loc>[^"]*)"[^>]*data-type-bien="(?P<type>[^"]*)"[^>]*data-url="(?P<url>[^"]*)"')
RE_PRIX = re.compile(r"(mise [àa] prix|prix de vente|prix plancher|prix de r[ée]serve|prix de d[ée]part|valeur v[ée]nale)[^0-9€]{0,60}?([0-9][0-9 \u202f\u00a0.]{2,})\s*€", re.I)
RE_TF = re.compile(r"taxe fonci[èe]re(?:\s*\d{4})?[^0-9€]{0,40}?([0-9][0-9 \u202f\u00a0.]{2,})\s*€", re.I)
RE_DATE_VENTE = re.compile(r"(?:Date d'adjudication|Date limite[^|]{0,40}|Date de cl[ôo]ture[^|]{0,30})\s*:?\s*\|?\s*(\d{2}/\d{2}/\d{4})")
RE_SURFACE = re.compile(r"Surface en m²\s*\|\s*([0-9]+(?:[,.][0-9]+)?)")
RE_SURFACE2 = re.compile(r"([0-9]{2,4}(?:[,.][0-9]+)?)\s*m²")
RE_INSEE = re.compile(r"Code INSEE\s*\|\s*(\d{5})")
RE_DPE = re.compile(r"Performance énergétique\s*:\s*([A-G])")
RE_JOURS = re.compile(r"Fini dans (\d+) jours?")
RE_CHAMBRES = re.compile(r"Nombre de chambres\s*\|\s*(\d+)")
RE_PROC = re.compile(r"Procédure de vente\s*\|\s*([^|]{3,160})")


def _texte(page: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = re.sub(r"<[^>]+>", "|", t)
    t = htmlmod.unescape(t)
    return re.sub(r"\s*\|[\s|]*", "|", t)


def parse_fiche(page: str) -> dict[str, Any]:
    t = _texte(page)
    out: dict[str, Any] = {}
    m = RE_SURFACE.search(t) or RE_SURFACE2.search(t)
    out["surface"] = float(m.group(1).replace(",", ".")) if m else None
    m = RE_INSEE.search(t)
    out["insee"] = m.group(1) if m else None
    m = RE_DPE.search(t)
    out["dpe"] = m.group(1) if m else None
    m = RE_JOURS.search(t)
    out["jours_restants"] = int(m.group(1)) if m else None
    m = RE_CHAMBRES.search(t)
    out["chambres"] = int(m.group(1)) if m else None
    m = RE_PROC.search(t)
    out["procedure"] = m.group(1).strip() if m else ""
    prix = None
    for label, val in RE_PRIX.findall(t):
        v = float(re.sub(r"[^0-9]", "", val))
        if 10000 <= v <= 20_000_000:
            prix = v
            break  # premiere mention = mise a prix (la consignation vient apres)
    out["prix"] = prix
    m = RE_TF.search(t)
    out["taxe_fonciere"] = float(re.sub(r"[^0-9]", "", m.group(1))) if m else None
    m = RE_DATE_VENTE.search(t)
    out["date_vente"] = f"{m.group(1)[6:]}-{m.group(1)[3:5]}-{m.group(1)[:2]}" if m else ""
    i = t.find("Descriptif du bien")
    out["description"] = t[i + 19:i + 600].replace("|", " ").strip() if i >= 0 else ""
    return out


def _get(s, url: str):
    """GET avec repli sans verification TLS : la chaine de certificats du portail n'est pas reconnue par tous les bundles."""
    import requests
    try:
        return s.get(url, timeout=30)
    except requests.exceptions.SSLError:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        log.warning("Certificat TLS non verifiable pour %s : lecture sans verification (donnees publiques)", url.split("/")[2])
        s.verify = False
        return s.get(url, timeout=30)


CACHE_PATH = None  # fixe par le pipeline : data/cache/etat.json


def _charger_cache(path) -> list[Listing]:
    import json
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for d in data.get("listings", []):
        d.pop("prix_m2", None)
        out.append(Listing(**d))
    age = (__import__("time").time() - data.get("_ts", 0)) / 86400
    log.warning("Cessions de l'Etat : portail inaccessible depuis ce reseau, utilisation du cache (%d biens, %.0f jours). Rafraichir en local : python scripts/run_weekly.py --dry-run --limite 1", len(out), age)
    return out


def _sauver_cache(path, listings: list[Listing]) -> None:
    import json, time
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"_ts": time.time(), "listings": [l.to_dict() for l in listings]}, ensure_ascii=False), encoding="utf-8")


def fetch_all(cfg_r: dict[str, Any], max_pages: int = 6, cache_path=None) -> Iterable[Listing]:
    """Lit le portail ; s'il refuse la connexion (403 hors France), retombe sur le cache versionne."""
    collected: list[Listing] = []
    ok = True
    try:
        for lst in _fetch_live(cfg_r, max_pages):
            collected.append(lst)
    except PermissionError:
        ok = False
    if not ok and cache_path:
        yield from _charger_cache(cache_path)
        return
    if ok and cache_path:
        _sauver_cache(cache_path, collected)
    yield from collected


def _fetch_live(cfg_r: dict[str, Any], max_pages: int = 6) -> Iterable[Listing]:
    s = session()
    s.headers["Accept"] = "text/html,*/*"
    n = 0
    for page_no in range(max_pages):
        try:
            r = _get(s, LIST_URL.format(page=page_no))
            if r.status_code == 403 and page_no == 0:
                raise PermissionError("403 : acces refuse depuis ce reseau")
            r.raise_for_status()
        except PermissionError:
            raise
        except Exception as exc:
            log.warning("cessions.immobilier-etat.gouv.fr : %s", exc)
            break
        cards = list(RE_CARD.finditer(r.text))
        if not cards:
            break
        for c in cards:
            if "logement" not in c.group("type").lower():
                continue  # le filtre de type du portail n'est pas honore : on garde la categorie Logements
            loc = htmlmod.unescape(c.group("loc"))
            ville, _, dep = loc.rpartition(" - ")
            try:
                f = _get(s, BASE + c.group("url"))
                f.raise_for_status()
                fiche = parse_fiche(f.text)
            except Exception as exc:
                log.warning("fiche Etat %s : %s", c.group("url"), exc)
                continue
            polite_pause(0.6, 1.2)
            if not fiche.get("surface") or not 9 <= fiche["surface"] <= 600:
                continue
            type_card = c.group("type").lower()
            tb = "house" if "maison" in type_card or "pavillon" in c.group("titre").lower() or "villa" in c.group("titre").lower() else "flat"
            if "immeuble" in type_card or "immeuble" in c.group("titre").lower():
                tb = "building"
            prix = fiche.get("prix")
            if prix and not (float(cfg_r.get("prix_min", 0)) * 0.5 <= prix <= float(cfg_r.get("prix_max", 1e9)) * 1.5):
                continue
            n += 1
            yield Listing(
                id=f"etat:{c.group('nid')}",
                source="etat",
                url=BASE + c.group("url"),
                titre=f"{htmlmod.unescape(c.group('titre'))} (bien de l'Etat)",
                description=f"{fiche.get('procedure') or 'Procedure non precisee'}. {fiche.get('description') or ''}".strip(),
                prix=prix or 0.0,                   # 0 = prix non communique : estime par DVF dans l'analyse
                surface=fiche["surface"],
                pieces=(fiche.get("chambres") or 1) + 1,
                type_bien=tb,
                ville=ville.strip().title(),
                code_postal="",
                categorie_ville="a_determiner",
                zone_recherche="France (Etat)",
                dpe=fiche.get("dpe"),
                taxe_fonciere=fiche.get("taxe_fonciere"),
                mode_vente="cession_etat",
                mise_a_prix=prix,
                date_vente=fiche.get("date_vente") or "",
                extra={"insee": fiche.get("insee"), "departement": dep.strip(), "jours_restants": fiche.get("jours_restants"),
                       "procedure": fiche.get("procedure"), "type_portail": c.group("type")},
            )
        polite_pause(0.8, 1.5)
    log.info("Cessions de l'Etat : %d logements retenus", n)
