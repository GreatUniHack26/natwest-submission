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
  It creates or updates the "FinTime news" workflow, activates it and writes
  `N8N_NEWS_WEBHOOK_URL` into `.env` (only that line). Without `--write-env` it just prints the URL.
- **Manual:** Workflows > Import from File > `fintime-news.json`, activate it, and set
  `N8N_NEWS_WEBHOOK_URL=http://localhost:5678/webhook/fintime-news` in `.env`.

Request: `{"topic": "energy" | null, "limit": 6, "region": "UK"}`. Response:
`{"items": [{"title", "summary", "url", "published", "publisher", "topic"}]}`.

If `N8N_NEWS_WEBHOOK_URL` is unset or n8n is down, the backend reads the same RSS feeds directly,
and returns `source: "unavailable"` (no items) if those fail too.
