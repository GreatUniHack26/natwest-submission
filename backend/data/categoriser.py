"""P1: need/want categorisation. Rules first, cached LLM only for unknown merchants.

Pre-compute labels (don't call the LLM live in the demo):
  0. User overrides (passed in; stored by the repository) beat everything below.
  1. Income (amount > 0) is always kind='income'.
  2. RULES match on whole words in the merchant name (so 'tfl' never hits 'Netflix').
  3. Unknown merchants are looked up in the on-disk cache (label_cache.json, committed so
     the demo works with no API key).
  4. Whatever is still unknown goes to the LLM in ONE batched call; results are cached.
  5. If there is no key or the call fails, fall back to ('other', 'want') and log a warning.
     Fallbacks are not cached, so a later run with a key can fix them.

`make seed` runs categorise() once, so labels are pre-computed in the DB.
"""
import json
import logging
import os
import re
from pathlib import Path

from backend import config
from contracts.schemas import Transaction

log = logging.getLogger(__name__)

FALLBACK = ("other", "want")
# Overridable for tests / other machines. Read at call time via the module attribute.
CACHE_PATH = Path(os.getenv("LABEL_CACHE_PATH", Path(__file__).with_name("label_cache.json")))

# whole-word phrase (lowercase) -> (category, kind). Must cover every generated merchant.
RULES: dict[str, tuple[str, str]] = {
    # housing, bills
    "rent": ("housing", "need"),
    "giffgaff": ("bills", "need"),
    "lebara": ("bills", "need"),
    "ee": ("bills", "need"),
    "octopus energy": ("bills", "need"),
    "british gas": ("bills", "need"),
    "zen internet": ("bills", "need"),
    "city council": ("bills", "need"),
    # groceries
    "tesco": ("groceries", "need"),
    "lidl": ("groceries", "need"),
    "aldi": ("groceries", "need"),
    "sainsbury": ("groceries", "need"),
    "waitrose": ("groceries", "need"),
    # transport
    "metrolink": ("transport", "need"),
    "tfl": ("transport", "need"),
    "first bus": ("transport", "need"),
    "shell": ("transport", "need"),
    # family essentials
    "little stars club": ("childcare", "need"),
    "primary school": ("school", "need"),
    "provident loan": ("debt", "need"),
    "course fee": ("education", "need"),
    # eating out
    "deliveroo": ("eating out", "want"),
    "greggs": ("eating out", "want"),
    "pret": ("eating out", "want"),
    "nando": ("eating out", "want"),
    "dominos": ("eating out", "want"),
    # subscriptions, shopping, leisure
    "spotify": ("subscriptions", "want"),
    "netflix": ("subscriptions", "want"),
    "disney": ("subscriptions", "want"),
    "puregym": ("fitness", "want"),
    "uniqlo": ("clothing", "want"),
    "primark": ("clothing", "want"),
}
_PATTERNS = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])"), v) for k, v in RULES.items()
]


def _rule_label(merchant: str) -> tuple[str, str] | None:
    name = merchant.lower()
    return next((v for pattern, v in _PATTERNS if pattern.search(name)), None)


def _key(merchant: str) -> str:
    return " ".join(merchant.lower().split())


def _load_cache() -> dict[str, tuple[str, str]]:
    try:
        raw = json.loads(CACHE_PATH.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable label cache %s: %s", CACHE_PATH, e)
        return {}
    return {k: (v["category"], v["kind"]) for k, v in raw.items() if _valid(v)}


def _save_cache(cache: dict[str, tuple[str, str]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    payload = {k: {"category": c, "kind": kd} for k, (c, kd) in sorted(cache.items())}
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(CACHE_PATH)  # atomic: a crash never leaves a half-written cache


def _valid(label) -> bool:
    return (
        isinstance(label, dict)
        and isinstance(label.get("category"), str) and label["category"].strip() != ""
        and label.get("kind") in ("need", "want")
    )


_PROMPT = """Classify each UK merchant name from a personal bank statement.
For each merchant give a short lowercase spending category (prefer one of: housing, bills,
groceries, transport, eating out, subscriptions, clothing, childcare, school, debt, health,
fitness, entertainment, other) and a kind: "need" (essential) or "want" (discretionary).
Reply with ONLY a JSON object mapping each merchant exactly as given to
{{"category": "...", "kind": "need" or "want"}}.

Merchants:
{merchants}"""


def _call_llm(prompt: str) -> str:
    """The single network call. Lazy import so tests and offline demos don't need the SDK."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
    response = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _parse_llm_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # tolerate markdown fences
    return json.loads(text)


def llm_label(merchants: list[str]) -> dict[str, tuple[str, str]]:
    """Label ALL given merchants with ONE LLM call. Returns only the valid labels (keyed by
    the merchant as given); missing/invalid ones are simply absent. Never raises."""
    if not merchants:
        return {}
    if not config.LLM_API_KEY:
        log.warning("No LLM_API_KEY: %d unlabelled merchants fall back to %s", len(merchants), FALLBACK)
        return {}
    prompt = _PROMPT.format(merchants=json.dumps(merchants, indent=2))
    try:
        parsed = _parse_llm_json(_call_llm(prompt))
    except Exception as e:  # network, auth, bad JSON: the demo must keep working
        log.warning("LLM labelling failed (%s); falling back to %s", e, FALLBACK)
        return {}
    if not isinstance(parsed, dict):
        log.warning("LLM returned %s, expected a JSON object", type(parsed).__name__)
        return {}
    return {
        m: (parsed[m]["category"].strip().lower(), parsed[m]["kind"])
        for m in merchants if m in parsed and _valid(parsed[m])
    }


def categorise(
    transactions: list[Transaction],
    overrides: dict[str, tuple[str, str]] | None = None,
) -> list[Transaction]:
    """Return copies with category/kind set. Pure apart from the label cache on disk.

    `overrides` maps transaction id -> (category, kind) and beats everything else (income
    sign, rules, cache, LLM). Overridden transactions are never sent to the LLM.
    """
    overrides = overrides or {}
    unknown: dict[str, str] = {}  # cache key -> merchant as first seen
    for t in transactions:
        if t.id not in overrides and t.amount <= 0 and _rule_label(t.merchant) is None:
            unknown.setdefault(_key(t.merchant), t.merchant)

    labels: dict[str, tuple[str, str]] = {}
    if unknown:
        cache = _load_cache()
        labels = {k: cache[k] for k in unknown if k in cache}
        missing = [m for k, m in unknown.items() if k not in labels]
        if missing:
            fresh = llm_label(missing)
            if fresh:
                cache.update({_key(m): label for m, label in fresh.items()})
                _save_cache(cache)
                labels.update({_key(m): label for m, label in fresh.items()})

    out = []
    for t in transactions:
        if t.id in overrides:
            category, kind = overrides[t.id]
        elif t.amount > 0:
            category, kind = "income", "income"
        else:
            category, kind = _rule_label(t.merchant) or labels.get(_key(t.merchant), FALLBACK)
        out.append(t.model_copy(update={"category": category, "kind": kind}))
    return out
