# AI News Agent

A daily AI/tech news briefing that runs itself for ~$0/month.

Once a day, a pipeline pulls curated RSS feeds, collapses duplicate coverage into single
stories, drops anything stale or junk, has Gemini write one shared newsletter edition as
JSON, and a static Astro site renders it. Readers pick topics on first visit
(`localStorage`, no accounts) and see their slice of the day.

See [PHASES.md](PHASES.md) for the build plan and locked decisions.

## Layout

```
pipeline/        Python ETL (uv-managed)
web/             Astro static site
data/feeds.json  Curated RSS sources and weights
data/editions/   One published edition JSON per day
data/memory/     Rolling 7-day story memory (anti-repeat)
tests/           Pytest (hermetic: no live network, no live LLM)
```

## Local development

Pipeline (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run pytest
uv run ruff check pipeline tests
uv run python -m pipeline ingest --date 2026-08-24
uv run python -m pipeline run --date today --no-llm
```

Site (needs Node 22+):

```bash
cd web
npm install
npm run dev      # http://localhost:4321
npm run build
```

## Secrets

Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (Google AI Studio). Only the LLM
stage needs it; ingest and tests run without any key. In GitHub Actions the key lives in
repository secrets, never in the repo.

## Going live (one-time setup)

1. **GitHub**: create a repo and push. `.github/workflows/ci.yml` runs lint/tests on
   every push; `.github/workflows/daily.yml` publishes an edition at 00:00 UTC
   (05:30 IST) daily.
2. **Gemini key**: get a free key at [aistudio.google.com](https://aistudio.google.com),
   add it as the `GEMINI_API_KEY` repository secret (Settings > Secrets and variables >
   Actions).
3. **Cloudflare Pages**: connect the repo at [pages.cloudflare.com](https://pages.cloudflare.com).
   Build settings: framework preset "Astro", root directory `web`, build command
   `npm run build`, output directory `dist`. Every push (including the daily bot commit)
   rebuilds the site.
4. Test it: Actions tab > "Daily edition" > Run workflow (tick "dry run" first if you
   want a no-LLM rehearsal).

## Operations

- **Add or remove a feed**: edit `data/feeds.json` (name, url, `source_weight` 0-1,
  `max_age_hours`). Higher weight = more trusted. Watch the "feed health" log lines in
  the daily run and demote feeds with many drops.
- **Rerun a day**: delete `data/editions/YYYY-MM-DD.json`, then
  `uv run python -m pipeline run --date YYYY-MM-DD` (or dispatch the workflow).
- **Dry run without a key**: `uv run python -m pipeline run --date today --no-llm`
  prints the clusters that survived the gates.
