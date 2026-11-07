"""Issue #6 unit tests: rules, cache, batched LLM labelling, fallbacks. No real network calls."""
import datetime as dt
import json
import logging

import pytest

from backend import config
from backend.data import categoriser
from backend.data.categoriser import RULES, categorise
from backend.data.generator import generate_household, generate_persona
from contracts.schemas import Transaction


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Throwaway cache, no key, and any LLM call fails the test unless a test installs a fake."""
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(config, "LLM_API_KEY", "")

    def no_llm(prompt):
        raise AssertionError("unexpected LLM call")

    monkeypatch.setattr(categoriser, "_call_llm", no_llm)
    return tmp_path / "cache.json"


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.reply(prompt) if callable(self.reply) else self.reply


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")


def tx(merchant, amount=-10.0, tid=None):
    return Transaction(id=tid or f"t-{merchant}-{amount}", user_id="u", date=dt.date(2026, 11, 1),
                       merchant=merchant, amount=amount, category="?", kind="want")


def labels(txs):
    return [(t.category, t.kind) for t in categorise(txs)]


# ---- rules -----------------------------------------------------------------------

def test_rule_kinds_are_valid_and_categories_nonempty():
    assert all(kind in ("need", "want") and cat for cat, kind in RULES.values())


@pytest.mark.parametrize("merchant,expected", [
    ("Netflix", ("subscriptions", "want")),       # contains 'tfl' as a substring only
    ("TfL Travel", ("transport", "need")),
    ("TESCO STORES 4521", ("groceries", "need")),
    ("Landlord (rent)", ("housing", "need")),
    ("Sainsbury's", ("groceries", "need")),
    ("Greggs (Uni)", ("eating out", "want")),
    ("EE", ("bills", "need")),
])
def test_rules_match_whole_words_case_insensitively(merchant, expected):
    assert labels([tx(merchant)]) == [expected]


@pytest.mark.parametrize("merchant", ["Parentpay", "Current Account Fee", "Sheet Music", "Employee Perks"])
def test_rules_do_not_match_inside_other_words(merchant):
    """'rent' in Parentpay/Current, 'ee' in Employee, 'shell' in nothing else: all unknown."""
    assert labels([tx(merchant)]) == [categoriser.FALLBACK]


def test_income_is_always_income_even_for_ruled_merchants():
    assert labels([tx("Tesco refund", 12.0), tx("Mystery Co", 500.0)]) == [("income", "income")] * 2


def test_pure_rules_make_no_llm_call_and_no_cache_file(isolated):
    categorise([tx("Tesco"), tx("Lidl"), tx("Giffgaff")])
    assert not isolated.exists()


# ---- generated data is fully covered -------------------------------------------------

def _all_generated():
    members = [generate_persona("sam"), generate_persona("salaried"), *generate_household("family")]
    return [(u.id, txs) for u, txs, _ in members]


@pytest.mark.parametrize("uid,txs", _all_generated(), ids=lambda x: x if isinstance(x, str) else "")
def test_every_generated_transaction_gets_category_and_kind(uid, txs):
    out = categorise(txs)
    assert len(out) == len(txs)
    assert all(t.category and t.kind in ("need", "want", "income") for t in out)
    assert all(t.category != "other" for t in out)  # nothing fell through to the fallback


@pytest.mark.parametrize("uid,txs", _all_generated(), ids=lambda x: x if isinstance(x, str) else "")
def test_categoriser_agrees_with_generator_labels(uid, txs):
    """The rules reproduce exactly what each generator planted (so seeding changes nothing)."""
    assert categorise(txs) == txs


def test_netflix_is_not_transport():
    sam = generate_persona("sam")[1]
    netflix = [t for t in categorise(sam) if t.merchant == "Netflix"]
    assert netflix and {t.category for t in netflix} == {"subscriptions"}


# ---- cache ------------------------------------------------------------------------

def test_cache_hit_needs_no_key_and_no_llm(isolated):
    isolated.write_text(json.dumps({"corner cafe": {"category": "eating out", "kind": "want"}}))
    assert labels([tx("Corner Cafe")]) == [("eating out", "want")]  # key is normalised


def test_cache_key_normalises_case_and_whitespace(isolated):
    isolated.write_text(json.dumps({"corner cafe": {"category": "eating out", "kind": "want"}}))
    assert labels([tx("  CORNER   cafe ")]) == [("eating out", "want")]


def test_corrupt_cache_is_ignored_not_fatal(isolated, caplog):
    isolated.write_text("{not json")
    with caplog.at_level(logging.WARNING):
        assert labels([tx("Mystery Co")]) == [categoriser.FALLBACK]
    assert "unreadable" in caplog.text


def test_invalid_cache_entries_are_skipped(isolated):
    isolated.write_text(json.dumps({
        "good co": {"category": "health", "kind": "need"},
        "bad kind": {"category": "x", "kind": "income"},
        "no category": {"kind": "want"},
        "not a dict": "oops",
    }))
    assert categoriser._load_cache() == {"good co": ("health", "need")}


# ---- LLM: batching, caching ------------------------------------------------------------

def _reply_for(mapping):
    return lambda prompt: json.dumps({m: {"category": c, "kind": k} for m, (c, k) in mapping.items()})


def test_all_unknown_merchants_go_in_one_call(monkeypatch, with_key):
    fake = FakeLLM(_reply_for({"Boots": ("health", "need"), "Zara": ("clothing", "want"),
                               "Vue Cinema": ("entertainment", "want")}))
    monkeypatch.setattr(categoriser, "_call_llm", fake)
    out = labels([tx("Boots"), tx("Zara"), tx("Vue Cinema"), tx("Tesco")])
    assert len(fake.prompts) == 1
    assert all(m in fake.prompts[0] for m in ("Boots", "Zara", "Vue Cinema"))
    assert "Tesco" not in fake.prompts[0]  # ruled merchants are never sent
    assert out == [("health", "need"), ("clothing", "want"), ("entertainment", "want"), ("groceries", "need")]


def test_duplicates_and_case_variants_are_sent_once(monkeypatch, with_key):
    fake = FakeLLM(_reply_for({"Boots": ("health", "need")}))
    monkeypatch.setattr(categoriser, "_call_llm", fake)
    labels([tx("Boots", tid="a"), tx("Boots", tid="b"), tx("BOOTS", tid="c")])
    assert fake.prompts[0].count("Boots") + fake.prompts[0].count("BOOTS") == 1


def test_income_is_never_sent_to_the_llm(monkeypatch, with_key):
    fake = FakeLLM(_reply_for({"Boots": ("health", "need")}))
    monkeypatch.setattr(categoriser, "_call_llm", fake)
    labels([tx("Boots"), tx("Payroll Ltd", 1000.0)])
    assert "Payroll" not in fake.prompts[0]


def test_results_are_cached_and_second_run_makes_zero_calls(monkeypatch, with_key, isolated):
    fake = FakeLLM(_reply_for({"Boots": ("health", "need")}))
    monkeypatch.setattr(categoriser, "_call_llm", fake)
    assert labels([tx("Boots")]) == [("health", "need")]
    assert json.loads(isolated.read_text()) == {"boots": {"category": "health", "kind": "need"}}

    monkeypatch.setattr(categoriser, "_call_llm", lambda p: pytest.fail("cache miss"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")  # and works with no key at all
    assert labels([tx("Boots")]) == [("health", "need")]


def test_only_uncached_merchants_are_sent(monkeypatch, with_key, isolated):
    isolated.write_text(json.dumps({"boots": {"category": "health", "kind": "need"}}))
    fake = FakeLLM(_reply_for({"Zara": ("clothing", "want")}))
    monkeypatch.setattr(categoriser, "_call_llm", fake)
    labels([tx("Boots"), tx("Zara")])
    assert len(fake.prompts) == 1 and "Zara" in fake.prompts[0] and "Boots" not in fake.prompts[0]
    assert set(json.loads(isolated.read_text())) == {"boots", "zara"}  # old entry kept


def test_cache_file_is_sorted_and_leaves_no_temp_file(monkeypatch, with_key, isolated):
    monkeypatch.setattr(categoriser, "_call_llm", FakeLLM(_reply_for(
        {"Zara": ("clothing", "want"), "Boots": ("health", "need")})))
    labels([tx("Zara"), tx("Boots")])
    assert list(json.loads(isolated.read_text())) == ["boots", "zara"]
    assert not isolated.with_suffix(".tmp").exists()


def test_llm_category_is_normalised(monkeypatch, with_key):
    monkeypatch.setattr(categoriser, "_call_llm", FakeLLM(_reply_for({"Boots": ("  Health ", "need")})))
    assert labels([tx("Boots")]) == [("health", "need")]


def test_markdown_fenced_json_is_accepted(monkeypatch, with_key):
    monkeypatch.setattr(categoriser, "_call_llm", FakeLLM(
        '```json\n{"Boots": {"category": "health", "kind": "need"}}\n```'))
    assert labels([tx("Boots")]) == [("health", "need")]


# ---- fallbacks ----------------------------------------------------------------------

def test_no_key_falls_back_warns_and_does_not_cache(isolated, caplog):
    with caplog.at_level(logging.WARNING):
        assert labels([tx("Mystery Co")]) == [categoriser.FALLBACK]
    assert "LLM_API_KEY" in caplog.text
    assert not isolated.exists()


@pytest.mark.parametrize("reply", ["not json at all", "[1, 2]", '"str"', "{}"])
def test_bad_llm_output_falls_back_without_caching(monkeypatch, with_key, isolated, reply):
    monkeypatch.setattr(categoriser, "_call_llm", FakeLLM(reply))
    assert labels([tx("Boots")]) == [categoriser.FALLBACK]
    assert not isolated.exists()


def test_llm_exception_falls_back(monkeypatch, with_key, isolated, caplog):
    def boom(prompt):
        raise ConnectionError("network down")

    monkeypatch.setattr(categoriser, "_call_llm", boom)
    with caplog.at_level(logging.WARNING):
        assert labels([tx("Boots")]) == [categoriser.FALLBACK]
    assert "network down" in caplog.text and not isolated.exists()


def test_one_invalid_entry_does_not_poison_the_rest(monkeypatch, with_key, isolated):
    monkeypatch.setattr(categoriser, "_call_llm", FakeLLM(json.dumps({
        "Boots": {"category": "health", "kind": "need"},
        "Zara": {"category": "clothing", "kind": "maybe"},     # invalid kind
        "Vue": {"category": "", "kind": "want"},               # empty category
    })))
    assert labels([tx("Boots"), tx("Zara"), tx("Vue")]) == [("health", "need"), categoriser.FALLBACK, categoriser.FALLBACK]
    assert set(json.loads(isolated.read_text())) == {"boots"}  # only the valid one is cached


def test_fallback_is_retried_once_a_key_exists(monkeypatch):
    assert labels([tx("Boots")]) == [categoriser.FALLBACK]  # no key: fallback, nothing cached
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(categoriser, "_call_llm", FakeLLM(_reply_for({"Boots": ("health", "need")})))
    assert labels([tx("Boots")]) == [("health", "need")]


# ---- purity ---------------------------------------------------------------------------

def test_inputs_not_mutated_and_order_preserved():
    src = [tx("Tesco", tid="1"), tx("Lidl", tid="2"), tx("Giffgaff", tid="3")]
    snapshot = [t.model_copy() for t in src]
    out = categorise(src)
    assert src == snapshot
    assert [t.id for t in out] == ["1", "2", "3"]
    assert out[0] is not src[0]


def test_empty_input():
    assert categorise([]) == []


def test_committed_cache_file_is_valid_if_present():
    path = categoriser.Path(categoriser.__file__).with_name("label_cache.json")
    if path.exists():
        raw = json.loads(path.read_text())
        assert all(categoriser._valid(v) for v in raw.values())
        assert list(raw) == sorted(raw)
