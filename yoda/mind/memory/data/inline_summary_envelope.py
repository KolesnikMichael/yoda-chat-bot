import datetime as dtm
import json
from dataclasses import dataclass, field

from .summary_outbox_entry import SummaryOutboxEntry

INLINE_SUMMARY_ENVELOPE_VERSION = 1


def _format_date_label(iso_ts: str) -> str:
    if not iso_ts:
        return "?"
    normalized = iso_ts.replace("Z", "+00:00")
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)
    try:
        return dtm.datetime.fromisoformat(normalized).strftime("%Y-%m-%d")
    except ValueError:
        return iso_ts[:10] if len(iso_ts) >= 10 else iso_ts


@dataclass
class InlineSummaryEnvelope:
    summary_id: str
    added_at: str
    text: str
    content_from_ts: str = ""
    content_to_ts: str = ""
    skills: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    def to_message_text(self) -> str:
        return json.dumps({
            "v": INLINE_SUMMARY_ENVELOPE_VERSION,
            "summary_id": self.summary_id,
            "added_at": self.added_at,
            "content_from_ts": self.content_from_ts,
            "content_to_ts": self.content_to_ts,
            "skills": self.skills,
            "topics": self.topics,
            "text": self.text,
        })

    def format_presentation_header(self) -> str:
        from_label = _format_date_label(self.content_from_ts)
        to_label = _format_date_label(self.content_to_ts)
        return f"[Summary · {from_label} — {to_label}]"

    def to_llm_content(self) -> str:
        return f"{self.format_presentation_header()}\n{self.text}"

    def to_outbox_entry(self, compressed_at: float) -> SummaryOutboxEntry:
        return SummaryOutboxEntry(
            summary_id=self.summary_id,
            document=self.text,
            compressed_at=compressed_at,
            content_from_ts=self.content_from_ts,
            content_to_ts=self.content_to_ts,
            skills=list(self.skills),
            topics=list(self.topics),
            added_at=self.added_at,
        )

    @classmethod
    def from_message_text(cls, raw: str) -> "InlineSummaryEnvelope":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid inline summary JSON: {raw!r}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Invalid inline summary envelope: {raw!r}")
        version = data.get("v")
        if version != INLINE_SUMMARY_ENVELOPE_VERSION:
            raise ValueError(f"Invalid inline summary envelope version: {raw!r}")
        summary_id = data.get("summary_id")
        added_at = data.get("added_at")
        text = data.get("text")
        content_from_ts = data.get("content_from_ts", "")
        content_to_ts = data.get("content_to_ts", "")
        skills_raw = data.get("skills", [])
        topics_raw = data.get("topics", [])
        if not isinstance(summary_id, str) or not isinstance(added_at, str) or not isinstance(text, str):
            raise ValueError(f"Invalid inline summary envelope fields: {raw!r}")
        if not isinstance(content_from_ts, str) or not isinstance(content_to_ts, str):
            raise ValueError(f"Invalid inline summary envelope timestamps: {raw!r}")
        if not isinstance(skills_raw, list) or not all(isinstance(s, str) for s in skills_raw):
            raise ValueError(f"Invalid inline summary envelope skills: {raw!r}")
        if not isinstance(topics_raw, list) or not all(isinstance(t, str) for t in topics_raw):
            raise ValueError(f"Invalid inline summary envelope topics: {raw!r}")
        return cls(
            summary_id=summary_id,
            added_at=added_at,
            text=text,
            content_from_ts=content_from_ts,
            content_to_ts=content_to_ts,
            skills=skills_raw,
            topics=topics_raw,
        )
