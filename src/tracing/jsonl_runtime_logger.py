from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonlTraceLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "event_type": event_type,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
