"""Official GOV.UK guidance on tax, allowances, benefits and government schemes for the coach.

Primary source is FinTime's n8n workflow (``N8N_GOVUK_WEBHOOK_URL``) when configured; otherwise,
or when it fails, the free public GOV.UK Search and Content APIs are called directly (no key):

- Search:  https://www.gov.uk/api/search.json?q=...
- Content: https://www.gov.uk/api/content<path>  (HTML in ``details.body`` or ``details.parts``)

A small curated ``KEY_PAGES`` map sends obvious queries ("personal allowance", "help to save")
straight to the right page even when search ranking is odd. Everything returned is third-party
text shown to an LLM, so it is treated as untrusted data: HTML, control and invisible characters
are stripped and lengths are capped. This module never raises to its caller.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

N8N_ENV = "N8N_GOVUK_WEBHOOK_URL"
N8N_TIMEOUT_S = 12.0
SEARCH_TIMEOUT_S = 5.0
CONTENT_TIMEOUT_S = 5.0
CACHE_TTL_S = 6 * 60 * 60
SEARCH_URL = "https://www.gov.uk/api/search.json"
CONTENT_URL = "https://www.gov.uk/api/content"
SITE = "https://www.gov.uk"
USER_AGENT = "FinTime-hackathon/1.0 (financial coach; GOV.UK guidance lookup)"
QUERY_MAX = 200
MAX_PAGES = 5
EXCERPT_MAX = 400
EXCERPTS_FIRST_PAGE = 6
EXCERPTS_OTHER_PAGES = 4
TITLE_MAX = 160
SUMMARY_MAX = 300

NOTE_OK = (
    "Official GOV.UK guidance (Crown copyright, Open Government Licence). General information, "
    "not personalised advice: quote figures exactly as written, link the page, and point the user "
    "to the official checker/calculator or Citizens Advice for their own situation."
)
NOTE_EMPTY = (
    "GOV.UK could not be reached or had no matching guidance, so there are no official figures. "
    "Do not quote rates or thresholds from memory; point the user to gov.uk or Citizens Advice."
)

# Curated topics -> GOV.UK path, preferred guide part slugs, trigger phrases. A trigger matches
# when every one of its words starts a word in the query ("child" matches "children").
# Every path was checked to return 200 from the Content API.
KEY_PAGES: dict[str, dict[str, Any]] = {
    "income tax rates": {
        "path": "/income-tax-rates", "parts": ["current-rates-and-allowances"],
        "triggers": ["income tax", "tax band", "tax rate", "basic rate", "higher rate",
                     "personal allowance", "tax free allowance", "earn before tax", "pay tax"],
    },
    "marriage allowance": {
        "path": "/marriage-allowance", "parts": ["how-it-works"],
        "triggers": ["marriage allowance", "transfer allowance partner", "civil partner allowance"],
    },
    "help to save": {
        "path": "/get-help-savings-low-income", "parts": ["how-it-works", "what-youll-get", "eligibility"],
        "triggers": ["help to save", "savings bonus low income", "government savings bonus"],
    },
    "universal credit": {
        "path": "/universal-credit", "parts": ["what-universal-credit-is", "eligibility", "what-youll-get"],
        "triggers": ["universal credit"],
    },
    "budgeting advance": {
        "path": "/universal-credit", "parts": ["get-advance-or-financial-support"],
        "triggers": ["budgeting advance", "universal credit advance", "advance payment", "hardship payment"],
    },
    "budgeting loan": {
        "path": "/budgeting-help-benefits", "parts": ["how-it-works", "what-youll-get", "eligibility"],
        "triggers": ["budgeting loan", "interest free loan benefits"],
    },
    "council tax discounts": {
        "path": "/council-tax", "parts": ["discounts-for-full-time-students", "who-has-to-pay"],
        "triggers": ["council tax"],
    },
    "council tax reduction": {
        "path": "/apply-council-tax-reduction", "parts": [],
        "triggers": ["council tax reduction", "council tax support", "council tax low income"],
    },
    "healthy start": {
        "path": "/healthy-start", "parts": [],
        "triggers": ["healthy start", "food vouchers", "free vitamins", "milk vouchers", "food child",
                     "food kid", "food baby", "food pregnant"],
    },
    "free school meals": {
        "path": "/apply-free-school-meals", "parts": [],
        "triggers": ["school meals", "school dinners", "school lunch", "food child", "food kid"],
    },
    "tax relief for employees": {
        "path": "/tax-relief-for-employees",
        "parts": ["overview", "uniforms-work-clothing-and-tools", "vehicles-you-use-for-work", "working-at-home"],
        "triggers": ["tax relief", "uniform", "work clothes", "mileage", "working from home tax",
                     "job expenses", "work expenses", "professional fees"],
    },
    "cycle to work": {
        "path": "/government/publications/cycle-to-work-scheme-implementation-guidance", "parts": [],
        "triggers": ["cycle to work", "cycle scheme", "bike scheme", "bike to work"],
    },
    "child benefit": {
        "path": "/child-benefit", "parts": ["how-it-works", "what-youll-get", "eligibility"],
        "triggers": ["child benefit"],
    },
    "tax-free childcare": {
        "path": "/tax-free-childcare", "parts": ["what-tax-free-childcare-is", "check-if-youre-eligible"],
        "triggers": ["tax free childcare", "childcare cost", "help childcare"],
    },
    "minimum wage": {
        "path": "/national-minimum-wage-rates", "parts": [],
        "triggers": ["minimum wage", "living wage", "nmw", "nlw"],
    },
    "student finance": {
        "path": "/student-finance", "parts": ["new-fulltime-students", "overview"],
        "triggers": ["student finance", "student loan", "maintenance loan", "tuition fee"],
    },
}

# Search result formats that are citizen guidance (kept first) vs. formats to skip unless nothing
# else matches. Anything else is kept after the guidance formats.
GUIDANCE_FORMATS = {
    "guide", "answer", "detailed_guide", "transaction", "calculator", "simple_smart_answer",
    "local_transaction", "guidance", "place", "licence", "step_by_step_nav",
}
SKIP_FORMATS = {
    "news_story", "press_release", "consultation", "open_consultation", "closed_consultation",
    "consultation_outcome", "speech", "impact_assessment", "research", "official_statistics",
    "national_statistics", "statistics_announcement", "official_statistics_announcement",
    "statistical_data_set", "foi_release", "correspondence", "decision", "corporate_report",
    "transparency", "policy_paper", "armed_forces_covenant_business", "policy_group",
    "organisation", "person", "ministerial_role", "world_location_news", "world_news_story",
    "government_response", "written_statement", "oral_statement", "authored_article",
    "independent_report", "case_study", "notice", "promotional",
}
# details fields (besides body/parts) that carry page HTML on transaction-style pages.
EXTRA_HTML_FIELDS = (
    "introduction", "introductory_paragraph", "more_information", "need_to_know",
    "what_you_need_to_know", "other_ways_to_apply",
)
STOPWORDS = {
    "the", "and", "for", "can", "how", "much", "what", "when", "who", "does", "get", "you", "your",
    "are", "with", "from", "this", "that", "have", "has", "will", "should", "about", "into", "any",
    "pay", "need", "there", "their", "they", "them", "our", "out", "not", "but", "per", "uk", "gov",
    "help", "rate", "rates", "is", "my", "me", "do", "a", "an", "of", "to", "in", "on", "or", "if",
    "it", "be", "as", "at", "by", "i", "we", "am", "much", "many",
}

_TAG_TOKEN_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>|<!--.*?-->|([^<]+)", re.S)
_CTRL_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff]")
_WS_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_MONEY_RE = re.compile(r"£\s?\d|\d\s?%|\bper cent\b", re.I)
_OLD_RE = re.compile(r"\bprevious\b|\bpast (tax )?years?\b|\brates between\b|\bfrom april 20[01]\d\b", re.I)
_PATH_RE = re.compile(r"^/[A-Za-z0-9/_\-.]{0,300}$")

_BLOCK_TAGS = {"p", "li", "h2", "h3", "h4", "tr", "dt", "dd"}
_CELL_TAGS = {"td", "th"}
_SKIP_TAGS = {"script", "style", "svg", "noscript"}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def clean_text(value: Any, max_len: int) -> str:
    """Plain text from untrusted HTML/text: no tags, entities, control or invisible characters."""
    if value is None:
        return ""
    text = re.sub(r"<[^>]*>", " ", str(value))
    text = html.unescape(text)
    text = re.sub(r"<[^>]*>", " ", text)
    text = _CTRL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > max_len:
        cut = text[: max_len - 1].rsplit(" ", 1)[0] or text[: max_len - 1]
        text = cut.rstrip(" ,.;:|") + "…"
    return text


def normalise_query(query: str) -> str:
    text = clean_text(query, QUERY_MAX).lower().replace("-", " ")
    return " ".join(_WORD_RE.findall(text))


def query_terms(query: str) -> list[str]:
    """Significant query words, stemmed to a 5-char prefix for loose matching."""
    terms: list[str] = []
    for word in normalise_query(query).split():
        if word in STOPWORDS or len(word) < 3:
            continue
        stem = word[:5]
        if stem not in terms:
            terms.append(stem)
    return terms


def _has_term(text_lower: str, term: str) -> bool:
    return re.search(r"\b" + re.escape(term), text_lower) is not None


def _safe_path(link: Any) -> str:
    if not isinstance(link, str):
        return ""
    link = link.strip()
    if link.startswith(SITE):
        link = link[len(SITE):]
    return link if _PATH_RE.match(link) and "//" not in link and ".." not in link else ""


def _date(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Curated pages
# ---------------------------------------------------------------------------

def match_key_pages(query: str) -> list[dict[str, Any]]:
    """Curated pages whose triggers match the query, longest trigger first, unique by path."""
    words = normalise_query(query).split()
    hits: list[tuple[int, str, dict[str, Any]]] = []
    for topic, page in KEY_PAGES.items():
        best = 0
        for trigger in page["triggers"]:
            needed = trigger.split()
            if all(any(w.startswith(n) for w in words) for n in needed):
                best = max(best, len(trigger))
        if best:
            hits.append((best, topic, page))
    hits.sort(key=lambda h: -h[0])
    out: list[dict[str, Any]] = []
    for _, topic, page in hits:
        existing = next((o for o in out if o["path"] == page["path"]), None)
        if existing:
            existing["parts"] = existing["parts"] + [p for p in page["parts"] if p not in existing["parts"]]
            continue
        out.append({"path": page["path"], "parts": list(page["parts"]), "topic": topic})
    return out


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def filter_results(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Relevant results, citizen guidance first; news/consultations only if nothing else matches."""
    terms = query_terms(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    for raw in results:
        if not isinstance(raw, dict):
            continue
        path = _safe_path(raw.get("link"))
        if not path or path in seen:
            continue
        haystack = f"{raw.get('title', '')} {raw.get('description', '')}".lower()
        hits = sum(1 for t in terms if _has_term(haystack, t))
        if terms and not hits:
            continue
        seen.add(path)
        scored.append((hits, raw))
    # Keep results matching nearly as many query words as the best one (drops "Tax your vehicle"
    # for "council tax student exemption").
    top = max((h for h, _ in scored), default=0)
    floor = max(1, top - 1) if len(terms) >= 3 else 1
    guidance: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for hits, raw in scored:
        if hits < floor:
            continue
        path = _safe_path(raw.get("link"))
        fmt = str(raw.get("format") or raw.get("content_store_document_type") or "")
        item = {
            "path": path,
            "title": clean_text(raw.get("title"), TITLE_MAX),
            "summary": clean_text(raw.get("description"), SUMMARY_MAX),
            "updated": _date(raw.get("public_timestamp")),
            "format": fmt,
            "parts": [],
        }
        if fmt in GUIDANCE_FORMATS:
            guidance.append(item)
        elif fmt in SKIP_FORMATS:
            skipped.append(item)
        else:
            other.append(item)
    return guidance + other or skipped


def search(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    resp = client.get(
        SEARCH_URL,
        params={
            "q": query,
            "count": 10,
            "fields": "title,description,link,format,public_timestamp,content_store_document_type",
        },
        timeout=SEARCH_TIMEOUT_S,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return filter_results(results if isinstance(results, list) else [], query)


# ---------------------------------------------------------------------------
# Content parsing
# ---------------------------------------------------------------------------

def html_blocks(markup: str) -> list[dict[str, str]]:
    """Split GOV.UK HTML into readable blocks: paragraphs, list items, headings and table rows
    (cells joined with " | "). List items carry their lead-in sentence when it ends with ':'."""
    blocks: list[dict[str, str]] = []
    if not isinstance(markup, str) or not markup:
        return blocks
    heading = ""
    lead_in = ""
    block_tag: str | None = None
    block_depth = 0
    buf: list[str] = []
    cells: list[str] = []
    cell_buf: list[str] | None = None
    skip_depth = 0

    def flush() -> None:
        nonlocal heading, lead_in, buf, cells
        if block_tag == "tr":
            text = " | ".join(cells) if any(c != "–" for c in cells) else ""
            kind = "row"
        else:
            text = clean_text("".join(buf), 2000)
            kind = {"h2": "heading", "h3": "heading", "h4": "heading", "li": "item"}.get(block_tag or "", "para")
        buf, cells = [], []
        if not text:
            return
        if kind == "heading":
            heading, lead_in = text, ""
            blocks.append({"kind": kind, "text": text, "heading": text})
            return
        block = {"kind": kind, "text": text, "heading": heading}
        if kind == "item" and lead_in:
            block["lead_in"] = lead_in
        if kind == "para":
            lead_in = text if text.endswith(":") else ""
        blocks.append(block)

    for match in _TAG_TOKEN_RE.finditer(markup):
        closing, tag, text = match.group(1), (match.group(2) or "").lower(), match.group(3)
        if text is not None:
            if skip_depth:
                continue
            if cell_buf is not None:
                cell_buf.append(text)
            elif block_tag:
                buf.append(text)
            continue
        if not tag:
            continue
        if tag in _SKIP_TAGS:
            skip_depth += -1 if closing else 1
            skip_depth = max(skip_depth, 0)
            continue
        if tag == "br" and block_tag and cell_buf is None:
            buf.append(" ")
            continue
        if block_tag == "tr" and tag in _CELL_TAGS:
            if closing:
                if cell_buf is not None:
                    cells.append(clean_text("".join(cell_buf), 200) or "–")
                cell_buf = None
            else:
                cell_buf = []
            continue
        if tag in _BLOCK_TAGS:
            if not closing:
                if block_tag is None:
                    block_tag, block_depth = tag, 1
                elif tag == block_tag:
                    block_depth += 1
                else:
                    buf.append(" ")  # e.g. <p> inside <li>: same block
            elif block_tag == tag:
                block_depth -= 1
                if block_depth <= 0:
                    if cell_buf is not None:
                        cells.append(clean_text("".join(cell_buf), 200) or "–")
                        cell_buf = None
                    flush()
                    block_tag = None
            continue
        if block_tag and tag in ("ul", "ol", "table", "div") and not closing:
            buf.append(" ")
    if block_tag:
        flush()
    return blocks


def _body_html(value: Any) -> str:
    """details.body is usually HTML, sometimes [{content_type, content}, ...]."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for part in value:
            if isinstance(part, dict) and part.get("content_type") == "text/html":
                return str(part.get("content") or "")
    return ""


def page_sections(content: dict[str, Any]) -> list[dict[str, Any]]:
    """[{slug, title, blocks}] for a content item: guide parts, or one section for the body."""
    details = content.get("details") if isinstance(content.get("details"), dict) else {}
    sections: list[dict[str, Any]] = []
    parts = details.get("parts")
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            slug = part.get("slug") if isinstance(part.get("slug"), str) else ""
            sections.append({
                "slug": slug if re.fullmatch(r"[a-z0-9\-]{1,100}", slug or "") else "",
                "title": clean_text(part.get("title"), TITLE_MAX),
                "blocks": html_blocks(_body_html(part.get("body"))),
            })
    body_html = _body_html(details.get("body"))
    extra = [details.get(k) for k in EXTRA_HTML_FIELDS if isinstance(details.get(k), str)]
    if body_html or extra:
        sections.append({"slug": "", "title": "", "blocks": html_blocks("\n".join([body_html, *extra]))})
    return sections


def group_blocks(blocks: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge a list into its lead-in sentence ("You can: a; b; c") and consecutive table rows
    into one readable unit ("Heading: Band | Income | Rate; Personal Allowance | Up to £12,570 | 0%")."""
    units: list[dict[str, str]] = []
    for block in blocks:
        prev = units[-1] if units else None
        kind = block["kind"]
        if kind == "item" and block.get("lead_in"):
            if prev and prev.get("group") == "list" and prev.get("lead_in") == block["lead_in"]:
                prev["text"] += f"; {block['text']}"
                continue
            if prev and prev["kind"] == "para" and prev["text"] == block["lead_in"]:
                units.pop()
            units.append({"kind": "item", "group": "list", "lead_in": block["lead_in"],
                          "heading": block.get("heading", ""), "text": f"{block['lead_in']} {block['text']}"})
            continue
        if kind == "row":
            if prev and prev.get("group") == "table" and prev.get("heading") == block.get("heading", ""):
                prev["text"] += f"; {block['text']}"
                continue
            prefix = f"{block['heading']}: " if block.get("heading") else ""
            units.append({"kind": "row", "group": "table", "heading": block.get("heading", ""),
                          "text": prefix + block["text"]})
            continue
        units.append(dict(block))
    return units


def _excerpt_text(block: dict[str, str]) -> str:
    return clean_text(block["text"], EXCERPT_MAX)


def select_excerpts(
    sections: list[dict[str, Any]], query: str, preferred_parts: list[str] | None = None, limit: int = 5
) -> tuple[list[str], str]:
    """Pick the most relevant blocks (query terms, £ amounts, percentages) in document order.
    Returns (excerpts, slug of the guide part holding the best excerpt or '')."""
    terms = query_terms(query)
    preferred = preferred_parts or []
    scored: list[tuple[float, int, str, str]] = []  # (score, order, text, slug)
    order = 0
    for section in sections:
        slug = section.get("slug", "")
        title_l = section.get("title", "").lower()
        part_bonus = 0.0
        if slug and slug in preferred:
            part_bonus += 3 - min(preferred.index(slug), 2) * 0.5
        part_bonus += sum(1.0 for t in terms if _has_term(title_l, t))
        for block in group_blocks(section["blocks"]):
            order += 1
            if block["kind"] == "heading":
                continue
            text = _excerpt_text(block)
            if len(text) < 25 and block["kind"] != "row":
                continue
            lower = text.lower()
            hits = sum(1 for t in terms if _has_term(lower, t))
            heading_hits = sum(1 for t in terms if _has_term(block.get("heading", "").lower(), t))
            score = 3.0 * hits + 1.0 * heading_hits + part_bonus
            if _MONEY_RE.search(text):
                score += 2.0 + (4.0 if block.get("group") == "table" else 0.0)
            if re.search(r"\bcurrent\b|\bthis tax year\b", f"{block.get('heading', '')} {lower[:80]}", re.I):
                score += 2.0
            elif re.search(r"\d", text):
                score += 0.5
            if "welsh (cymraeg)" in lower or "@" in text:
                score -= 5
            if _OLD_RE.search(f"{title_l} {block.get('heading', '')} {lower[:80]}"):
                score -= 8  # previous years' rates are rarely what the user wants
            scored.append((score, order, text, slug))
    if not scored:
        return [], ""
    seen: set[str] = set()
    best = sorted(scored, key=lambda s: (-s[0], s[1]))
    picked: list[tuple[float, int, str, str]] = []
    for item in best:
        if item[2] in seen:
            continue
        if item[0] <= 0 and picked:
            break
        seen.add(item[2])
        picked.append(item)
        if len(picked) >= limit:
            break
    top_slug = picked[0][3] if picked else ""
    picked.sort(key=lambda s: s[1])
    return [p[2] for p in picked], top_slug


def build_page(content: dict[str, Any], query: str, hint: dict[str, Any], limit: int) -> dict[str, Any] | None:
    path = _safe_path(content.get("base_path")) or hint["path"]
    if content.get("document_type") in ("redirect", "gone") or not path:
        return None
    sections = page_sections(content)
    excerpts, slug = select_excerpts(sections, query, hint.get("parts"), limit)
    title = clean_text(content.get("title"), TITLE_MAX) or hint.get("title", "")
    if not title or not excerpts:
        return None
    first_slug = next((s["slug"] for s in sections if s.get("slug")), "")
    url = f"{SITE}{path}" + (f"/{slug}" if slug and slug != first_slug else "")
    return {
        "title": title,
        "url": url,
        "summary": clean_text(content.get("description"), SUMMARY_MAX) or hint.get("summary", ""),
        "updated": _date(content.get("public_updated_at")) or hint.get("updated", ""),
        "excerpts": excerpts,
    }


def fetch_content(client: httpx.Client, path: str) -> dict[str, Any] | None:
    try:
        resp = client.get(f"{CONTENT_URL}{path}", timeout=CONTENT_TIMEOUT_S)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - one bad page must not sink the others
        return None


def _direct_lookup(query: str, max_pages: int) -> list[dict[str, Any]]:
    candidates = match_key_pages(query)
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                      follow_redirects=False) as client:
        try:
            found = search(client, query)
        except Exception:  # noqa: BLE001
            found = []
        for item in found:
            existing = next((c for c in candidates if c["path"] == item["path"]), None)
            if existing:
                existing.setdefault("title", item["title"])
                existing.setdefault("summary", item["summary"])
                existing.setdefault("updated", item["updated"])
            else:
                candidates.append(item)
        # Fetch a couple of spares so a missing page does not shrink the answer.
        wanted = candidates[: max_pages + 2]
        if not wanted:
            return []
        with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
            contents = list(pool.map(lambda c: fetch_content(client, c["path"]), wanted))
    pages: list[dict[str, Any]] = []
    for hint, content in zip(wanted, contents):
        if not content:
            continue
        limit = EXCERPTS_FIRST_PAGE if not pages else EXCERPTS_OTHER_PAGES
        page = build_page(content, query, hint, limit)
        if page and all(p["url"] != page["url"] for p in pages):
            pages.append(page)
        if len(pages) >= max_pages:
            break
    return pages


# ---------------------------------------------------------------------------
# n8n
# ---------------------------------------------------------------------------

def sanitise_page(raw: Any) -> dict[str, Any] | None:
    """Re-clean a page from n8n (untrusted): GOV.UK URLs only, capped text."""
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("json"), dict):
        raw = raw["json"]
    url = raw.get("url") if isinstance(raw.get("url"), str) else ""
    path = _safe_path(url) if url.startswith(SITE + "/") else ""
    title = clean_text(raw.get("title"), TITLE_MAX)
    excerpts_raw = raw.get("excerpts") if isinstance(raw.get("excerpts"), list) else []
    excerpts = [e for e in (clean_text(x, EXCERPT_MAX) for x in excerpts_raw[:EXCERPTS_FIRST_PAGE]) if e]
    if not path or not title or not excerpts:
        return None
    return {
        "title": title,
        "url": f"{SITE}{path}",
        "summary": clean_text(raw.get("summary"), SUMMARY_MAX),
        "updated": _date(raw.get("updated")) or clean_text(raw.get("updated"), 10),
        "excerpts": excerpts,
    }


def _fetch_n8n(url: str, query: str, max_pages: int) -> list[dict[str, Any]]:
    resp = httpx.post(
        url,
        json={"query": query, "max_pages": max_pages},
        timeout=N8N_TIMEOUT_S,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0].get("json", data[0])
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        raise ValueError("n8n response has no pages list")
    out = [p for p in (sanitise_page(r) for r in pages) if p]
    return out[:max_pages]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def lookup_gov_uk(query: str, max_pages: int = 3) -> dict[str, Any]:
    """Official GOV.UK guidance excerpts for a tax/benefits/schemes question. Never raises."""
    try:
        max_pages = max(1, min(int(max_pages), MAX_PAGES))
    except (TypeError, ValueError):
        max_pages = 3
    clean_query = clean_text(query, QUERY_MAX) if isinstance(query, str) else ""
    key = f"{normalise_query(clean_query)}|{max_pages}"
    if not clean_query or not key.split("|")[0]:
        return {"query": clean_query, "fetched_at": _now_iso(), "source": "gov.uk", "pages": [],
                "note": NOTE_EMPTY}

    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return {**hit[1], "pages": [dict(p, excerpts=list(p["excerpts"])) for p in hit[1]["pages"]]}

    pages: list[dict[str, Any]] = []
    source = "gov.uk"
    n8n_url = (os.environ.get(N8N_ENV) or "").strip()
    if n8n_url:
        try:
            pages = _fetch_n8n(n8n_url, clean_query, max_pages)
            source = "n8n"
        except Exception:  # noqa: BLE001
            pages = []
        if not pages:
            source = "gov.uk"
    if not pages:
        try:
            pages = _direct_lookup(clean_query, max_pages)
        except Exception:  # noqa: BLE001
            pages = []

    result = {
        "query": clean_query,
        "fetched_at": _now_iso(),
        "source": source,
        "pages": pages,
        "note": NOTE_OK if pages else NOTE_EMPTY,
    }
    if pages:
        with _cache_lock:
            _cache[key] = (time.monotonic(), result)
    return {**result, "pages": [dict(p, excerpts=list(p["excerpts"])) for p in pages]}
