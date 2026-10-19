"""Chargement de la configuration YAML et surcharge par variables d'environnement / Google Sheet."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "config.yaml"


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg.setdefault("sorties", {})
    env_sheet = os.environ.get("GSHEET_ID")
    if env_sheet:
        cfg["sorties"]["google_sheet_id"] = env_sheet
    return cfg


def set_dotted(cfg: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Affecte cfg["a"]["b"]["c"] = value pour la cle "a.b.c"."""
    parts = dotted_key.split(".")
    node = cfg
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def get_dotted(cfg: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def coerce(value: str) -> Any:
    """Convertit une chaine saisie dans le Sheet en bool / int / float / str."""
    if value is None:
        return None
    text = str(value).strip()
    low = text.lower()
    if low in {"true", "vrai", "oui", "yes"}:
        return True
    if low in {"false", "faux", "non", "no"}:
        return False
    text_num = text.replace("%", "").replace(",", ".").replace(" ", "")
    try:
        if "." in text_num:
            val = float(text_num)
        else:
            val = int(text_num)
        if text.strip().endswith("%"):
            return val / 100.0
        return val
    except ValueError:
        return text


def apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Retourne une copie de cfg avec les surcharges (cle pointee -> valeur)."""
    out = copy.deepcopy(cfg)
    for key, value in overrides.items():
        if not key:
            continue
        set_dotted(out, key.strip(), coerce(value) if isinstance(value, str) else value)
    return out
