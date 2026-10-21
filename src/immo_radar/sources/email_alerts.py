"""Alertes e-mail des portails (Leboncoin, SeLoger, PAP, Logic-Immo, Jinka...) lues en IMAP.

Principe : tu crees des recherches sauvegardees sur les portails avec alerte e-mail vers une boite
dediee ; le pipeline lit les mails non lus (IMAP, lecture seule + marquage "lu"), extrait les annonces
(lien, titre, prix, ville, surface, pieces) et les passe dans l'analyse 360. Aucun robot ne visite
les portails : ce sont eux qui envoient la donnee.

Secrets attendus (variables d'environnement) : IMAP_USER, IMAP_PASSWORD (mot de passe d'application
Gmail), optionnellement IMAP_HOST (imap.gmail.com par defaut).

Les annonces extraites sont conservees dans data/cache/alertes_email.json pendant `retention_jours`
jours, car un e-mail n'est lu qu'une fois alors que l'annonce doit rester analysee plusieurs semaines.
"""
from __future__ import annotations

import email
import html as htmlmod
import imaplib
import json
import logging
import os
import re
import time
from email.header import decode_header
from pathlib import Path
from typing import Any, Iterable

from ..models import Listing

log = logging.getLogger(__name__)

# Portails reconnus : (motif d'expediteur ou de lien, nom de source, regex des liens d'annonce)
PORTAILS = [
    ("leboncoin", "leboncoin", re.compile(r"https?://(?:www\.)?leboncoin\.fr/(?:ad/)?[a-z_]*/?(\d{6,})(?:\.htm)?[^\s\"'<>]*", re.I)),
    ("seloger", "seloger", re.compile(r"https?://(?:www\.)?seloger\.com/annonces/[^\s\"'<>]*?(\d{6,})[^\s\"'<>]*", re.I)),
    ("pap.fr", "pap", re.compile(r"https?://(?:www\.)?pap\.fr/annonces?/[^\s\"'<>]*?(r\d{6,}|\d{6,})[^\s\"'<>]*", re.I)),
    ("logic-immo", "logic_immo", re.compile(r"https?://(?:www\.)?logic-immo\.com/[^\s\"'<>]*?(\d{6,})[^\s\"'<>]*", re.I)),
    ("jinka", "jinka", re.compile(r"https?://(?:www\.)?jinka\.fr/ad/([0-9a-f-]{36})[^\s\"'<>]*", re.I)),
    ("bienici", "bienici_email", re.compile(r"https?://(?:www\.)?bienici\.com/annonce/[^\s\"'<>]*?/([a-z0-9-]+-\d{5,})[^\s\"'<>]*", re.I)),
]

RE_PRIX = re.compile(r"(\d{1,3}(?:[   .]\d{3}){1,2}|\d{5,7})\s*(?:€|EUR|euros?)", re.I)
RE_SURFACE = re.compile(r"(\d{2,4}(?:[,.]\d)?)\s*m(?:²|2|\s*carr)", re.I)
RE_PIECES = re.compile(r"(\d{1,2})\s*(?:pi[eè]ces?|p\.|P\b)", re.I)
RE_CP = re.compile(r"\b(\d{5})\b")
RE_VILLE_CP = re.compile(r"([A-ZÀ-Üa-zà-ü' -]{2,40})\s*\(?(\d{5})\)?")
RE_DPE = re.compile(r"\b(?:DPE|classe énergie|classe energie)\s*:?\s*([A-G])\b", re.I)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        out.append(text.decode(enc or "utf-8", errors="ignore") if isinstance(text, bytes) else text)
    return "".join(out)


