"""Focused unit and integration tests for Issue #16: Agent LLM tool-calling loop (orchestrator)."""
import re
from unittest.mock import MagicMock

import httpx
import pytest

from backend import agent, config
from backend.agent import orchestrator, tools
from contracts.schemas import User

CURRENCY_RE = re.compile(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)")


def test_thirty_pound_shirt_triggers_simulate_purchase_and_merges_numbers(monkeypatch):
    """'Can I afford a £30 shirt?' calls simulate_purchase(amount=30) and returns verified numbers."""
    monkeypatch.setattr(config, "MOCK_FORECAST", True)
    monkeypatch.setattr(config, "LLM_MODEL", "claude-sonnet-5-5")

    recorded_calls = []
    real_run_tool = tools.run_tool

    def spy_run_tool(user_id: str, name: str, args: dict):
        recorded_calls.append((user_id, name, args))
        return real_run_tool(user_id, name, args)

    monkeypatch.setattr(tools, "run_tool", spy_run_tool)

    llm_responses = iter(
        [
            {
                "id": "msg_1",
                "role": "assistant",
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_shirt_30",
                        "name": "simulate_purchase",
                        "input": {"amount": 30},
                    }
                ],
            },
            {
                "id": "msg_2",
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Yes, you can afford the £30 shirt. Your safe-to-spend is £210, "
                            "leaving £180 safe after this purchase, though Black Friday on 27 Nov could save you money."
                        ),
                    }
                ],
            },
        ]
    )

    llm_calls = []

    def fake_call_llm(**kwargs):
        llm_calls.append(kwargs)
        return next(llm_responses)

    monkeypatch.setattr(orchestrator, "call_llm", fake_call_llm)

    reply = orchestrator.run_chat("sam", "Can I afford a £30 shirt?", tone="friendly")

    # 1. Verify simulate_purchase was triggered with £30
    assert len(recorded_calls) == 1
    assert recorded_calls[0] == ("sam", "simulate_purchase", {"amount": 30})

    # 2. Verify numbers_used matches PurchaseVerdict fixture
    assert reply.numbers_used == {
        "price": 30.0,
        "safe_to_spend": 210.0,
        "safe_after": 180.0,
    }

    # 3. Verify every £ figure in reply.text is backed by numbers_used
    quoted_amounts = [float(m.replace(",", "")) for m in CURRENCY_RE.findall(reply.text)]
    assert quoted_amounts == [30.0, 210.0, 180.0]
    for amt in quoted_amounts:
        assert amt in reply.numbers_used.values()

    # 4. Verify model pinning and tool schemas passed to LLM
    assert llm_calls[0]["model"] == "claude-sonnet-5-5"
    assert llm_calls[0]["tool_defs"] == tools.TOOLS


def test_failed_tool_produces_plain_apology_without_invented_numbers(monkeypatch):
    """When a tool fails, the agent returns a safe apology and never invents financial figures."""

    def failing_tool(user_id: str, name: str, args: dict):
        raise RuntimeError("Forecast service failed")

    monkeypatch.setattr(tools, "run_tool", failing_tool)

    # Case A: LLM attempts to hallucinate £210 after tool error -> orchestrator blocks it
    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_fail_1",
                        "name": "simulate_purchase",
                        "input": {"amount": 30},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "text",
                        "text": "You have £210 safe to spend so yes, you can afford the £30 shirt.",
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    reply = orchestrator.run_chat("sam", "Can I afford a £30 shirt?", tone="friendly")
    assert reply.numbers_used == {}
    assert CURRENCY_RE.findall(reply.text) == []
    assert "sorry" in reply.text.lower() or "couldn't" in reply.text.lower()


def test_failed_tool_when_llm_apologises_plainly(monkeypatch):
    """When a tool fails and the LLM returns a plain apology with no numbers, it is preserved."""

    def failing_tool(user_id: str, name: str, args: dict):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(tools, "run_tool", failing_tool)

    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_fail_2",
                        "name": "get_safe_to_spend",
                        "input": {},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Sorry, the safe-to-spend tool failed so I cannot check your figures right now.",
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    reply = orchestrator.run_chat("sam", "What is my safe to spend?", tone="direct")
    assert reply.numbers_used == {}
    assert CURRENCY_RE.findall(reply.text) == []
    assert "sorry" in reply.text.lower()


