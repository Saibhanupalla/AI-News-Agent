# Build phases

This is the implementation map for the AI/tech daily briefing. Work **one phase at a time**. A phase is not done until its tests pass and the “Done when” checklist is true.

Do not skip ahead to the site or the LLM. Most of these products fail on junk sources and repeating yesterday, not on the model.

## Status (2026-08-24, end of day)

**Phases 0–9 are built and committed** (one commit per phase, 56 pipeline tests + 14 web tests, all green). The pipeline runs live end-to-end through the quality gate; the site builds and renders the golden edition with onboarding.

**Remaining user actions to go live** (see README "Going live"):

1. Create a GitHub repo and push
2. Add `GEMINI_API_KEY` secret (free key from Google AI Studio)
3. Connect Cloudflare Pages (root `web/`, build `npm run build`, output `dist`)
4. Dispatch the "Daily edition" workflow once and eyeball the result

**Known deviations from the letter of this plan:**

- Phase 8 browser test is pure-logic + build-output assertions, not Playwright (kept CI light; add Playwright later if UI regressions bite)
- Terse lab titles ("Introducing GPT-6") do not merge with press coverage of the same event — documented limitation with a regression test
- Live Gemini run not yet eyeballed (needs the API key)

## How to use this file

- Start a phase only when the previous phase is done.
- Write tests first (or with the code). No feature lands without tests for that phase.
- Each phase has a hard **out of scope** list. If it is listed, leave it for later.
- After a phase, run that phase’s commands before moving on.
- **v1 = phases 0–9** (through public URL + daily cron). **Phase 10 is v2**, only after v1 is live.

## Repo shape (from phase 0)

```
pipeline/                 Python ETL (uv)
web/                      Astro static site
data/feeds.json            Source list and weights
data/editions/            One JSON file per day
data/memory/              7-day story memory
tests/                    Pytest for the pipeline
.github/workflows/        CI + daily cron
```

---

## Phase 0 — Scaffold

**Goal:** Empty but runnable project. Anyone can clone, install, and run tests (even if tests only prove the harness works).

**In scope**

- `uv` Python 3.12 project (`pyproject.toml`, lockfile)
- Package layout under `pipeline/` with a CLI stub: `uv run python -m pipeline --help`
- Astro + Tailwind app under `web/` that renders a hardcoded “coming soon” page
- `data/feeds.json` (can be a short placeholder list)
- Empty `data/editions/` and `data/memory/` with `.gitkeep`
- `git init` + `.gitignore` (`.venv`, `node_modules`, `.env`, `__pycache__`)
- `.env.example` with `GEMINI_API_KEY=` (no real key)
- GitHub Action `.github/workflows/ci.yml` that installs uv and runs `pytest` (`workflow_dispatch` is enough until there is a remote)
- `README.md` with local run commands

**Out of scope**

- Real RSS fetching
- LLM calls
- Onboarding
- Cloudflare production deploy

**Tests**

- Pytest collects and one smoke test passes (`pipeline` imports)
- `ruff check` is wired (`uv run ruff check pipeline tests`)
- `web/` builds: `npm run build` in `web/`

**Done when**

- [ ] `uv sync` works
- [ ] `uv run pytest` is green
- [ ] `web/` dev server starts
- [ ] CI workflow runs pytest on demand
- [ ] No API keys required

---

## Phase 1 — Test harness and fixtures

**Goal:** Make later phases cheap to test. Fake feeds, frozen dates, and golden JSON so we never depend on the live internet in CI.

**In scope**

- `tests/fixtures/feeds/` — small RSS/Atom XML files (happy path, empty feed, malformed, missing dates)
- `tests/fixtures/editions/` — sample yesterday + today JSON
- Helpers: load fixture feed, freeze “today”, temp `data/` directory
- HTTP client seam so ingest can take a stub instead of the network
- LLM client seam (protocol / ABC) that tests can fake; no real Gemini yet

**Out of scope**

- Production ingest logic beyond what fixtures need
- Calling Google or Groq

**Tests**

- Fixture RSS files parse with `feedparser`
- Stub HTTP returns fixture bytes without network
- Fake LLM client records calls and returns a canned Pydantic object
- CI uses only fixtures (no network)

**Done when**

- [ ] CI is hermetic (no live RSS, no live LLM)
- [ ] Next phases can add tests without inventing a new harness

---

## Phase 2 — Ingest and normalize

**Goal:** Pull curated RSS, turn messy entries into one clean article shape. Dead feeds must not kill the day.

**In scope**

