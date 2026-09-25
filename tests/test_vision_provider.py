import pytest

from yoda.mind.perception.vision import VisionProvider


class _RecordingChat:
    def __init__(self) -> None:
        self.messages: list[dict] | None = None
        self.model_name: str | None = None

    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
        self.model_name = model_name
        self.messages = messages
        return "a cat on a table"


def _image(tmp_path) -> str:
    path = tmp_path / "photo.png"
    path.write_bytes(b"\x89PNG\r\n")
    return str(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend", "image_url_type"),
    [("openrouter", dict), ("mistral", str)],
)
async def test_vision_image_shape_follows_backend(tmp_path, backend: str, image_url_type: type) -> None:
    chat = _RecordingChat()
    provider = VisionProvider(
        {"model_name": "vision-model", "provider": "mistral"},
        chat,
        backend,  # type: ignore[arg-type]
    )
    description = await provider.image_to_description(_image(tmp_path))
    assert description == "a cat on a table"
    assert chat.model_name == "vision-model"
    assert chat.messages is not None
    image_part = chat.messages[0]["content"][1]
    assert image_part["type"] == "image_url"
    assert isinstance(image_part["image_url"], image_url_type)
    if backend == "openrouter":
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    else:
        assert image_part["image_url"].startswith("data:image/png;base64,")


def test_vision_provider_requires_backend() -> None:
    with pytest.raises(TypeError):
        VisionProvider({"model_name": "vision-model"}, _RecordingChat())  # type: ignore[call-arg]
