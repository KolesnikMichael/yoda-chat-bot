import json
from dataclasses import dataclass


@dataclass
class InlineSummaryEnvelope:
    summary_id: str
    added_at: str
    text: str

    def to_message_text(self) -> str:
        return json.dumps({
            "v": 1,
            "summary_id": self.summary_id,
            "added_at": self.added_at,
            "text": self.text,
        })

    @classmethod
    def from_message_text(cls, raw: str) -> "InlineSummaryEnvelope":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid inline summary JSON: {raw!r}") from exc
        if not isinstance(data, dict) or data.get("v") != 1:
            raise ValueError(f"Invalid inline summary envelope version: {raw!r}")
        summary_id = data.get("summary_id")
        added_at = data.get("added_at")
        text = data.get("text")
        if not isinstance(summary_id, str) or not isinstance(added_at, str) or not isinstance(text, str):
            raise ValueError(f"Invalid inline summary envelope fields: {raw!r}")
        return cls(summary_id=summary_id, added_at=added_at, text=text)
