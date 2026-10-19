"""Contraintes reglementaires par commune (config/reglementation.yaml)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from ..config import ROOT

DEFAULT_PATH = ROOT / "config" / "reglementation.yaml"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\s+\d+(er|e|eme)\b.*$", "", text)  # "Lyon 3e" -> "lyon"
    return re.sub(r"[^a-z]+", "", text)


class Reglementation:
    def __init__(self, path: str | Path | None = None):
        with open(path or DEFAULT_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        self.defaut: dict[str, Any] = data.get("defaut", {})
        self.communes = {_norm(k): v for k, v in (data.get("communes") or {}).items()}

    def pour(self, ville: str) -> dict[str, Any]:
        rules = dict(self.defaut)
        rules.update(self.communes.get(_norm(ville), {}))
        return rules

    @staticmethod
    def courte_duree(rules: dict[str, Any], dpe: str | None = None) -> tuple[bool, int, str]:
        """(faisable, niveau de risque 0-3, note) pour une residence secondaire louee en meuble de tourisme."""
        dpe = (dpe or "").upper()
        if rules.get("compensation"):
            return False, 3, "Changement d'usage avec compensation : courte duree reservee a la residence principale (90 nuits) ou au bail mobilite"
        if rules.get("changement_usage") and dpe in {"F", "G"}:
            return False, 3, "DPE F/G : l'autorisation de changement d'usage est refusee (DPE E minimum, D en 2034)"
        if rules.get("quota"):
            return True, 2, "Quotas / autorisations temporaires de meubles de tourisme (loi Le Meur) : offre a conditionner a l'autorisation"
        if rules.get("changement_usage"):
            return True, 2, "Autorisation de changement d'usage a demander en mairie (souvent temporaire, 3 a 9 ans)"
        if rules.get("zone_tendue"):
            return True, 1, "Declaration en mairie et numero d'enregistrement national ; quotas possibles a tout moment en zone tendue"
        return True, 0, "Declaration en mairie et numero d'enregistrement national suffisent"
