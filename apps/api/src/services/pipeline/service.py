from src.logger import get_logger
from src.models.domain import Lane
from src.services import classify, importer, pairing, reconstruction, verify

log = get_logger(__name__)

FAST_STEPS = (
    ("import", importer.import_due_files),
    ("pair", pairing.pair_events),
    ("verify", verify.verify_new_clients),
    ("classify", classify.classify_new_verdicts),
    ("views", reconstruction.update_views),
)


async def run_lane(site_id: str, lane: Lane) -> None:
    raise NotImplementedError


async def run_recommendations(site_id: str, window: str) -> None:
    raise NotImplementedError
