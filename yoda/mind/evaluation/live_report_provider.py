"""Async writer for privacy-safe live routing evaluation reports (TASK-021)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from yoda.mind.evaluation.data import LiveEvalReport


class LiveEvalReportProvider:
    async def write(
        self,
        report: LiveEvalReport,
        directory: Path,
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        short_id = uuid.uuid4().hex[:8]
        path = directory / f"live_routing_eval_{stamp}_{short_id}.json"
        payload = report.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
