import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Sample log files: <site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz] (samples/logs/README.md).
# The dashboard reads the same rule (apps/dashboard/src/lib/log-name.ts).
LOG_NAME = re.compile(
    r"^(?P<site>[A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*)__(?P<source>[a-z]+)__"
    r"(?P<start>\d{8}T\d{4}Z)(?:__(?P<label>[A-Za-z0-9._-]+?))?\.log(?:\.gz)?$"
)
LOG_SUFFIXES = (".log", ".log.gz", ".gz")


@dataclass(frozen=True)
class LogName:
    site: str
    source: str
    start: datetime
    label: str | None


def parse_log_name(name: str) -> LogName | None:
    # None = the name does not follow the rule; the caller then needs an explicit site and source.
    match = LOG_NAME.match(name)
    if match is None:
        return None
    start = datetime.strptime(match["start"], "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
    return LogName(match["site"], match["source"], start, match["label"])


def is_log_file(path: Path) -> bool:
    return path.is_file() and path.name.endswith(LOG_SUFFIXES)
