"""Vendor IP lists: daily download as a new snapshot (2.8b). Offline mode = bundled lists."""


async def download_snapshots() -> None:
    raise NotImplementedError


def ip_in_snapshot(ip: str, source: str) -> tuple[bool, str]:
    """Return (match, snapshot_version)."""
    raise NotImplementedError
