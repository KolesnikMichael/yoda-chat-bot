"""Async façade for Pixazo text-to-image (Flux) gateway."""

from typing import Any

import httpx


class PixazoApi:
    def __init__(self, gateway_url: str, api_key: str) -> None:
        self._gateway_url = gateway_url
        self._api_key = api_key

    async def generate_image_bytes(
        self,
        prompt: str,
        *,
        num_steps: int = 4,
        seed: int = 42,
        width: int = 512,
        height: int = 512,
    ) -> bytes:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Ocp-Apim-Subscription-Key": self._api_key,
        }
        payload: dict[str, Any] = {
            "prompt": prompt,
            "num_steps": num_steps,
            "seed": seed,
            "height": height,
            "width": width,
        }
        timeout = httpx.Timeout(120.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._gateway_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
            output_url = body.get("output")
            if not output_url or not isinstance(output_url, str):
                raise ValueError(f"Unexpected Pixazo response: {body!r}")

            image_response = await client.get(output_url)
            image_response.raise_for_status()
            return image_response.content
