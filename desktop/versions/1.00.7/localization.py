"""Small, dependency-free catalog for ClipNest interface text."""

import json
from pathlib import Path

from PySide6.QtCore import QLocale


_language = "zh_CN"
_catalog = json.loads(Path(__file__).with_name("locales.json").read_text(encoding="utf-8"))


def effective_language(choice: str) -> str:
    if choice in {"zh_CN", "zh_TW", "en"}:
        return choice
    system = QLocale.system().name().lower()
    if system.startswith(("zh_tw", "zh_hk", "zh_mo")):
        return "zh_TW"
    if system.startswith("zh"):
        return "zh_CN"
    return "en"


def set_language(choice: str) -> str:
    global _language
    _language = effective_language(choice)
    return _language


def language() -> str:
    return _language


def tr(source: str) -> str:
    if _language == "zh_CN":
        return source
    return _catalog.get(_language, {}).get(source, source)
