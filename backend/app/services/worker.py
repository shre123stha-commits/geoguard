"""Background scan worker (techspec §7, task 4.2).

Runs inside the API process as a daemon thread (v1: one machine, one process). Polls for
`queued` scans, claims one with `FOR UPDATE SKIP LOCKED`, runs it with `ScanRunner`, repeats.
On startup, `running` scans older than `stale_after` are marked failed (`worker_restart`).
"""

import logging
import threading
import time
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.repositories import ScanRepository
from app.services.scan_runner import (
    ScanFailedError,
    ScanRunner,
    SourceFactory,
    default_source_factory,
)

logger = logging.getLogger(__name__)


class ScanWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        poll_seconds: float = 3.0,
        stale_after: timedelta = timedelta(hours=2),
        source_factory: SourceFactory = default_source_factory,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.poll_seconds = poll_seconds
        self.stale_after = stale_after
        self._source_factory = source_factory
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.busy = False

    # ---- lifecycle ------------------------------------------------------------------------
    def start(self) -> None:
        self.recover()
        self._thread = threading.Thread(target=self._loop, name="scan-worker", daemon=True)
        self._thread.start()
        logger.info("scan worker started", extra={"poll_s": self.poll_seconds})

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        logger.info("scan worker stopped")

    def recover(self) -> int:
        with self.session_factory() as db:
            n = ScanRepository(db).recover_stale(self.stale_after)
        if n:
            logger.warning("marked %d stale running scan(s) as failed (worker_restart)", n)
        return n

    # ---- work -----------------------------------------------------------------------------
    def run_once(self) -> bool:
        """Claim and run one queued scan. Returns True if a scan was processed."""
        with self.session_factory() as db:
            scan = ScanRepository(db).claim_next()
            if scan is None:
                return False
            self.busy = True
            try:
                ScanRunner(db, self.settings, self._source_factory).run(scan)
            except ScanFailedError as exc:
                logger.warning("scan failed", extra={"scan_id": str(scan.id), "code": exc.code})
            finally:
                self.busy = False
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self.run_once()
            except Exception:  # noqa: BLE001 - keep the loop alive (DB hiccups etc.)
                logger.exception("worker iteration failed")
                processed = False
            if not processed:
                self._stop.wait(self.poll_seconds)
            else:
                time.sleep(0)  # yield; immediately look for the next queued scan
