from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonMemoryStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.root / run_id / "memory.json"

    def _load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, run_id: str, payload: dict[str, Any]) -> None:
        path = self._path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def write(self, run_id: str, key: str, value: Any) -> bool:
        payload = self._load(run_id)
        payload[key] = value
        self._write(run_id, payload)
        return True

    def append_event(self, run_id: str, key: str, value: Any) -> list[Any]:
        payload = self._load(run_id)
        payload.setdefault(key, [])
        payload[key].append(value)
        self._write(run_id, payload)
        return payload[key]

    def read(self, run_id: str, key: str, default: Any = None) -> Any:
        return self._load(run_id).get(key, default)

    def snapshot(self, run_id: str) -> dict[str, Any]:
        return self._load(run_id)
