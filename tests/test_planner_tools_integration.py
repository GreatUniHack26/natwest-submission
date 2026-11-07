"""Planner tools end to end: chat loop with a scripted LLM, and real seeded data in real mode."""
import datetime as dt
import json
import re

import pytest

from backend import config
from backend import forecast as fc
from backend.agent import orchestrator, tools
from backend.data import categoriser, repository
from backend.data.seed import seed

CURRENCY_RE = re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)")
TWO = [
    {"name": "Card A", "balance": 200, "apr": 24, "minimum": 20},
    {"name": "Loan B", "balance": 100, "apr": 12, "minimum": 10},
]


def _tool_use(call_id, name, args):
    return {"id": "m", "role": "assistant", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}]}


def _text(text):
    return {"id": "m2", "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def _script(monkeypatch, responses):
    it = iter(responses)
    sent = []

    def fake(**kwargs):
        sent.append(kwargs)
        return next(it)

    monkeypatch.setattr(orchestrator, "call_llm", fake)
    return sent


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "MOCK_FORECAST", True)
    monkeypatch.setattr(config, "MOCK_DATA", True)
    monkeypatch.setattr(config, "MOCK_AGENT", True)


# ---- through the orchestrator ---------------------------------------------------------------------------

def test_chat_debt_question_calls_the_tool_and_every_pound_figure_is_verified(monkeypatch, mock_mode):
    sent = _script(monkeypatch, [
        _tool_use("t1", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100}),
        _text("Paying the 24% card first costs £9.64 in interest, against £11.29 the other way, "
              "so you save £1.65. Either way you are clear in 4 months."),
    ])
    reply = orchestrator.run_chat("sam", "I owe £200 on a card and £100 on a loan, what's the best way to pay them off?")
    assert any(t["name"] == "plan_debt_payoff" for t in sent[0]["tool_defs"])
    assert reply.numbers_used["avalanche_total_interest"] == 9.64
    quoted = [float(m.replace(",", "")) for m in CURRENCY_RE.findall(reply.text)]
    assert quoted == [9.64, 11.29, 1.65]
    assert all(q in reply.numbers_used.values() for q in quoted)


def test_chat_tool_result_sent_back_to_the_llm_is_valid_json_with_the_plan(monkeypatch, mock_mode):
    sent = _script(monkeypatch, [
        _tool_use("t1", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 100}),
        _text("Done."),
    ])
    orchestrator.run_chat("sam", "plan my debts")
    result_msg = sent[1]["messages"][-1]["content"][0]
    assert result_msg["type"] == "tool_result" and not result_msg.get("is_error")
    payload = json.loads(result_msg["content"])
    assert payload["avalanche"]["total_interest"] == 9.64 and payload["cap_month_1"] == 100


def test_chat_bad_tool_arguments_become_a_plain_apology_not_invented_numbers(monkeypatch, mock_mode):
    _script(monkeypatch, [
        _tool_use("t1", "plan_debt_payoff", {"debts": [], "monthly_budget": 100}),
        _text("You'll be debt-free in £5 months!"),   # LLM improvises after the failed tool
    ])
    reply = orchestrator.run_chat("sam", "plan my debts")
    assert "£5" not in reply.text and reply.numbers_used == {}


def test_chat_savings_goal_flow(monkeypatch, mock_mode):
    _script(monkeypatch, [
        _tool_use("t1", "plan_savings_goal", {"target_amount": 600, "target_date": "2027-05-07", "goal_name": "Holiday"}),
        _text("That needs £100.00 a month for 6 months."),
    ])
    reply = orchestrator.run_chat("sam", "Can I save £600 for a holiday by May?")
    assert reply.numbers_used["required_monthly"] == 100.0
    assert [float(m) for m in CURRENCY_RE.findall(reply.text)] == [100.0]


# ---- real data in real mode ----------------------------------------------------------------------------

@pytest.fixture
def real(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "pt.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    seed()


def test_debt_cap_uses_the_real_safe_to_spend_of_a_seeded_user(real):
    safe = fc.safe_to_spend("maya", config.TODAY).safe_amount
    out = tools.run_tool("maya", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 500})
    assert out["safe_to_spend"] == safe
    assert out["cap_month_1"] == min(500, max(safe, 0))
    for s in (out["avalanche"], out["snowball"]):
        assert s["first_month_total"] <= max(safe, 0) + 1e-9      # never above what is safe to spend


def test_salaried_persona_gets_a_feasible_emergency_fund_plan(real):
    out = tools.run_tool("alex", "plan_emergency_fund", {})
    assert out["feasible"] and out["reason"] == "ok" and out["target_amount"] > 0
    assert out["plan"]["required_monthly"] <= out["plan"]["available_monthly"]
    assert out["plan"]["already_saved"] == 1500          # alex's seeded 'Emergency fund' pot is credited
    assert out["plan"]["suggested_pot"] is None          # so no new pot is suggested (top up instead)
    assert out["numbers_used"]["required_monthly"] == out["plan"]["required_monthly"]


def test_a_new_pot_is_suggested_but_never_created_when_none_exists(real):
    out = tools.run_tool("alex", "plan_savings_goal", {"target_amount": 1200, "target_date": "2027-09-01",
                                                       "goal_name": "New bike"})
    assert out["feasible"]
    assert out["suggested_pot"] == {"name": "New bike", "amount": out["required_monthly"], "created": False}
    assert "New bike" not in [p.name for p in repository.get_pots("alex")]


def test_vulnerable_persona_is_told_honestly_it_is_not_affordable(real):
    out = tools.run_tool("sam", "plan_emergency_fund", {})
    assert not out["feasible"] and out["reason"] == "exceeds_surplus"
    assert "short" in out["explanation"] and out["plan"]["shortfall"] > 0


def test_tools_leave_the_database_untouched(real):
    before = (repository.get_pots("alex"), repository.get_transactions("alex"))
    tools.run_tool("alex", "plan_emergency_fund", {})
    tools.run_tool("alex", "plan_savings_goal", {"target_amount": 900, "target_date": "2027-06-01"})
    tools.run_tool("alex", "plan_debt_payoff", {"debts": TWO, "monthly_budget": 200})
    assert (repository.get_pots("alex"), repository.get_transactions("alex")) == before


def test_already_funded_goal_from_an_existing_pot(real):
    # alex's seeded 'Holiday' pot holds £600
    out = tools.run_tool("alex", "plan_savings_goal",
                         {"target_amount": 600, "target_date": "2027-05-01", "goal_name": "Holiday"})
    assert out["feasible"] and out["reason"] == "already_funded" and out["required_monthly"] == 0
