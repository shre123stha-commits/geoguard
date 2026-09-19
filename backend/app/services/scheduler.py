"""Recurring scans (techspec §7 Scheduler, task 4.6).

Design: instead of registering one APScheduler job per schedule (state would live in memory
and drift from the DB), a single tick runs every minute, reads `scan_schedules` with
`next_run_at <= now`, creates a normal `queued` scan for each (same worker path), and stores
the next due time. APScheduler's `CronTrigger` is used only to parse cron strings and compute
next fire times. Missed runs while the app was off are not replayed: on startup,
`next_run_at` in the past is simply recomputed from now.
"""

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, sessionmaker

from app.db.enums import ScanStatus
from app.db.models import ScanSchedule
from app.pipeline.fusion import ALGORITHM_VERSION
from app.repositories import ScanRepository, ScheduleRepository

logger = logging.getLogger(__name__)

PRESETS = {
    "weekly": "0 2 * * 1",  # Monday 02:00
    "monthly": "0 2 1 * *",  # 1st of the month 02:00
}


class CronError(ValueError):
    pass


_CRON_DOW = {
    "0": "sun",
    "1": "mon",
    "2": "tue",
    "3": "wed",
    "4": "thu",
    "5": "fri",
    "6": "sat",
    "7": "sun",
}
_DOW_NAMES = {"sun", "mon", "tue", "wed", "thu", "fri", "sat"}


def _dow_field(field: str) -> str:
    """Standard cron weekdays (0/7 = Sunday, 1 = Monday) -> APScheduler names.

    APScheduler's `from_crontab` would read `1` as Tuesday (its numbering starts at Monday).
    """
    out = []
    for part in field.split(","):
        rng, _, step = part.partition("/")
        if rng == "*":
            out.append(part)
            continue
        names = []
        for tok in rng.split("-"):
            t = tok.lower()
            if t in _DOW_NAMES:
                names.append(t)
            elif t in _CRON_DOW:
                names.append(_CRON_DOW[t])
            else:
                raise CronError(f"invalid weekday '{tok}'")
        out.append("-".join(names) + (f"/{step}" if step else ""))
    return ",".join(out)


def parse_cron(expr: str) -> CronTrigger:
    """Accept a preset name or a 5-field crontab string (UTC, standard weekday numbering)."""
    expr = PRESETS.get(expr.strip().lower(), expr.strip())
    fields = expr.split()
    if len(fields) != 5:
        raise CronError("cron must have 5 fields: minute hour day month weekday")
    minute, hour, day, month, dow = fields
    try:
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=_dow_field(dow),
            timezone=UTC,
        )
    except ValueError as exc:
        raise CronError(f"invalid cron expression: {exc}") from exc


def next_run(cron: str, after: datetime | None = None) -> datetime:
    after = after or datetime.now(UTC)
    trig = parse_cron(cron)
    # APScheduler treats `after` as inclusive; we need strictly later (avoid double firing).
    nxt = trig.get_next_fire_time(None, after + timedelta(seconds=1))
    if nxt is None:
        raise CronError("cron expression never fires")
    out: datetime = nxt.astimezone(UTC)
    return out


@dataclass(frozen=True)
class Windows:
    baseline: tuple[date, date]
    current: tuple[date, date]


def compute_windows(
    rule: dict[str, Any], current_window_days: int, today: date | None = None
) -> Windows:
    """Current window ends today; baseline per rule (techspec §7).

    Rules:
      same_season_previous_year (default) — same dates, one year earlier (window_days optional)
      fixed — explicit baseline_start / baseline_end (ISO dates)
      years_back — like the default but N years back (`years`)
    """
    today = today or datetime.now(UTC).date()
    cur_end = today
    cur_start = today - timedelta(days=current_window_days - 1)
    mode = rule.get("mode", "same_season_previous_year")
    if mode == "fixed":
        b0, b1 = (
            date.fromisoformat(rule["baseline_start"]),
            date.fromisoformat(rule["baseline_end"]),
        )
    else:
        years = int(rule.get("years", 1)) if mode == "years_back" else 1
        window = int(rule.get("window_days", current_window_days))
        b1 = _years_back(cur_end, years)
        b0 = b1 - timedelta(days=window - 1)
    if b1 >= cur_start:
        raise ValueError("baseline window must end before the current window starts")
    return Windows((b0, b1), (cur_start, cur_end))


def _years_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year - years, day=28)


class ScanScheduler:
    def __init__(self, session_factory: sessionmaker[Session], tick_seconds: float = 60.0) -> None:
        self.session_factory = session_factory
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.recompute_all()
        self._thread = threading.Thread(target=self._loop, name="scan-scheduler", daemon=True)
        self._thread.start()
        logger.info("scheduler started", extra={"tick_s": self.tick_seconds})

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def recompute_all(self) -> int:
        """Startup: never replay missed runs; move past-due schedules to their next slot."""
        now = datetime.now(UTC)
        n = 0
        with self.session_factory() as db:
            for s in ScheduleRepository(db).list_all(active_only=True):
                if s.next_run_at is None or s.next_run_at <= now:
                    s.next_run_at = next_run(s.cron, now)
                    n += 1
            db.commit()
        return n

    def tick(self, now: datetime | None = None) -> list[uuid.UUID]:
        """Create scans for every due schedule; returns the new scan ids."""
        now = now or datetime.now(UTC)
        created: list[uuid.UUID] = []
        with self.session_factory() as db:
            repo = ScheduleRepository(db)
            for s in repo.list_all(active_only=True):
                if s.next_run_at is None or s.next_run_at > now:
                    continue
                scan_id = self.fire(db, s, now)
                if scan_id is not None:
                    created.append(scan_id)
            db.commit()
        return created

    def fire(self, db: Session, s: ScanSchedule, now: datetime) -> uuid.UUID | None:
        return fire_schedule(db, s, now)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - keep ticking
                logger.exception("scheduler tick failed")
            self._stop.wait(self.tick_seconds)


def fire_schedule(db: Session, s: ScanSchedule, now: datetime) -> uuid.UUID | None:
    """Queue one scan for `s` (duplicate-queue guard) and advance next_run_at."""
    s.next_run_at = next_run(s.cron, now)
    s.last_run_at = now
    scans = ScanRepository(db)
    if _has_open_scan(scans, s.id):
        logger.info("schedule skipped: previous scan still open", extra={"schedule": str(s.id)})
        return None
    parcels = list(s.parcels)
    if not parcels:
        logger.warning("schedule has no parcels", extra={"schedule": str(s.id)})
        return None
    try:
        w = compute_windows(s.baseline_rule, s.current_window_days, now.date())
    except ValueError as exc:
        logger.warning("schedule windows invalid: %s", exc, extra={"schedule": str(s.id)})
        return None
    scan = scans.create(
        parcels,
        w.baseline,
        w.current,
        dict(s.params),
        ALGORITHM_VERSION,
        created_by=s.created_by,
        schedule_id=s.id,
    )
    db.flush()
    logger.info("schedule fired", extra={"schedule": str(s.id), "scan_id": str(scan.id)})
    return scan.id


def _has_open_scan(scans: ScanRepository, schedule_id: uuid.UUID) -> bool:
    from sqlalchemy import select

    from app.db.models import Scan

    return (
        scans.db.scalar(
            select(Scan.id)
            .where(Scan.schedule_id == schedule_id)
            .where(Scan.status.in_([ScanStatus.queued, ScanStatus.running]))
            .limit(1)
        )
        is not None
    )
