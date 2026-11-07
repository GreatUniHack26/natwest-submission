# FinTime news workflow (n8n)

`fintime-news.json` is an n8n workflow that gives the coach's `get_economic_news` tool recent UK
cost-of-living headlines. A POST webhook (`/webhook/fintime-news`) reads the BBC Business,
Guardian Money and Bank of England RSS feeds, merges them, keeps items about energy, fuel,
rates, inflation, wages, benefits, rent and tax, puts the requested `topic` first, sorts newest
first and returns at most `limit` (max 10).

Run n8n: `docker run -it --rm -p 5678:5678 n8nio/n8n`, then open http://localhost:5678.

Deploy it, either way:
- **Script:** create an API key in n8n (Settings > n8n API), set `N8N_BASE_URL=http://localhost:5678`
  and `N8N_API_KEY=...` in `.env`, then run `.venv/bin/python scripts/n8n_setup.py --write-env`.
  It creates or updates the "FinTime news" (and "FinTime GOV.UK") workflows, activates them and writes
  `N8N_NEWS_WEBHOOK_URL` (and `N8N_GOVUK_WEBHOOK_URL`) into `.env` (only those lines). Use
  `--workflow news|govuk|all` to pick one. Without `--write-env` it just prints the URLs.
- **Manual:** Workflows > Import from File > `fintime-news.json`, activate it, and set
  `N8N_NEWS_WEBHOOK_URL=http://localhost:5678/webhook/fintime-news` in `.env`.

Request: `{"topic": "energy" | null, "limit": 6, "region": "UK"}`. Response:
`{"items": [{"title", "summary", "url", "published", "publisher", "topic"}]}`.

If `N8N_NEWS_WEBHOOK_URL` is unset or n8n is down, the backend reads the same RSS feeds directly,
and returns `source: "unavailable"` (no items) if those fail too.

# FinTime GOV.UK workflow (n8n)

`fintime-govuk.json` grounds the coach's `lookup_gov_uk` tool in official GOV.UK guidance on tax,
allowances, benefits and government schemes. A POST webhook (`/webhook/fintime-govuk`):

1. **GOV.UK Search** calls `https://www.gov.uk/api/search.json` (free, no key).
2. **Pick Pages** puts curated `KEY_PAGES` matches first (same map as `backend/integrations/govuk.py`),
   then relevant guidance results; news, press releases and consultations only if nothing else matches.
3. **GOV.UK Content** fetches `https://www.gov.uk/api/content<path>` for each page.
4. **Extract Excerpts** strips HTML and keeps the most relevant paragraphs, lists and table rows
   (e.g. `Personal Allowance | Up to £12,570 | 0%`), at most 400 characters each.

Deploy with `.venv/bin/python scripts/n8n_setup.py --workflow govuk --write-env` (or `--workflow all`,
the default, for both workflows). It creates or updates "FinTime GOV.UK", activates it and writes
`N8N_GOVUK_WEBHOOK_URL` into `.env`. Restart the API so the new variable is loaded.

Request: `{"query": "personal allowance", "max_pages": 3}`. Response:
`{"source": "gov.uk", "pages": [{"title", "url", "summary", "updated", "excerpts"}]}`.

If `N8N_GOVUK_WEBHOOK_URL` is unset or n8n fails, the backend calls the GOV.UK APIs directly
(`source: "gov.uk"`); if those fail too it returns no pages and tells the coach not to quote figures.
Results are cached in-process for 6 hours.
