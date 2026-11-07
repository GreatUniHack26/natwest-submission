"""Tests for the regional benchmarks agent tool adapter (#41)."""
from __future__ import annotations

import sys
import types

import pytest

from backend.agent import benchmark_adapter, orchestrator
from contracts.schemas import User


def test_benchmark_tool_schema_shape():
    schema = benchmark_adapter.BENCHMARK_TOOL_SCHEMA
    assert schema["name"] == "get_benchmark"
    assert "neutral" in schema["description"].lower()
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    assert set(input_schema["properties"].keys()) == {"category", "household_size"}
    assert input_schema["additionalProperties"] is False


def test_is_benchmarks_available_when_absent_and_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "backend.benchmarks", None)  # None makes `import` raise: genuinely absent
    assert benchmark_adapter.is_benchmarks_available() is False

    dummy_mod = types.ModuleType("backend.benchmarks")
    monkeypatch.setitem(sys.modules, "backend.benchmarks", dummy_mod)
    assert benchmark_adapter.is_benchmarks_available() is False

    dummy_mod.get_benchmark = lambda region, household_size: {}
    assert benchmark_adapter.is_benchmarks_available() is True


@pytest.mark.parametrize(
    "bad_args",
    [
        {"household_size": 0},
        {"household_size": -1},
        {"household_size": True},
        {"household_size": False},
        {"household_size": "two"},
        {"household_size": 99},
        {"category": ""},
        {"category": "   "},
        {"category": 123},
        {"unexpected": "value"},
        ["not", "a", "dict"],
    ],
)
def test_validate_benchmark_args_rejects_invalid(bad_args):
    with pytest.raises(ValueError):
        benchmark_adapter.validate_benchmark_args(bad_args)


def test_validate_benchmark_args_accepts_valid():
    assert benchmark_adapter.validate_benchmark_args(None) == {}
    assert benchmark_adapter.validate_benchmark_args({}) == {}
    assert benchmark_adapter.validate_benchmark_args(
        {"category": " eating out ", "household_size": 2}
    ) == {"category": "eating out", "household_size": 2}


def test_run_get_benchmark_raises_when_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "backend.benchmarks", None)  # None makes `import` raise: genuinely absent
    with pytest.raises(RuntimeError, match="backend.benchmarks"):
        benchmark_adapter.run_get_benchmark("sam", {"category": "eating out"})


def test_run_get_benchmark_manchester_single_household_eating_out(monkeypatch):
    mock_mod = types.ModuleType("backend.benchmarks")
    mock_mod.get_benchmark = lambda region, household_size: {
        "region": region,
        "household_size": household_size,
        "categories": {
            "eating out": 85.0,
            "groceries": 190.0,
            "transport": 65.0,
        },
        "source": "ONS Family Spending",
    }
    monkeypatch.setitem(sys.modules, "backend.benchmarks", mock_mod)

    result = benchmark_adapter.run_get_benchmark("sam", {"category": "eating out"})

    assert result["region"] == "Manchester"
    assert result["household_size"] == 1
    assert result["category"] == "eating out"
    assert result["comparable"] is True
    assert "Neutral comparison" in result["framing_note"]

    numbers_used = result["numbers_used"]
    assert numbers_used["benchmark_eating_out"] == pytest.approx(85.0)
    # Fixture transactions for sam: Greggs -4.80 + Deliveroo -18.90 = 23.70
    assert numbers_used["user_eating_out_spend"] == pytest.approx(23.70)

    extracted = orchestrator.extract_numbers_used(result)
    assert extracted["benchmark_eating_out"] == pytest.approx(85.0)
    assert extracted["user_eating_out_spend"] == pytest.approx(23.70)


def test_run_get_benchmark_no_comparable_category_does_not_invent_numbers(monkeypatch):
    mock_mod = types.ModuleType("backend.benchmarks")
    mock_mod.get_benchmark = lambda region, household_size: {
        "categories": {
            "groceries": 190.0,
            "housing": 850.0,
        }
    }
    monkeypatch.setitem(sys.modules, "backend.benchmarks", mock_mod)

    result = benchmark_adapter.run_get_benchmark("sam", {"category": "pet care"})

    assert result["region"] == "Manchester"
    assert result["household_size"] == 1
    assert result["category"] == "pet care"
    assert result["comparable"] is False
    assert result["benchmark"] is None
    assert "No comparable regional benchmark category" in result["explanation"]
    assert "Neutral comparison" in result["framing_note"]
    assert "benchmark_pet_care" not in result["numbers_used"]
    assert result["numbers_used"] == {"user_pet_care_spend": 0.0}


def test_run_get_benchmark_infers_household_size_from_household_members(monkeypatch):
    mock_mod = types.ModuleType("backend.benchmarks")
    mock_mod.get_benchmark = lambda region, household_size: {"groceries": 320.0}
    monkeypatch.setitem(sys.modules, "backend.benchmarks", mock_mod)

    monkeypatch.setattr(
        benchmark_adapter.data,
        "get_user",
        lambda uid: User(
            id=uid,
            name="Sam",
            persona="Family",
            region="Manchester",
            household_id="hh_1",
            tone="friendly",
        ),
    )
    monkeypatch.setattr(
        benchmark_adapter.data,
        "get_household_members",
        lambda hid: [
            User(id="u1", name="A", persona="p", region="Manchester", household_id=hid),
            User(id="u2", name="B", persona="p", region="Manchester", household_id=hid),
            User(id="u3", name="C", persona="p", region="Manchester", household_id=hid),
        ],
    )

    result = benchmark_adapter.run_get_benchmark("sam", {})
    assert result["household_size"] == 3
    assert result["comparable"] is True
    assert result["numbers_used"]["benchmark_groceries"] == pytest.approx(320.0)
    assert result["numbers_used"]["user_groceries_spend"] == pytest.approx(23.40)
