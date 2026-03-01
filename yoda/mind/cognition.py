class CognitionOperation:
  def normalize_user_text(self, text: str) -> str:
    normalized = (text or "").strip()
    return normalized if normalized else "Silence, your message was."
