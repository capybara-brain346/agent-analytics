async def download_snapshots() -> None:
    raise NotImplementedError


def ip_in_snapshot(ip: str, source: str) -> tuple[bool, str]:
    raise NotImplementedError
