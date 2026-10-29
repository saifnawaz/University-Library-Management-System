"""ChatHistory: the last few questions and answers of one chat, for follow-up questions."""

from __future__ import annotations

from typing import Any


class ChatHistory:
    """A short memory of one session's chat: the last MAX_TURNS answered questions.

    It lets the assistant understand follow-ups such as "when is it due?". It is kept
    in the user's session (see app.py), never in the database, so it ends at logout.
    Texts are cut to MAX_CHARS so the session cookie stays small.
    """

    MAX_TURNS: int = 3
    MAX_CHARS: int = 500

    def __init__(self, turns: list[tuple[str, str]] | None = None) -> None:
        """Start empty, or from earlier (question, answer) pairs, oldest first."""
        self._turns: list[tuple[str, str]] = []
        for question, answer in turns or []:
            self.add(question, answer)

    @classmethod
    def from_list(cls, data: Any) -> ChatHistory:
        """Rebuild from to_list() data (e.g. from the session); anything malformed is skipped."""
        turns = []
        if isinstance(data, list):
            for entry in data:
                if (isinstance(entry, dict) and isinstance(entry.get("question"), str)
                        and isinstance(entry.get("answer"), str)):
                    turns.append((entry["question"], entry["answer"]))
        return cls(turns)

    def add(self, question: str, answer: str) -> None:
        """Remember one answered question; the oldest is forgotten after MAX_TURNS."""
        self._turns.append((self._cut(question), self._cut(answer)))
        del self._turns[:-self.MAX_TURNS]

    @property
    def turns(self) -> list[tuple[str, str]]:
        """The remembered (question, answer) pairs, oldest first. Returns a copy."""
        return list(self._turns)

    def questions(self) -> list[str]:
        """The remembered questions, oldest first."""
        return [question for question, _ in self._turns]

    def to_list(self) -> list[dict[str, str]]:
        """Plain data for the session and the web API."""
        return [{"question": q, "answer": a} for q, a in self._turns]

    def __len__(self) -> int:
        return len(self._turns)

    def _cut(self, text: str) -> str:
        text = str(text).strip()
        return text if len(text) <= self.MAX_CHARS else text[:self.MAX_CHARS - 1].rstrip() + "…"
