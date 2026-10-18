# ruff: noqa: E501
import pytest

from src.models.domain import UaType
from src.services.classify.ua import ua_type

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
EDGE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"

CASES = [
    (CHROME, UaType.BROWSER),
    (FIREFOX, UaType.BROWSER),
    (SAFARI, UaType.BROWSER),
    (EDGE, UaType.BROWSER),
    (CHROME.replace("Chrome/", "HeadlessChrome/"), UaType.HEADLESS),
    (
        "Mozilla/5.0 (Unknown; Linux x86_64) AppleWebKit/538.1 (KHTML, like Gecko) PhantomJS/2.1.1 Safari/538.1",
        UaType.HEADLESS,
    ),
    (CHROME + " Puppeteer", UaType.HEADLESS),
    (CHROME + " Playwright/1.40", UaType.HEADLESS),
    ("python-requests/2.31.0", UaType.LIBRARY),
    ("curl/8.4.0", UaType.LIBRARY),
    ("Wget/1.21.4", UaType.LIBRARY),
    ("Go-http-client/2.0", UaType.LIBRARY),
    ("axios/1.6.2", UaType.LIBRARY),
    ("node-fetch/1.0 (+https://github.com/bitinn/node-fetch)", UaType.LIBRARY),
    ("okhttp/4.12.0", UaType.LIBRARY),
    ("Java/17.0.2", UaType.LIBRARY),
    ("libwww-perl/6.67", UaType.LIBRARY),
    ("python-httpx/0.25.2", UaType.LIBRARY),
    ("Python/3.12 aiohttp/3.9.1", UaType.LIBRARY),
    ("Scrapy/2.11.0 (+https://scrapy.org)", UaType.LIBRARY),
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", UaType.BOT),
    (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.1; +https://openai.com/gptbot)",
        UaType.BOT,
    ),
    ("Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", UaType.BOT),
    ("SomeSpider/1.0", UaType.BOT),
    ("MyCrawler/2", UaType.BOT),
    ("", UaType.OTHER),
    (None, UaType.OTHER),
    ("-", UaType.OTHER),
    ("zzz-unknown-thing", UaType.OTHER),
]


@pytest.mark.parametrize(("ua", "expected"), CASES)
def test_ua_type(ua, expected):
    assert ua_type(ua) == expected
