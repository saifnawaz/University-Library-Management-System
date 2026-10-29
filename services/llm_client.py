"""LLM clients: one abstract interface, a real Google Gemini client and a fake one for tests."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable

from exceptions import LLMError

log = logging.getLogger(__name__)


class LLMClient(ABC):
    """Anything that can turn a system prompt and a message into a text reply.

    ChatAssistant and LLMTopicGuard only know this interface, so the real
    Gemini client and the test fake can be swapped freely.
    """

    @abstractmethod
    def generate(self, system_prompt: str, message: str) -> str:
        """Return the model's reply as plain text. Raises LLMError if there is none."""


class GeminiClient(LLMClient):
    """Calls Google Gemini through Google's official SDK (the google-genai package)."""

    DEFAULT_MODEL: str = "gemini-3.8-flash"
    TIMEOUT_SECONDS: int = 20
    TEMPERATURE: float = 0.2      # low: stick to the facts we pass in
    MAX_OUTPUT_TOKENS: int = 2048

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        """Set up the SDK client. Nothing is sent until generate() is called."""
        if not api_key:
            raise ValueError("A Gemini API key is required.")
        from google import genai           # imported here so tests never need it loaded
        from google.genai import types
        self._types = types
        self._model: str = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=self.TIMEOUT_SECONDS * 1000),  # milliseconds
        )

    @classmethod
    def from_env(cls) -> GeminiClient | None:
        """A client using GEMINI_API_KEY and GEMINI_MODEL from .env, or None if there is no key."""
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            return None
        return cls(key, os.getenv("GEMINI_MODEL", "").strip() or cls.DEFAULT_MODEL)

    @property
    def model(self) -> str:
        """The Gemini model name, e.g. 'gemini-3.8-flash'."""
        return self._model

    def generate(self, system_prompt: str, message: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=message,
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.TEMPERATURE,
                    max_output_tokens=self.MAX_OUTPUT_TOKENS,
                ),
            )
            text = (response.text or "").strip()
        except Exception as e:  # network, quota, bad key, blocked reply: all mean "no answer"
            log.warning("Gemini request failed: %s", type(e).__name__)
            raise LLMError("The language model did not answer.") from e
        if not text:
            raise LLMError("The language model gave an empty answer.")
        return text


class FakeLLMClient(LLMClient):
    """A stand-in for tests: no internet, a canned reply, and a record of every call."""

    def __init__(self, reply: str | Callable[[str, str], str] = "Fake answer.",
                 fail: bool = False) -> None:
        """reply: fixed text, or a function (system_prompt, message) -> text.
        fail: if True, every call raises LLMError, like an API outage."""
        self._reply = reply
        self._fail: bool = fail
        self._calls: list[tuple[str, str]] = []

    @property
    def calls(self) -> list[tuple[str, str]]:
        """Every (system_prompt, message) sent so far (a copy)."""
        return list(self._calls)

    def generate(self, system_prompt: str, message: str) -> str:
        self._calls.append((system_prompt, message))
        if self._fail:
            raise LLMError("Fake outage.")
        return self._reply(system_prompt, message) if callable(self._reply) else self._reply