def _html_to_blocks(html: str) -> str:
    """Texte brut avec des sauts de ligne aux frontieres de blocs, liens conserves sous la forme [URL]."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S | re.I)
    t = re.sub(r'<a\s[^>]*href="([^"]+)"[^>]*>', r" [\1] ", t, flags=re.I)
    t = re.sub(r"<(?:br|/p|/div|/tr|/li|/h\d|/td)[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"[ \t  ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def _type_bien(text: str) -> str:
    low = text.lower()
    if "immeuble" in low:
        return "building"
    if "maison" in low or "villa" in low or "pavillon" in low or "longère" in low or "longere" in low:
        return "house"
    return "flat"


def extraire_annonces(html: str, source_hint: str = "") -> list[dict[str, Any]]:
    """Extrait les annonces d'un e-mail d'alerte.

    Le texte est decoupe en segments : du premier lien d'une annonce jusqu'au premier lien de la suivante
    (avec un court retour en arriere pour un titre place avant l'image). Prix, surface, pieces, ville et DPE
    sont cherches dans le segment de l'annonce uniquement, pour ne pas melanger deux annonces voisines.
    """
    texte = _html_to_blocks(html)
    low = texte.lower()
    occurrences: list[tuple[int, int, str, str, str]] = []  # (debut, fin, id, source, url)
    for motif, source, rx in PORTAILS:
        if source_hint and motif not in source_hint and motif not in low[:20000]:
            continue
        premiers: dict[str, int] = {}
        for m in rx.finditer(texte):
            ident = m.group(1)
            if ident in premiers:
                # meme annonce citee plusieurs fois (image + titre) : on etend la fin au dernier lien
                k = premiers[ident]
                deb, _, i2, s2, u2 = occurrences[k]
                occurrences[k] = (deb, m.end(), i2, s2, u2)
                continue
            premiers[ident] = len(occurrences)
            occurrences.append((m.start(), m.end(), ident, source, m.group(0).rstrip(".,);]")))
    occurrences.sort()
    annonces: list[dict[str, Any]] = []
    for i, (deb, fin, ident, source, url) in enumerate(occurrences):
        prev_end = occurrences[i - 1][1] if i > 0 else 0
        next_start = occurrences[i + 1][0] if i + 1 < len(occurrences) else len(texte)
        seg_start = max(prev_end, deb - 160)
        seg = texte[seg_start:next_start]
        seg_sans_liens = re.sub(r"\[https?://[^\]]*\]", " ", seg)
        prix_m = RE_PRIX.search(seg_sans_liens)
        surf_m = RE_SURFACE.search(seg_sans_liens)
        pieces_m = RE_PIECES.search(seg_sans_liens)
        dpe_m = RE_DPE.search(seg_sans_liens)
        ville, cp = "", ""
        vm = RE_VILLE_CP.search(seg_sans_liens)
        if vm:
            ville, cp = vm.group(1).strip(" -'"), vm.group(2)
        else:
            cpm = RE_CP.search(seg_sans_liens)
            cp = cpm.group(1) if cpm else ""
        lignes = [l.strip() for l in seg_sans_liens.split("\n") if l.strip()]

        def _est_titre(l: str) -> bool:
            return len(l) > 8 and "http" not in l and not RE_PRIX.fullmatch(l) and not re.fullmatch(r"[\w' -]+ ?\d{5}", l) \
                and not l.lower().startswith(("classe", "dpe", "se d", "voir", "nouvelles annonces"))

        titre = next((l for l in lignes if _est_titre(l)), "")
        annonces.append({
            "id": ident,
            "source": source,
            "url": url,
            "titre": titre[:140],
            "prix": float(re.sub(r"[^0-9]", "", prix_m.group(1))) if prix_m else None,
            "surface": float(surf_m.group(1).replace(",", ".")) if surf_m else None,
            "pieces": int(pieces_m.group(1)) if pieces_m else None,
            "ville": ville.title() if ville else "",
            "code_postal": cp,
            "dpe": dpe_m.group(1).upper() if dpe_m else None,
            "contexte": seg_sans_liens.strip()[:400],
        })
    return annonces


def to_listing(a: dict[str, Any], categorie: str = "a_determiner") -> Listing | None:
    if not a.get("prix") or not a.get("surface") or a["surface"] < 9 or a["prix"] < 5000:
        return None
    texte = f"{a.get('titre', '')} {a.get('contexte', '')}"
    return Listing(
        id=f"{a['source']}:{a['id']}",
        source=a["source"],
        url=a["url"],
        titre=a.get("titre") or f"Annonce {a['source']} {a['id']}",
        description=a.get("contexte", ""),
        prix=float(a["prix"]),
        surface=float(a["surface"]),
        pieces=int(a.get("pieces") or max(1, round(a["surface"] / 25))),
        type_bien=_type_bien(texte),
        ville=a.get("ville") or "",
        code_postal=a.get("code_postal") or "",
        categorie_ville=categorie,
        zone_recherche="alerte e-mail",
        dpe=a.get("dpe"),
        date_publication=a.get("date", ""),
        extra={"email_sujet": a.get("sujet", "")},
    )


class Cache:
    def __init__(self, path: str | Path, retention_jours: int = 45):
        self.path = Path(path)
        self.retention = retention_jours * 86400
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def ajouter(self, annonces: Iterable[dict[str, Any]]) -> int:
        n = 0
        now = time.time()
        for a in annonces:
            key = f"{a['source']}:{a['id']}"
            if key not in self.data:
                n += 1
            a = dict(a)
            a["_ts"] = self.data.get(key, {}).get("_ts", now)
            self.data[key] = a
        return n

    def actives(self) -> list[dict[str, Any]]:
        limite = time.time() - self.retention
        self.data = {k: v for k, v in self.data.items() if v.get("_ts", 0) >= limite}
        return list(self.data.values())

    def sauvegarder(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def lire_boite(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Lit les e-mails non lus des expediteurs configures et renvoie les annonces extraites."""
    user, password = os.environ.get("IMAP_USER"), os.environ.get("IMAP_PASSWORD")
    if not user or not password:
        log.info("Alertes e-mail : IMAP_USER / IMAP_PASSWORD absents, etape ignoree")
        return []
    host = os.environ.get("IMAP_HOST") or cfg.get("imap_host", "imap.gmail.com")
    dossier = cfg.get("dossier", "INBOX")
    expediteurs = cfg.get("expediteurs") or ["leboncoin.fr", "seloger.com", "pap.fr", "logic-immo.com", "jinka.fr", "bienici.com"]
    marquer_lu = bool(cfg.get("marquer_lu", True))
    max_mails = int(cfg.get("max_mails_par_run", 200))
    annonces: list[dict[str, Any]] = []
    try:
        box = imaplib.IMAP4_SSL(host)
        box.login(user, password)
        box.select(dossier, readonly=not marquer_lu)
        ids: list[bytes] = []
        for exp in expediteurs:
            status, data = box.search(None, "UNSEEN", "FROM", f'"{exp}"')
            if status == "OK" and data and data[0]:
                ids += data[0].split()
        ids = list(dict.fromkeys(ids))[-max_mails:]
        log.info("Alertes e-mail : %d mails non lus a traiter", len(ids))
        for mid in ids:
            status, data = box.fetch(mid, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                continue
            msg = email.message_from_bytes(data[0][1])
            sujet = _decode(msg.get("Subject"))
            exp = _decode(msg.get("From")).lower()
            date = msg.get("Date", "")
            html_parts, text_parts = [], []
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in {"text/html", "text/plain"}:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    (html_parts if ctype == "text/html" else text_parts).append(payload.decode(charset, errors="ignore"))
            corps = "\n".join(html_parts) if html_parts else "<pre>" + htmlmod.escape("\n".join(text_parts)) + "</pre>"
            trouvees = extraire_annonces(corps, source_hint=exp)
            for a in trouvees:
                a["sujet"] = sujet
                a["date"] = date
            annonces += trouvees
            if marquer_lu:
                box.store(mid, "+FLAGS", "\\Seen")
        box.logout()
    except imaplib.IMAP4.error as exc:
        log.warning("Alertes e-mail : connexion IMAP refusee (%s). Verifier IMAP_USER / mot de passe d'application.", exc)
    except Exception as exc:
        log.warning("Alertes e-mail : %s", exc)
    return annonces


def fetch_all(cfg: dict[str, Any], cache_path: str | Path) -> Iterable[Listing]:
    cache = Cache(cache_path, int(cfg.get("retention_jours", 45)))
    nouvelles = lire_boite(cfg)
    n = cache.ajouter(nouvelles)
    actives = cache.actives()
    cache.sauvegarder()
    sans_surface = sum(1 for a in actives if not a.get("surface"))
    log.info("Alertes e-mail : %d annonces nouvelles, %d actives (%d sans surface, ignorees)", n, len(actives), sans_surface)
    for a in actives:
        lst = to_listing(a)
        if lst:
            yield lst
