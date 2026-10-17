from dataclasses import dataclass


@dataclass(frozen=True)
class BotEntry:
    id: str
    vendor: str
    ua_pattern: str
    category: str
    verify: dict


def load_registry() -> tuple[str, list[BotEntry]]:
    raise NotImplementedError


def match_user_agent(user_agent: str, entries: list[BotEntry]) -> BotEntry | None:
    raise NotImplementedError
