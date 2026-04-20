from __future__ import annotations

import contextlib
import io
import traceback
from dataclasses import dataclass, field
from typing import Any

from src.contracts_runtime import CodeExecutionResult


@dataclass
class CodeExecutionTool:
    allowed_imports: tuple[str, ...] = ("math", "statistics", "json", "numpy", "pandas", "scipy", "numpy_financial")
    base_globals: dict[str, Any] = field(default_factory=dict)

    def __call__(self, code: str) -> CodeExecutionResult:
        stdout = io.StringIO()
        stderr = io.StringIO()
        env: dict[str, Any] = {"__builtins__": __builtins__, **self.base_globals}
        try:
            for name in self.allowed_imports:
                try:
                    env[name] = __import__(name)
                except Exception:
                    continue
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(code, env, env)
            result = env.get("RESULT")
            locals_snapshot = {
                key: _json_safe(value)
                for key, value in env.items()
                if key not in {"__builtins__"} and not callable(value) and not key.startswith("__")
            }
            return CodeExecutionResult(ok=True, stdout=stdout.getvalue(), stderr=stderr.getvalue(), result=result, locals_snapshot=locals_snapshot)
        except Exception:
            stderr.write(traceback.format_exc())
            return CodeExecutionResult(ok=False, stdout=stdout.getvalue(), stderr=stderr.getvalue(), result=None, locals_snapshot={})


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    return repr(value)