- Curate 15–25 feeds in `data/feeds.json` (name, url, source_weight, max_age_hours)
- Fetch with `httpx` (timeouts, per-feed error handling)
- Parse with `feedparser`
- Normalize to Pydantic `Article`: `id`, `title`, `url`, `canonical_url`, `source`, `published_at`, `snippet`
- Skip entries with no title or no url
- Write raw-normalized JSON for a date (debug artifact is fine)

**Out of scope**

- Clustering
- Freshness vs yesterday
- LLM
- Website

**Tests**

- Fixture feed → expected article fields
- Malformed / empty feed → skip, log, do not raise
- Timeout / HTTP 500 → skip that feed, continue others
- Canonical URL strips tracking params (`utm_`, `fbclid`)
- `published_at` parsed from several RSS date formats; missing date → drop or mark unknown (pick one, test it)
- Live optional test marked `@pytest.mark.network` (not run in CI)

**Done when**

- [ ] `uv run python -m pipeline ingest --date YYYY-MM-DD` writes normalized articles from fixtures
- [ ] One real local run against live RSS works on your machine (manual)
- [ ] All unit tests green without network

---

## Phase 3 — Same-day dedupe and cluster

**Goal:** One event, one cluster, many source links. “OpenAI launched X” from three outlets is one story.

**In scope**

- Cluster by canonical URL (exact)
- Cluster by `rapidfuzz` (`rapidfuzz` on PyPI) title similarity above a threshold
- Cluster record: `cluster_id`, `title`, `urls[]`, `sources[]`, `articles[]`
- Stable ids so the same inputs produce the same `cluster_id`

**Out of scope**

- Cross-day memory
- Quality scoring
- LLM

**Tests**

- Same URL twice → one cluster
- Same story, different URLs, similar titles → one cluster
- Unrelated titles → two clusters
- Tracking-param URLs still collapse to one
- Threshold does not merge “Gemini 3 launch” with “Gemini 3 pricing rumor” unless we decide they should (add a regression fixture when we see a miss)

**Done when**

- [ ] Fixture pack of ~15 articles collapses to a known cluster count
- [ ] Each cluster lists all source names and links

---

## Phase 4 — Freshness (do not repeat yesterday)

**Goal:** Day 2 is not a copy of day 1. Exact repeats die. Ongoing stories only ship as an **update** when something new happened.

**In scope**

- `data/memory/recent_stories.json` — last 7 days: urls, title tokens, `event_key`, first_seen, last_summary
- Drop if URL in memory
- Drop if title similarity vs memory is high and no new facts (heuristic in this phase; LLM delta in phase 6)
- Drop if `published_at` older than ~36h (labs blogs: 48h via feed config)
- Age-out memory entries older than 7 days
- After a successful publish (phase 6/7), append survivors to memory (wire the write here with a function; call it for real when editions exist)
- Label: `new` vs `possible_update`

**Out of scope**

- LLM “is there a new fact?” (stub: `possible_update` passes through; phase 6 decides)
- Website “Continuing” section (phase 7)

**Tests**

- Yesterday’s URL today → dropped, reason `duplicate_url`
- Same title, new URL → dropped or `possible_update` (assert the chosen rule)
- New story not in memory → kept
- Entry from 8 days ago is ignored (memory pruned)
- Two-day fixture: run day A, then day A’s items again as day B → day B has zero copies of A’s top stories
- Memory file round-trip (read, prune, write)

**Done when**

- [ ] Two-day fixture test is the gate: day 2 ≠ day 1
- [ ] Drop reasons are logged (`duplicate_url`, `duplicate_title`, `stale`)

---

## Phase 5 — Quality and relevance gate

**Goal:** Keep news someone who onboarded for AI/tech would want. Drop listicles, evergreen, off-topic, and weak single-source vendor posts.

**In scope**

- Rules (no LLM yet): recency already done; source_weight; multi-source bonus; keyword/type heuristics for listicles (`10 best`, “tools to try”, jobs, events)
- Topic taxonomy used by onboard (ids from Locked decisions):
  - `foundation-models` Foundation models
  - `research` Research
  - `startups-funding` Startups and funding
  - `policy` Policy and regulation
  - `open-source` Open source
  - `hardware` Hardware / chips
  - `tools` Tools and products
  - `big-tech` Big Tech
- Heuristic topic tags from keywords (LLM will replace/improve in phase 6)
- Feed health log: counts per source by drop reason
- Cutoff: target ~8–15 clusters after this gate

**Out of scope**

- LLM `reader_value` / `story_type` (phase 6)
- Changing the website
- Auto-deleting feeds (log only; human edits `feeds.json`)

**Tests**

- Listicle title → dropped `evergreen`
- Single-source vendor post below weight → dropped or ranked last (assert the rule)
- Two independent sources → kept
- Off-taxonomy (sports, celebrity) → `off_topic`
- High-weight lab blog + recent → kept
- Feed health counters increment

