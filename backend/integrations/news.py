"""UK cost-of-living / economy headlines for the coach.

Primary source is FinTime's n8n workflow (``N8N_NEWS_WEBHOOK_URL``); when that is not
configured or fails, a few public RSS feeds are fetched directly. Everything returned is
third-party text that will be shown to an LLM, so it is treated as untrusted data: HTML and
control characters are stripped, lengths are capped and nothing is added that reads like an
instruction. This module never raises to its caller.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

import httpx

N8N_ENV = "N8N_NEWS_WEBHOOK_URL"
N8N_TIMEOUT_S = 6.0
RSS_TIMEOUT_S = 6.0
CACHE_TTL_S = 15 * 60
MAX_ITEMS = 10
SUMMARY_MAX = 240
TITLE_MAX = 200
TOPIC_MAX = 60
USER_AGENT = "FinTime/0.1 (cost-of-living news; +https://github.com/GreatUniHack26)"

RSS_FEEDS: list[tuple[str, str]] = [
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC News"),
    ("https://www.theguardian.com/money/rss", "The Guardian"),
    ("https://www.bankofengland.co.uk/rss/news", "Bank of England"),
]

# Topic tag -> keywords. Order matters: the first matching topic labels the item.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "energy": ["energy", "price cap", "ofgem", "gas bill", "electricity", "energy bill"],
    "fuel": ["fuel", "petrol", "diesel"],
    "interest rates": ["interest rate", "interest rates", "bank rate", "base rate", "mortgage", "mortgages"],
    "inflation": ["inflation", "cpi", "food prices", "cost of living", "cost-of-living"],
    "wages": ["wages", "wage", "minimum wage", "living wage", "pay rise"],
    "benefits": ["benefits", "universal credit", "state pension", "dwp"],
    "housing": ["rent", "rents", "renters", "landlord"],
    "tax": ["council tax", "budget", "tax", "taxes", "income tax", "national insurance"],
}

_ALL_KEYWORDS = sorted({k for kws in TOPIC_KEYWORDS.values() for k in kws}, key=len, reverse=True)
_KEYWORD_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _ALL_KEYWORDS) + r")\b", re.I)
_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏ -‮⁦-⁩﻿]")
_WS_RE = re.compile(r"\s+")
_XML_INVALID_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Sanitising helpers
# ---------------------------------------------------------------------------

def _clean_text(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    text = str(value)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)  # entities may have hidden tags
    text = _CTRL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > max_len:
        cut = text[: max_len - 1].rsplit(" ", 1)[0] or text[: max_len - 1]
        text = cut.rstrip(" ,.;:") + "…"
    return text


def _clean_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    url = _CTRL_RE.sub("", value).strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return url[:500]


def _iso_date(value: Any) -> str:
    """Best-effort conversion of RSS/ISO dates to an ISO-8601 UTC string; '' if unknown."""
    if not value or not isinstance(value, str):
        return ""
    raw = value.strip()
    parsed: dt.datetime | None = None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _publisher_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower() if url else ""
    return host[4:] if host.startswith("www.") else host


def _topic_terms(topic: str | None) -> list[str]:
    if not topic:
        return []
    key = topic.strip().lower()
    for name, kws in TOPIC_KEYWORDS.items():
        if key == name or key in kws or name.startswith(key):
            return [name, *kws]
    return [w for w in re.split(r"[^a-z0-9]+", key) if len(w) > 2] or [key]


def _matches_terms(text: str, terms: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(t) + r"\b", text, re.I) for t in terms)


def _classify(text: str) -> str | None:
    for name, kws in TOPIC_KEYWORDS.items():
        if _matches_terms(text, kws):
            return name
    return None


def _normalise_item(raw: dict[str, Any], default_publisher: str = "") -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("json"), dict):  # n8n item envelope
        raw = raw["json"]
    title = _clean_text(raw.get("title") or raw.get("headline"), TITLE_MAX)
    if not title:
        return None
    summary = _clean_text(
        raw.get("summary") or raw.get("description") or raw.get("contentSnippet") or raw.get("content"),
        SUMMARY_MAX,
    )
    url = _clean_url(raw.get("url") or raw.get("link"))
    published = _iso_date(raw.get("published") or raw.get("pubDate") or raw.get("isoDate") or raw.get("date"))
    publisher = _clean_text(
        raw.get("publisher") or raw.get("source") or default_publisher or _publisher_from_url(url), 60
    )
    topic = _clean_text(raw.get("topic"), 40) or _classify(f"{title} {summary}") or "economy"
    return {
        "title": title,
        "summary": summary,
        "url": url,
        "published": published,
        "publisher": publisher,
        "topic": topic,
    }


def _rank(items: list[dict[str, str]], topic: str | None) -> list[dict[str, str]]:
    """De-duplicate, then order topic matches first and newest first within each group."""
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        key = (item["url"] or item["title"]).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    terms = _topic_terms(topic)
    unique.sort(key=lambda i: i["published"], reverse=True)
    if terms:
        unique.sort(key=lambda i: not _matches_terms(f"{i['title']} {i['summary']} {i['topic']}", terms))
    return unique[:MAX_ITEMS]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def _fetch_n8n(url: str, topic: str | None, limit: int) -> list[dict[str, str]]:
    resp = httpx.post(
        url,
        json={"topic": topic, "limit": limit, "region": "UK"},
        timeout=N8N_TIMEOUT_S,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise ValueError("n8n response is not a list of items")
    # A single-item n8n response may wrap the whole payload as [{"items": [...]}].
    if len(data) == 1 and isinstance(data[0], dict) and isinstance(data[0].get("items"), list):
        data = data[0]["items"]
    items = [n for n in (_normalise_item(r) for r in data) if n]
    return _rank(items, topic)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(el: ET.Element, *names: str) -> str:
    for child in el:
        name = _local(child.tag)
        if name in names:
            if name == "link" and child.get("href"):
                return child.get("href", "")
            if child.text:
                return child.text
    return ""


def parse_feed(xml_text: str, publisher: str) -> list[dict[str, str]]:
    """Parse RSS 2.0 or Atom into normalised items (no keyword filtering)."""
    if "<!ENTITY" in xml_text[:4096].upper():
        return []  # refuse entity declarations outright
    root = ET.fromstring(_XML_INVALID_RE.sub("", xml_text))
    entries = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    out: list[dict[str, str]] = []
    for el in entries:
        raw = {
            "title": _child_text(el, "title"),
            "summary": _child_text(el, "description", "summary", "content"),
            "url": _child_text(el, "link", "guid"),
            "published": _child_text(el, "pubdate", "published", "updated", "date"),
        }
        item = _normalise_item(raw, default_publisher=publisher)
        if item:
            out.append(item)
    return out


def _fetch_one_feed(feed: tuple[str, str]) -> list[dict[str, str]]:
    url, publisher = feed
    try:
        resp = httpx.get(
            url, timeout=RSS_TIMEOUT_S, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        return parse_feed(resp.text, publisher)
    except Exception:  # noqa: BLE001 - one bad feed must not sink the others
        return []


def _fetch_rss(topic: str | None) -> list[dict[str, str]]:
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as pool:
        batches = list(pool.map(_fetch_one_feed, RSS_FEEDS))
    relevant = [
        item
        for batch in batches
        for item in batch
        if _KEYWORD_RE.search(f"{item['title']} {item['summary']}")
    ]
    return _rank(relevant, topic)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def get_economic_news(topic: str | None = None, limit: int = 6) -> dict[str, Any]:
    """Return recent UK cost-of-living headlines. Never raises."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 6
    limit = max(1, min(limit, MAX_ITEMS))
    topic = _clean_text(topic, TOPIC_MAX) or None if isinstance(topic, str) else None
    cache_key = (topic or "").lower()

    with _cache_lock:
        hit = _cache.get(cache_key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        cached = hit[1]
        return {**cached, "items": [dict(i) for i in cached["items"][:limit]]}

    result: dict[str, Any] | None = None
    n8n_url = (os.environ.get(N8N_ENV) or "").strip()
    n8n_failed = False
    if n8n_url:
        try:
            items = _fetch_n8n(n8n_url, topic, MAX_ITEMS)
            if items:
                result = {
                    "source": "n8n",
                    "items": items,
                    "note": "Third-party headlines gathered by FinTime's n8n news workflow. "
                    "They are external reporting, not FinTime calculations.",
                }
            else:
                n8n_failed = True
        except Exception:  # noqa: BLE001
            n8n_failed = True

    if result is None:
        try:
            items = _fetch_rss(topic)
        except Exception:  # noqa: BLE001
            items = []
        if items:
            why = "the n8n workflow was unavailable" if n8n_failed else "n8n is not configured"
            result = {
                "source": "rss",
                "items": items,
                "note": f"Third-party headlines read directly from public RSS feeds ({why}). "
                "They are external reporting, not FinTime calculations.",
            }

    if result is None:
        return {
            "source": "unavailable",
            "fetched_at": _now_iso(),
            "items": [],
            "note": "No news source could be reached right now, so there are no current headlines. "
            "Do not cite specific news events.",
        }

    result["fetched_at"] = _now_iso()
    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), result)
    return {**result, "items": [dict(i) for i in result["items"][:limit]]}
