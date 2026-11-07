"""Shared contracts. FROZEN after kickoff: changes need a PR approved by all 5.

Every module imports its types from here. Fixtures in contracts/fixtures/*.json
must validate against these models (tests/test_contracts.py enforces it).
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

Kind = Literal["need", "want", "income"]
Tone = Literal["friendly", "direct", "simple"]
Severity = Literal["low", "medium", "high"]


class User(BaseModel):
    id: str
    name: str
    persona: str  # e.g. "student, irregular income"
    region: str  # e.g. "Manchester"
    household_id: Optional[str] = None  # extension: family view
    tone: Tone = "friendly"


class Transaction(BaseModel):
    id: str
    user_id: str
    date: dt.date
    merchant: str
    amount: float  # negative = spend, positive = income (GBP)
    category: str  # e.g. "groceries"
    kind: Kind  # need / want / income


class Pot(BaseModel):
    id: str
    user_id: str
    name: str
    amount: float
    due_date: Optional[dt.date] = None  # None = open-ended (e.g. emergency fund)


class ForecastPoint(BaseModel):
    date: dt.date
    low: float
    expected: float
    high: float


class RiskEvent(BaseModel):
    date: dt.date
    reason: str
    severity: Severity


class Forecast(BaseModel):
    user_id: str
    horizon_days: int
    points: list[ForecastPoint]
    risk_events: list[RiskEvent]
    assumptions: list[str] = Field(default_factory=list)  # shown to the user (transparency)


class BreakdownItem(BaseModel):
    label: str
    amount: float


class SafeToSpend(BaseModel):
    balance: float
    pots_total: float
    upcoming_bills: float
    safe_amount: float  # balance - pots_total - upcoming_bills
    breakdown: list[BreakdownItem]


class PurchaseVerdict(BaseModel):
    affordable: bool
    safe_after: float
    better_date: Optional[dt.date] = None  # e.g. next big sale
    reason: str
    numbers_used: dict[str, float]


class Alert(BaseModel):
    id: str
    type: Literal["overspend", "sudden_change", "risk"]
    category: Optional[str] = None
    message: str
    suggested_action: str
    severity: Severity


class Tip(BaseModel):  # extension: savings / tax tips (information, not advice)
    id: str
    title: str
    body: str
    est_saving: Optional[float] = None
    disclaimer: str = "General information, not financial or tax advice."


class SimulateRequest(BaseModel):
    amount: float
    date: Optional[dt.date] = None  # default: today


class ChatRequest(BaseModel):
    message: str
    tone: Optional[Tone] = None


class ChatReply(BaseModel):
    text: str
    numbers_used: dict[str, float] = Field(default_factory=dict)  # transparency
    audio_url: Optional[str] = None
