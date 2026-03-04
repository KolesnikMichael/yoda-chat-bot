class CognitionOperation:
  @staticmethod
  def normalize_user_text(text: str) -> str:
    normalized = (text or "").strip()
    return normalized if normalized else "<got empty message from user>"
