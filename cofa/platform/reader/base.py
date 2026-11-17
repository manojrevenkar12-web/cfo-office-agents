"""What a reader returns. Readers only read: they turn customer text into fields. Code decides what to do."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

INTENTS = ("promise_to_pay", "dispute", "invoice_copy", "says_paid", "other")
REASONS = ("price", "damage", "quantity", "other")


@dataclass
class AdviceLine:
    doc: str
    gross_cents: int | None
    less_cents: int
    paid_cents: int | None
    note: str = ""


@dataclass
class Advice:
    lines: list[AdviceLine]
    total_cents: int | None
    instructions: list[str] = field(default_factory=list)
    tokens: int = 0


@dataclass
class ReplyRead:
    intent: str
    docs: list[str]
    date: str | None = None
    reason_class: str | None = None
    instructions: list[str] = field(default_factory=list)
    tokens: int = 0


class Reader(Protocol):
    name: str

    def read_advice(self, text: str) -> Advice: ...

    def read_reply(self, text: str) -> ReplyRead: ...
