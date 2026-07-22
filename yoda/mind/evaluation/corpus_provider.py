"""Async routing corpus loading (TASK-020)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from yoda.mind.evaluation.data import RoutingCorpus


class CorpusLoadError(Exception):
    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


class RoutingCorpusProvider:
    async def load(self, path: Path) -> RoutingCorpus:
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CorpusLoadError(path, f"cannot read corpus: {exc}") from exc

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise CorpusLoadError(path, f"invalid JSON at line {exc.lineno}") from exc

        try:
            return RoutingCorpus.model_validate(payload)
        except ValidationError as exc:
            case_id = None
            field_path = ""
            for error in exc.errors():
                loc = error.get("loc", ())
                if loc and loc[0] == "cases" and len(loc) > 1:
                    index = loc[1]
                    if isinstance(index, int) and index < len(payload.get("cases", [])):
                        case_id = payload["cases"][index].get("id")
                field_path = ".".join(str(part) for part in loc)
                break
            detail = f"case={case_id} field={field_path} error={exc.errors()[0]['msg']}"
            raise CorpusLoadError(path, detail) from exc
