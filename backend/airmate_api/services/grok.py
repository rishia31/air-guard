"""Small async client for the xAI APIs Airmate uses: Responses (chat with tools) and text to speech."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from ..config import Settings

log = logging.getLogger(__name__)

ToolRunner = Callable[[str, dict], Awaitable[dict]]


class GrokError(RuntimeError):
    pass


class GrokClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._http: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.grok_enabled

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.settings.xai_base_url,
                headers={"Authorization": f"Bearer {self.settings.xai_api_key}"},
                timeout=httpx.Timeout(45.0, connect=10.0),
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def respond(
        self,
        input: str | list[dict],
        *,
        instructions: str | None = None,
        tools: list[dict] | None = None,
        previous_response_id: str | None = None,
        model: str | None = None,
        reasoning: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        if not self.enabled:
            raise GrokError("XAI_API_KEY is not set")
        body: dict[str, Any] = {"model": model or self.settings.grok_chat_model, "input": input, "store": True}
        if previous_response_id:
            body["previous_response_id"] = previous_response_id  # the first turn's system prompt carries over
        elif instructions:
            body["instructions"] = instructions
        if tools:
            body["tools"] = tools
        effort = self.settings.grok_chat_reasoning if reasoning is None else reasoning
        if effort:
            body["reasoning"] = {"effort": effort}
        if max_output_tokens:
            body["max_output_tokens"] = max_output_tokens
        if temperature is not None:
            body["temperature"] = temperature
        response = await self._client().post("/responses", json=body)
        if response.status_code == 400 and "reasoning" in body and "reason" in response.text.lower():
            log.info("Model %s rejected the reasoning setting; retrying without it", body["model"])
            body.pop("reasoning")
            response = await self._client().post("/responses", json=body)
        if response.status_code >= 400:
            raise GrokError(f"xAI {response.status_code}: {response.text[:400]}")
        return response.json()

    async def run_tools(
        self,
        input: str | list[dict],
        *,
        instructions: str,
        tools: list[dict],
        runner: ToolRunner,
        previous_response_id: str | None = None,
        max_rounds: int = 5,
        **kwargs,
    ) -> tuple[str, str, list[dict]]:
        """Run a Responses conversation turn, executing function calls until the model answers.

        Returns (reply text, last response id, tool calls made).
        """
        response = await self.respond(
            input, instructions=instructions, tools=tools, previous_response_id=previous_response_id, **kwargs
        )
        calls_made: list[dict] = []
        for _ in range(max_rounds):
            calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if not calls:
                break
            outputs = []
            for call in calls:
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await runner(call["name"], args)
                calls_made.append({"name": call["name"], "arguments": args, "result": result})
                outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)})
            response = await self.respond(outputs, tools=tools, previous_response_id=response["id"], **kwargs)
        return output_text(response), response["id"], calls_made

    async def text(self, prompt: str, *, instructions: str, model: str | None = None, reasoning: str | None = None,
                   max_output_tokens: int = 600, temperature: float | None = 0.4) -> str:
        response = await self.respond(
            prompt, instructions=instructions, model=model, reasoning=reasoning, max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        return output_text(response)

    async def tts(self, text: str, voice: str | None = None, codec: str = "mp3") -> tuple[bytes, str]:
        if not self.enabled:
            raise GrokError("XAI_API_KEY is not set")
        response = await self._client().post(
            "/tts",
            json={"text": text, "voice_id": voice or self.settings.grok_voice, "language": "en",
                  "output_format": {"codec": codec}},
        )
        if response.status_code >= 400:
            raise GrokError(f"xAI TTS {response.status_code}: {response.text[:300]}")
        return response.content, response.headers.get("content-type", "audio/mpeg")


def output_text(response: dict) -> str:
    parts = []
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text") and content.get("text"):
                    parts.append(content["text"])
    return "\n".join(parts).strip()
