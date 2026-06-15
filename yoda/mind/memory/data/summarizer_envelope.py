from pydantic import BaseModel


class SummarizerValidationError(ValueError):
    """Malformed summariser JSON envelope after LLM response."""


class LlmSummarizerEnvelope(BaseModel):
    summary: str
    topics: list[str]
    profile_updates: dict[str, dict[str, object]]
