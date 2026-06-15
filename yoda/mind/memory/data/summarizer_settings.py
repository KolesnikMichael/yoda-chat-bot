from dataclasses import dataclass


@dataclass(frozen=True)
class SummarizerSettings:
    model_name: str

    @classmethod
    def from_settings(cls, settings: dict) -> "SummarizerSettings":
        mind = settings.get("mind", {})
        chat_compression = mind.get("memory", {}).get("chat_compression", {})
        summarizer_block = chat_compression.get("summarizer", {})
        model_name = summarizer_block.get("model_name")
        if not model_name:
            model_name = mind.get("perception", {}).get("language", {}).get("model_name")
        if not model_name:
            raise ValueError("Summariser model name is not configured")
        return cls(model_name=str(model_name))