**Done when**

- [ ] Golden fixture set has known keep/drop labels
- [ ] Pipeline can run ingest → cluster → freshness → quality on fixtures with no LLM

---

## Phase 6 — LLM refine and edition object

**Goal:** Turn surviving clusters into a real newsletter JSON: tags, summaries, novelty, reader value, top stories, editor intro.

**In scope**

- Gemini client behind the phase 1 seam (`GEMINI_API_KEY` in `.env` / Actions secrets)
- Model: `gemini-3.1-flash-lite`, structured output matching Pydantic
- Batch 1: per cluster → topic tags, 1–2 sentence summary, `story_type` (`news` | `update` | `opinion` | `evergreen`), `novelty`, `reader_value`, `event_key`
- For `possible_update`: pass last_summary; if no new fact → drop; if new fact → `update` with a short delta
- Batch 2 (optional Flash): pick Must know (3), section order, 3-line intro
- Write `data/editions/YYYY-MM-DD.json`
- Append shipped clusters to story memory
- Ship only `news` / `update` above cutoff
- Same cluster must not be Must know two days in a row unless update is major

**Out of scope**

- Rendering HTML
- Per-user generation
- Scraping full article bodies

**Tests**

- Fake LLM returns canned scores → edition JSON validates
- `evergreen` / `opinion` below cutoff → not in edition
- `possible_update` + fake “no new fact” → dropped
- `possible_update` + fake “new fact” → in `continuing`, not Must know
- Missing API key → fail clearly in LLM mode; ingest-only mode still works
- Edition schema: date, intro, `must_know[]`, `sections{}`, `continuing[]`, each item has source links
- No live Gemini in CI (fake client only)
- Optional `@pytest.mark.llm` live call, not in CI

**Done when**

- [ ] Fixture pipeline produces a valid edition JSON committed as a golden file
- [ ] Live local run with a real key produces a sensible briefing (manual eyeball)
- [ ] Token use stays batched (few calls, not one per article)

---

## Phase 7 — Static site

**Goal:** People can read today’s briefing in a browser. Looks like a newsletter, not a dump of links.

**In scope**

- Astro pages:
  - `/` today’s edition (latest JSON)
  - `/archive` list of dates
  - `/edition/YYYY-MM-DD` past days
- Render intro, Must know, sections, Continuing (labeled Update)
- Every story: title, summary, source names, outbound links (new tab)
- Empty data state: friendly “no edition yet”
- Legal/footer: aggregator, we summarize and link, not original reporting
- Read JSON at **build time**

**Out of scope**

- Topic picker (phase 8)
- Auth
- Client-side fetching of live RSS

**Tests**

- Playwright or Astro build test against committed golden edition:
  - Home shows Must know titles from JSON
  - Source links present and `https`
  - Archive lists the fixture date
  - Missing edition → empty state, not a crash
- `npm run build` succeeds in CI

**Done when**

- [ ] `npm run dev` shows a real briefing from fixture/golden JSON
- [ ] Build is static (no server required to read)
- [ ] Mobile-width layout is readable (spot check)

---

## Phase 8 — Onboarding and personalization

**Goal:** First visit, pick topics. Homepage shows Must know + those topics + collapsed “Rest of today.” Feels personalized with no accounts.

**In scope**

- One onboard screen: 3–8 topics from the taxonomy
- Save ids in `localStorage`
- Filter sections by prefs; Must know always visible
- No prefs → full edition
- Change topics later (small settings control)
- Skip / continue CTA

**Out of scope**

- User accounts
- Server-side prefs
- Email

**Tests**

- Unit/component: given edition JSON + prefs `["research"]`, only `research` section + Must know + rest collapsed
- Empty prefs → all sections
- Unknown pref id → ignore, do not crash
- Playwright: complete onboard → reload → prefs persist and filter still applies

**Done when**

- [ ] New user can pick topics and see a filtered briefing
- [ ] Refresh keeps prefs
- [ ] Must know still shows if the user did not pick that topic

---

## Phase 9 — Daily automation and deploy

**Goal:** The product runs without you. Once a day, new JSON lands, site rebuilds, site is public.

**In scope**

- GitHub Action `.github/workflows/daily.yml`:
  - schedule (UTC 00:00 ≈ 05:30 IST — pick one and document it)
  - `workflow_dispatch`
  - `uv run python -m pipeline run --date today`
  - commit `data/editions/` + `data/memory/`
  - fail **soft** on individual feeds; fail **hard** if zero articles or invalid edition
- `GEMINI_API_KEY` in GitHub Actions secrets
- Cloudflare Pages: build `web/`, publish on push
- PR pytest stays in `ci.yml` (Phase 0)
- README: how to add a feed, how to rerun a day

