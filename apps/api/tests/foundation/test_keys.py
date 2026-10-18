import pytest

from src.models.keys import client_key, normalize_ip


def test_ipv4_unchanged() -> None:
    assert normalize_ip("20.171.1.5") == "20.171.1.5"


def test_ipv6_becomes_slash_64() -> None:
    assert normalize_ip("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == "2001:db8:1:2::/64"


def test_ipv6_same_64_same_result() -> None:
    assert normalize_ip("2001:db8:1:2::1") == normalize_ip("2001:db8:1:2:ffff::9")


def test_ipv4_mapped_ipv6_is_ipv4() -> None:
    assert normalize_ip("::ffff:20.171.1.5") == "20.171.1.5"


def test_invalid_ip_raises() -> None:
    with pytest.raises(ValueError):
        normalize_ip("not-an-ip")


def test_client_key_is_stable() -> None:
    assert client_key("GPTBot/1.2", "20.171.1.5") == client_key("GPTBot/1.2", "20.171.1.5")


def test_client_key_differs_by_ua_and_ip() -> None:
    base = client_key("GPTBot/1.2", "20.171.1.5")
    assert base != client_key("GPTBot/1.3", "20.171.1.5")
    assert base != client_key("GPTBot/1.2", "20.171.1.6")


def test_client_key_groups_ipv6_by_64() -> None:
    assert client_key("UA", "2001:db8::1") == client_key("UA", "2001:db8::2")


@pytest.mark.parametrize(
    ("ua", "ip"), [(None, "1.2.3.4"), ("", "1.2.3.4"), ("UA", None), ("UA", ""), ("UA", "bad")]
)
def test_client_key_none_when_not_grouped(ua: str | None, ip: str | None) -> None:
    assert client_key(ua, ip) is None
