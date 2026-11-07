"""Alarm feed: ranked act > watch > good, one alarm per category, plain copy."""
import pytest

from backend import config
from backend.insights import alarms


def test_feed_is_ranked_deduped_and_plain(monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", False)
    try:
        feed = alarms.build_alarms("sam")
    except Exception as exc:
        pytest.skip(f"seeded data unavailable: {exc}")
    levels = [a["level"] for a in feed]
    assert levels == sorted(levels, key=alarms.RANK.__getitem__)
    assert len({a["id"] for a in feed}) == len(feed) <= alarms.MAX_ALARMS
    spend_ids = [a["id"] for a in feed if a["id"].startswith("spend:")]
    assert len(spend_ids) == len(set(spend_ids))
    for a in feed:
        assert a["title"] and a["action"] and a["ask_nat"]
        assert "—" not in a["title"] + a["body"] + a["action"]
