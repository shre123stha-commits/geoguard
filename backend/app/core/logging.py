"""Structured key=value logging (techspec §9). Never log secrets."""

import logging
import sys


class KeyValueFormatter(logging.Formatter):
    """Formats records as `ts=... level=... logger=... msg="..." key=value ...`.

    Extra context (scan_id, detection_id, user_id) is passed via `logger.info(..., extra={...})`.
    """

    _CONTEXT_KEYS = ("scan_id", "detection_id", "user_id", "step", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            f"ts={self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z')}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f'msg="{record.getMessage()}"',
        ]
        for key in self._CONTEXT_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                parts.append(f"{key}={value}")
        if record.exc_info:
            parts.append(f'exc="{self.formatException(record.exc_info)}"')
        return " ".join(parts)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