@pytest.mark.parametrize(
    "tool_name,bad_args",
    [
        ("simulate_purchase", {}),  # missing required amount
        ("simulate_purchase", {"amount": -10}),  # negative amount
        ("simulate_purchase", {"amount": 0}),  # zero amount
        ("simulate_purchase", {"amount": True}),  # boolean instead of number
        ("simulate_purchase", {"amount": "thirty"}),  # string instead of number
        ("simulate_purchase", {"amount": 30, "date": "not-a-date"}),  # malformed date
        ("simulate_purchase", {"amount": 30, "date": 20261107}),  # non-string date
        ("simulate_purchase", {"amount": 30, "extra_field": 1}),  # unexpected property
        ("get_safe_to_spend", {"unexpected": "arg"}),  # unexpected property
        ("get_upcoming_sales", {"within_days": 366}),  # out of range days
        ("get_upcoming_sales", {"within_days": -5}),  # negative days
        ("get_upcoming_sales", {"within_days": 30.5}),  # float instead of int
        ("get_upcoming_sales", {"within_days": False}),  # bool instead of int
        ("get_forecast", {"horizon_days": 0}),  # out of range
        ("get_forecast", {"horizon_days": 500}),  # out of range
        ("get_forecast", {"horizon_days": "90"}),  # string instead of int
        ("get_alerts", ["not-a-dict"]),  # non-dict args
    ],
)
def test_invalid_tool_arguments_are_rejected(tool_name, bad_args):
    """Invalid arguments to tools.run_tool raise ValueError."""
    with pytest.raises(ValueError):
        tools.run_tool("sam", tool_name, bad_args)


def test_unknown_tools_are_rejected(monkeypatch):
    """Unknown tool names raise ValueError in run_tool and produce a safe apology in run_chat."""
    with pytest.raises(ValueError, match="Unknown tool"):
        tools.run_tool("sam", "predict_lottery_numbers", {})

    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_unknown",
                        "name": "predict_lottery_numbers",
                        "input": {},
                    }
                ]
            }
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    reply = orchestrator.run_chat("sam", "What are the lottery numbers?", tone="friendly")
    assert reply.numbers_used == {}
    assert CURRENCY_RE.findall(reply.text) == []
    assert "sorry" in reply.text.lower()


def test_missing_tone_uses_users_saved_tone_and_supports_all_tones(monkeypatch):
    """When tone is None, run_chat uses the user's saved tone from data.get_user."""
    monkeypatch.setattr(
        "backend.data.get_user",
        lambda uid: User(
            id=uid,
            name="Sam",
            persona="Student",
            region="Manchester",
            tone="simple",
        ),
    )

    captured_prompts = []

    def fake_call_llm(**kwargs):
        captured_prompts.append(kwargs["system_prompt"])
        return {"content": [{"type": "text", "text": "Your safe money is £210."}]}

    monkeypatch.setattr(orchestrator, "call_llm", fake_call_llm)

    orchestrator.run_chat("sam", "How much can I spend?", tone=None)
    assert len(captured_prompts) == 1
    assert "You are FinTime" in captured_prompts[0]
    assert "reading age ~9" in captured_prompts[0]

    # Verify all three tones build distinct prompts containing base.md + tone_<tone>.md
    for tone_name, expected_phrase in [
        ("friendly", "supportive friend"),
        ("direct", "direct and concise"),
        ("simple", "reading age ~9"),
    ]:
        prompt = orchestrator.build_system_prompt(tone_name)
        assert "Never do arithmetic yourself" in prompt
        assert expected_phrase in prompt


def test_multiple_tool_rounds_merge_numbers_and_terminate(monkeypatch):
    """Multiple tool-calling rounds execute sequentially, merge numbers_used, and terminate."""
    monkeypatch.setattr(config, "MOCK_FORECAST", True)

    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_round_1",
                        "name": "get_safe_to_spend",
                        "input": {},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_round_2",
                        "name": "simulate_purchase",
                        "input": {"amount": 30},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Your balance is £1640 with £210 safe to spend. "
                            "Buying the £30 item leaves £180 safe to spend."
                        ),
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    reply = orchestrator.run_chat("sam", "Check my balance and if I can afford £30", tone="direct")

    assert reply.numbers_used == {
        "balance": 1640.0,
        "pots_total": 1250.0,
        "upcoming_bills": 180.0,
        "safe_amount": 210.0,
        "price": 30.0,
        "safe_to_spend": 210.0,
        "safe_after": 180.0,
    }
    assert "£1640" in reply.text
    assert "£180" in reply.text


def test_max_tool_rounds_prevents_infinite_loop(monkeypatch):
    """If the LLM endlessly requests tools, run_chat stops after MAX_TOOL_ROUNDS."""
    monkeypatch.setattr(config, "MOCK_FORECAST", True)

    tool_call_count = 0
    real_run_tool = tools.run_tool

    def counting_run_tool(user_id: str, name: str, args: dict):
        nonlocal tool_call_count
        tool_call_count += 1
        return real_run_tool(user_id, name, args)

    monkeypatch.setattr(tools, "run_tool", counting_run_tool)

    # Always return a tool_use block forever
    monkeypatch.setattr(
        orchestrator,
        "call_llm",
        lambda **kwargs: {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_loop",
                    "name": "get_safe_to_spend",
                    "input": {},
                }
            ]
        },
    )

    reply = orchestrator.run_chat("sam", "Loop forever", tone="friendly")
    assert tool_call_count == orchestrator.MAX_TOOL_ROUNDS
    assert reply.text == orchestrator.MAX_ROUNDS_APOLOGY


