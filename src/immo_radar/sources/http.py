"""Session HTTP partagee avec en-tetes navigateur, retries et temporisation."""
from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    })
    return s


def get_json(s: requests.Session, url: str, params: dict[str, Any] | None = None, retries: int = 3, timeout: int = 30) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = s.get(url, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:  # ValueError = JSON invalide
            last = exc
            pause = (2 ** attempt) + random.uniform(0.2, 1.0)
            log.warning("GET %s echoue (%s), nouvelle tentative dans %.1fs", url, exc, pause)
            time.sleep(pause)
    raise RuntimeError(f"Echec definitif GET {url}: {last}")


def polite_pause(min_s: float = 0.8, max_s: float = 2.0) -> None:
    time.sleep(random.uniform(min_s, max_s))
