import re

from ua_parser import parse

from src.models.domain import UaType

HEADLESS = re.compile(r"headless|phantomjs|puppeteer|playwright|selenium|webdriver", re.I)
LIBRARY = re.compile(
    r"python-requests|python-urllib|\bcurl/|\bwget|go-http-client|axios|node-fetch|okhttp"
    r"|^java/|libwww|httpx|aiohttp|scrapy",
    re.I,
)
BOT = re.compile(r"bot\b|bot/|crawler|spider|crawl|slurp", re.I)
BROWSER_FAMILIES = (
    "chrome",
    "chromium",
    "firefox",
    "safari",
    "edge",
    "opera",
    "samsung internet",
    "ie",
    "internet explorer",
    "brave",
    "vivaldi",
    "duckduckgo",
    "uc browser",
    "yandex browser",
)


def ua_type(user_agent: str | None) -> UaType:
    ua = (user_agent or "").strip()
    if not ua or ua == "-":
        return UaType.OTHER
    if HEADLESS.search(ua):
        return UaType.HEADLESS
    if LIBRARY.search(ua):
        return UaType.LIBRARY
    if BOT.search(ua):
        return UaType.BOT
    family = parse(ua).user_agent
    name = family.family.lower() if family else ""
    if any(
        name == b or name.startswith(b + " ") or name.endswith(" " + b) for b in BROWSER_FAMILIES
    ):
        return UaType.BROWSER
    return UaType.OTHER