def test_timeout_and_unavailable_llm_handling(monkeypatch):
    """Timeouts and HTTP errors from the LLM API are handled safely with a configured timeout."""
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "claude-sonnet-5-5")

    captured_timeout = None
    captured_model = None

    def timeout_post(url, *, headers=None, json=None, timeout=None):
        nonlocal captured_timeout, captured_model
        captured_timeout = timeout
        captured_model = json.get("model") if json else None
        raise httpx.ReadTimeout("Request timed out")

    monkeypatch.setattr(httpx, "post", timeout_post)

    reply = orchestrator.run_chat("sam", "Can I afford £30?", tone="friendly")
    assert captured_timeout == orchestrator.LLM_TIMEOUT_SECONDS
    assert captured_model == "claude-sonnet-5-5"
    assert reply.text == orchestrator.LLM_UNAVAILABLE_APOLOGY
    assert reply.numbers_used == {}
    assert CURRENCY_RE.findall(reply.text) == []


def test_mock_agent_and_mock_forecast_compatibility(monkeypatch):
    """agent.chat respects MOCK_AGENT=True (fixture) and MOCK_AGENT=False + MOCK_FORECAST=True."""
    # 1. MOCK_AGENT = True returns the fixture directly without calling LLM
    monkeypatch.setattr(config, "MOCK_AGENT", True)
    mock_llm = MagicMock(side_effect=AssertionError("LLM should not be called when MOCK_AGENT=True"))
    monkeypatch.setattr(orchestrator, "call_llm", mock_llm)

    mock_reply = agent.chat("sam", "Can I afford this shirt?")
    assert mock_reply.numbers_used == {"price": 30.0, "safe_to_spend": 210.0, "safe_after": 180.0}
    assert "£30 shirt" in mock_reply.text

    # 2. MOCK_AGENT = False and MOCK_FORECAST = True runs orchestrator against forecast fixtures
    monkeypatch.setattr(config, "MOCK_AGENT", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", True)

    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "get_safe_to_spend",
                        "input": {},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "text",
                        "text": "You have £210 safe to spend after £1250 in pots and £180 in bills.",
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    live_reply = agent.chat("sam", "What is my safe to spend?")
    assert live_reply.numbers_used["safe_amount"] == 210.0
    assert live_reply.numbers_used["balance"] == 1640.0


def test_get_tips_tool_integration_in_orchestrator(monkeypatch):
    """get_tips tool executes via tools.run_tool and merges est_saving into ChatReply.numbers_used."""
    monkeypatch.setattr(config, "MOCK_DATA", True)

    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_tips",
                        "name": "get_tips",
                        "input": {},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "As a student with transport and rent spend, you may want to check the "
                            "16-25 Railcard (estimated £3.07 saving on your recent travel) and "
                            "Council Tax student exemptions on GOV.UK. General information, not financial or tax advice."
                        ),
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    reply = orchestrator.run_chat("sam", "Do you have any savings tips?", tone="friendly")
    assert "tip_railcard_16_25_est_saving" in reply.numbers_used
    assert reply.numbers_used["tip_railcard_16_25_est_saving"] == 3.07
    assert "GOV.UK" in reply.text


def test_get_benchmark_tool_integration_in_orchestrator(monkeypatch):
    """When backend.benchmarks is available, get_benchmark is exposed and merges numbers_used."""
    import sys
    import types

    monkeypatch.setattr(config, "MOCK_DATA", True)

    fake_benchmarks = types.ModuleType("backend.benchmarks")
    fake_benchmarks.get_benchmark = lambda region, household_size: {  # type: ignore[attr-defined]
        "region": region,
        "household_size": household_size,
        "categories": {"eating out": 95.0, "groceries": 180.0},
        "source": "ONS Family Spending",
    }
    monkeypatch.setitem(sys.modules, "backend.benchmarks", fake_benchmarks)

    active_names = [t["name"] for t in tools.get_active_tools()]
    assert "get_benchmark" in active_names

    responses = iter(
        [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_bench",
                        "name": "get_benchmark",
                        "input": {"category": "eating out", "household_size": 1},
                    }
                ]
            },
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "For a 1-person household in Manchester, the ONS benchmark for eating out is £95, "
                            "compared with your £23.70 spend over the last 30 days."
                        ),
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: next(responses))

    reply = orchestrator.run_chat("sam", "Am I spending more than similar households on eating out?", tone="friendly")
    assert reply.numbers_used["benchmark_eating_out"] == 95.0
    assert reply.numbers_used["user_eating_out_spend"] == 23.7


def test_offline_connect_error_and_demo_mode_fallback_in_orchestrator(monkeypatch):
    """When network fails with ConnectError or DEMO_MODE=1 is set, run_chat serves deterministic fallback."""
    monkeypatch.setattr(config, "MOCK_FORECAST", True)

    def offline_call_llm(**kwargs):
        raise httpx.ConnectError("Network is unreachable")

    monkeypatch.setattr(orchestrator, "call_llm", offline_call_llm)

    reply = orchestrator.run_chat("sam", "Can I afford a £30 shirt?", tone="friendly")
    assert reply.numbers_used["price"] == 30.0
    assert reply.numbers_used["safe_to_spend"] == 210.0
    assert reply.numbers_used["safe_after"] == 180.0
    assert "£30" in reply.text
    assert "£210" in reply.text
    assert "£180" in reply.text


