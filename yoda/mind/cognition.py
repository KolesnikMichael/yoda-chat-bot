class CognitionOperation:
    @staticmethod
    def normalize_user_text(text: str) -> str:
        normalized = (text or "").strip()
        return normalized if normalized else "<got empty message from user>"

    @staticmethod
    def determine_chat_type(user_id: int, chat_id: int) -> str:
        return "private" if user_id == chat_id else "group"

    @staticmethod
    def should_reply(chat_type: str) -> bool:
        return True