**Out of scope**

- Custom domain (optional, later)
- Auto-PR review of edition quality

**Tests**

- Workflow YAML is valid
- Dry-run job with fixtures (or `PIPELINE_MODE=fixtures`) on `workflow_dispatch`
- If Gemini is missing in CI scheduled run, job fails with a clear message (do not push an empty edition)
- Manual: one scheduled or dispatched run on the real repo produces a new date file

**Done when**

- [ ] Public URL serves today’s briefing
- [ ] Next calendar day produces a new edition without a laptop
- [ ] Day 2 is not a copy of day 1 on the live site (spot check)
- [ ] v1 is live at ~$0/month

---

## Phase 10 — v2 (only after v1 is live)

Do not start this to “finish the architecture.” Only if real readers exist.

**Possible work (order if we do it)**

1. Feed-health pass: demote or remove feeds with high drop rates after ~7 live days
2. Click / hide signals (Plausible or tiny Worker) to retune `reader_value` cutoffs
3. Magic-link accounts + Cloudflare D1 for prefs (same edition JSON, still no per-user LLM)
4. Email via Resend free tier (daily link, not a unique generated letter)
5. More topics beyond AI/tech
6. Audio/TTS or video — only if you explicitly want it; this is where cost jumps

**v2 tests (when relevant)**

- Prefs round-trip in D1
- Logged-out site still works
- Email contains canonical links, not full article text
- Still one LLM edition per day regardless of user count

**Done when**

- [ ] You have a reason (real users), not just leftover ambition

---



---

## Commands (fill in as phases land)

```bash
# Pipeline
uv sync
uv run pytest
uv run ruff check pipeline tests
uv run python -m pipeline ingest --date 2026-08-24
uv run python -m pipeline run --date today

# Site
cd web && npm install && npm run dev
cd web && npm run build
```

Live Gemini is never required for `pytest` in CI.

---

## Locked decisions (do not re-argue during build)

These match the product plan. If something in a phase text drifts, **this table wins**.

**Product**

- One shared daily edition. Personalization is filter-only (v1: `localStorage`).
- Summarize + link. Never republish full articles.
- No accounts, email, TTS, or paid news APIs in v1.

**Paths**

| Thing | Path |
|---|---|
| Pipeline package | `pipeline/` |
| Site | `web/` |
| Tests | `tests/` |
| Feeds | `data/feeds.json` |
| Editions | `data/editions/YYYY-MM-DD.json` |
| Story memory | `data/memory/recent_stories.json` |
| CI | `.github/workflows/ci.yml` |
| Daily job | `.github/workflows/daily.yml` |
| Env example | `.env.example` |

**Stack**

| Thing | Choice |
|---|---|
| Python | 3.12 + uv |
| HTTP / RSS | `httpx` + `feedparser` |
| Schemas | Pydantic v2 |
| Title similarity | `rapidfuzz` |
| LLM | `google-genai`, model `gemini-3.1-flash-lite` |
| LLM secret | `GEMINI_API_KEY` |
| Site | Astro + Tailwind, one vanilla TS island for onboard |
| Host | Cloudflare Pages (Phase 9) |
| CI dates | Frozen in tests; no live network in CI |

**Topic ids (onboard + JSON tags)**

Use these slugs everywhere:

- `foundation-models`
- `research`
- `startups-funding`
- `policy`
- `open-source`
- `hardware`
- `tools`
- `big-tech`

Must know is not a topic the user picks. It is always shown.

**Feeds (Phase 2 — start here, add only if a feed stays useful)**

Trade: The Verge, TechCrunch, Ars Technica, MIT Technology Review, VentureBeat AI.

Labs: OpenAI, Anthropic, Google DeepMind, Meta AI, Hugging Face blog.

Community: Hacker News RSS.

Optional catch-all: Google News RSS `artificial intelligence when:1d`.

**CLI**

```bash
uv run python -m pipeline ingest --date YYYY-MM-DD
uv run python -m pipeline run --date today
```

**Edition JSON (Phase 6 must emit this shape)**

- `date`
- `intro`
- `must_know[]`
- `sections` keyed by topic id
- `continuing[]` (labeled updates)
- Each item: title, summary, `topic_ids[]`, source names, `https` links

---

## Gaps that are fine (not blockers)

- No code yet — that is Phase 0.
- No GitHub remote — create when you want CI on a remote; local pytest is enough until then.
- No Gemini key until Phase 6.
- No Cloudflare until Phase 9.
- Playwright lands in Phase 7, not in the scaffold.
- Exact RSS URLs are collected in Phase 2, not now.

Nothing else is missing to start Phase 0.
