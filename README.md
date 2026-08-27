# E100 Visibility Tracker

GEO/AI-visibility tracker for the E100 brand (e100.eu, business fuel cards)
across LLM assistants. Regularly asks a pool of market-typical questions to
each configured LLM provider, detects where (if at all) E100 appears in the
answer relative to competitors, stores the result, and prints a human-
readable report with run-over-run trend.

## Pipeline

1. Read the query pool, brand/competitor dictionary, provider list and
   market (language/country) from `config.toml` -- nothing is hardcoded.
2. Call every enabled provider's official API for every query (adapter
   pattern -- see `src/e100_visibility/providers/`). One failing provider or
   query is recorded as an error and never aborts the run.
3. Analyze each answer: either a deterministic local extractor (default,
   `analysis.method = "heuristic"`) or a call to an LLM analyzer with a
   structured-JSON prompt (`analysis.method = "llm"`, falls back to the
   heuristic if the analyzer call/parse fails).
4. Store every observation (raw answer, raw API payload, extracted fields,
   timestamp, provider, market) in a local SQLite file for history/trend.
5. Aggregate: share of voice, average position, top competitors, fully
   absent queries, trend vs. the previous run for the same market, and a
   few rule-based recommendations.
6. Render one text report: a block per query x provider, then a summary.

Zero third-party runtime dependencies -- `urllib`/`tomllib`/`sqlite3` from
the standard library, same philosophy as the sibling `dropdomain-scout`
tool.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
cp .env.example .env   # fill in the keys for the providers you enabled
```

## Try it without any API key

`config.demo.toml` uses an offline adapter (`kind = "offline"`,
`src/e100_visibility/providers/offline_provider.py`) that returns
deterministic canned Polish answers instead of calling a real API --
zero cost, zero network, zero keys. Useful for trying the CLI/report
interface while real provider keys are still being arranged:

```bash
e100-visibility run --config config.demo.toml
e100-visibility run --config config.demo.toml   # run again to see the trend section
```

Same query pool/brand/competitors as the real config, two synthetic
"providers" so the report shows a genuine multi-provider comparison. Since
it's deterministic, a second run reports "без изменений" (no change) in the
trend section, not new random numbers -- that's the tool correctly
detecting an unchanged input, not a bug.

## Run

```bash
e100-visibility run --config config.toml --env-file .env
```

Repeatable/scheduled execution is left to the OS (cron, launchd, a CI
schedule, etc.) -- this is a deterministic, idempotent-per-invocation CLI
script by design; it does not manage its own scheduling.

```bash
# cron example: every day at 07:00
0 7 * * * cd /path/to/e100-visibility-tracker && .venv/bin/e100-visibility run --config config.toml --env-file .env >> run.log 2>&1
```

Useful flags:

- `--providers openai gemini` -- restrict this run to a subset of the
  providers defined in the config (e.g. to retry just the one that errored).
- `--out DIR` -- override `[report].output_dir` for this run.
- `e100-visibility report --config config.toml --run-id N` -- re-render the
  report for an already-stored run (e.g. to recompute trend after a later
  run was added) without calling any provider again.

Each run prints the report to stdout and also writes
`<output_dir>/report_run<id>.txt`; full history (raw answers + extracted
fields) lives in `[storage].path` (a SQLite file).

### Exporting history for the web dashboard

```bash
e100-visibility export-web --config config.toml --out web/data
```

Reads every stored run (not just the latest) and writes `web/data/runs.json`
for the static dashboard in `web/` (see below) to `fetch()`. Deliberately
excludes the raw LLM answer text and the raw API response of every
observation -- only the same derived fields already shown in the text
report (query, provider, mentioned, position, context, sentiment, ...) go
into this file, because it is meant to be committed to a public repo.

### config.toml vs. config.ci.toml

Two committed config templates, for two different histories:

- `config.example.toml` -- copy to `config.toml` (gitignored) for your own
  local/manual runs. Default `[storage].path`/`[report].output_dir` point
  inside `output/` (also gitignored), so ad-hoc local testing never touches
  the committed history.
- `config.ci.toml` -- used by the weekly GitHub Actions workflow (see
  below). No secrets (same as `config.example.toml` -- provider keys still
  come from the environment). `[storage].path = "data/history.sqlite3"` and
  `[report].output_dir = "web/data"` point *inside* the repo on purpose:
  Actions runners are ephemeral, so the run history has to be committed
  back after every scheduled run, not left on the runner's disk. Both paths
  are deliberately excluded from `.gitignore`'s `output/`/`*.sqlite3`-style
  rules -- see the comment in `.gitignore` if you add another data path.

## Configuration

See `config.example.toml` for the full, commented default: Polish
"karty paliwowe dla firm" query pool, E100 brand aliases, a competitor
dictionary (DKV, Shell, BP, Orlen, Eurowag, ...), and the three built-in
providers (OpenAI, Gemini, Perplexity). To add a market: add a config file
with a different `[market]`/`queries`/`competitors` and point `--config` at
it -- language/market is a config parameter, not a code branch.

**Note on TOML**: keep `queries = [...]` above the first `[[providers]]` or
`[[competitors]]` table header -- in TOML, a bare array after a table header
belongs to that table, not to the document root.

### Managing the query pool

Two ways to define `queries`, chosen per config file:

- **Inline array** (`config.example.toml`) -- `queries = ["...", "..."]`
  directly in the TOML. Simplest for a one-off local config.
- **`queries_file`** (`config.ci.toml` -> `queries/poland.txt`) -- a path
  (relative to that config file) to a plain text file, one query per line;
  blank lines and lines starting with `#` are ignored as comments. Lets the
  pool be edited on its own -- including via GitHub's in-browser file
  editor, which is exactly what the dashboard's **"+ Добавить вопрос"**
  button links to (`.../edit/main/queries/poland.txt`) -- without touching
  any TOML. If a config sets both, `queries_file` wins; the inline array is
  only a fallback for configs that don't use a file. Either way, an empty
  result (empty file, or neither key set) raises a `ConfigError` -- there's
  always at least one query.

Edits to `queries/poland.txt` take effect on the *next* run -- either the
next scheduled Monday, or triggered immediately from the repo's **Actions**
tab (`weekly-run.yml` -> **Run workflow**).

**One-off test query, without editing the file:** `e100-visibility run
--config config.ci.toml --extra-query "some question"` appends that single
query for this run only -- it's never written to `queries_file`/`queries`.
The same thing is exposed as the workflow's manual-trigger input: **Actions**
-> **Weekly E100 visibility run** -> **Run workflow** -> `extra_query` field.

### Web search

The OpenAI and Gemini adapters always request web search, so their answers
are grounded in live results and carry citations (`has_source_link` in the
report is otherwise almost always "нет", since a plain chat-completion
answers from training data with nothing to cite):

- **OpenAI**: sends `"web_search_options": {}` on every Chat Completions
  call. This *requires* `model` to be a Chat-Completions search model --
  currently `gpt-5-search-api` (as set in `config.example.toml`). A plain
  chat model such as `gpt-4o` rejects this field with a 400 error; Chat
  Completions has no way to add web search to a non-search model (that
  needs OpenAI's separate Responses API, which this adapter doesn't use).
  The previous search models, `gpt-4o-search-preview` /
  `gpt-4o-mini-search-preview`, were shut down by OpenAI on 2026-07-23.
- **Gemini**: sends `"tools": [{"google_search": {}}]` on every
  `generateContent` call. Unlike OpenAI, this is a normal tool on an
  ordinary model (`gemini-2.5-flash` works as-is) -- no dedicated search
  model needed.
- Known gap: Gemini's `groundingChunks[].web.uri` is often a
  `vertexaisearch.cloud.google.com` redirect rather than the literal
  `e100.eu` URL, so the heuristic analyzer's domain-substring check for
  `has_source_link` can under-count Gemini citations even when e100.eu was
  in fact cited. Resolving the redirect (an extra HTTP call per citation)
  was left out of scope here.
- If `[analysis].method = "llm"` and `[analysis].provider = "openai"`, the
  analyzer call itself also goes through the search-enabled model above,
  so it will search the web and append its own citations/annotations
  around the JSON reply it's asked to return. **This combination has not
  been exercised against a live API key** -- the unit tests mock the HTTP
  layer, so they can't tell you whether `gpt-5-search-api` reliably wraps
  its JSON in enough extra text/citation markup to break
  `analyze_with_llm`'s `\{.*\}` extraction (the model's own answer
  already tests fine with an untouched `gpt-4o`-style reply; only the
  search-specific behavior is unverified). Before relying on this
  specific combination in production, run one real call with
  `OPENAI_API_KEY` set against a couple of queries and check that
  `analyze_with_llm` still parses a clean result. Until then, prefer
  `[analysis].method = "heuristic"` (the config default) or point
  `[analysis].provider` at a non-search model if you add one.

### Adding a new LLM provider

1. Write a class implementing `ask(self, query, *, language, country) ->
   ProviderResponse` in `src/e100_visibility/providers/` (see
   `openai_provider.py` for the shortest example).
2. Register it in `providers/registry.py`.
3. Reference it from `config.toml` via `kind = "<your-name>"`.

Nothing in the orchestrator, analysis step, or CLI needs to change.

### Analysis method

- `heuristic` (default): local, free, deterministic, fully unit-tested.
  Only recognises competitors listed under `[[competitors]]` -- an
  unlisted competitor is invisible to it.
- `llm`: sends the analyzer prompt to the provider named in
  `[analysis].provider`, parses its structured JSON reply. Recognises any
  competitor by name (open vocabulary) at the cost of one extra call per
  query x provider; degrades to the heuristic on failure (logged in the
  report as an error, the observation is not lost).

## Web dashboard (web/)

Static HTML/CSS/vanilla JS, no build step, no framework, no CDN scripts --
`web/index.html` just `fetch()`s `web/data/runs.json` (written by
`export-web`, see above) at a relative path. Deployable as-is to any static
host (Cloudflare Pages, GitHub Pages, S3, ...).

- Two date inputs filter which runs feed the trend charts and populate the
  run picker (default: the latest run in range).
- Two line charts (hand-drawn inline SVG, no charting library): Share of
  Voice % and average position over time, one line per provider plus a
  bold "overall" line. The position chart's y-axis is inverted (1 at the
  top) since a lower position is better.
- The selected run's full per-query x provider table, top competitors,
  absent queries, recommendations and provider errors -- the same content
  as the text report, in a browsable table.
- Colors are CSS custom properties re-defined under
  `prefers-color-scheme: dark`, so it follows the OS/browser theme with no
  toggle needed.

To preview locally:

```bash
cd web
python3 -m http.server 8000
# open http://localhost:8000
```

(`fetch()` needs an actual HTTP server -- opening `index.html` directly as
a `file://` URL will fail on the JSON fetch in most browsers.)

`web/data/runs.json` starts as `[]` in this repo (the dashboard shows an
empty-state message, not fake data, until the first real run is exported)
and is meant to be committed after every `export-web` -- see the weekly
GitHub Actions workflow below.

### Breakdown charts (by provider / by query / by competitor)

Three more hand-drawn SVG charts for the selected run, below the top
competitors table: E100's share of voice by provider (bar), by individual
query (bar, sorted descending), and E100 vs. top competitors as a share of
all brand mentions in the run (donut).

- `isDemo = run.aggregate.overall.successful_queries === 0` (true right
  now, since no provider is wired up with a key yet) switches all three to
  a fixed, hardcoded, clearly-labeled demo dataset -- never random, never
  silently mixed with real numbers. Each demo chart carries a `--warning`
  colored "ДЕМО" banner. The instant any run has at least one successful
  observation, real numbers take over automatically and permanently for
  that run -- there's no partial-demo/partial-real state.
- Real-data formulas: **by provider** = each provider's own
  `share_of_voice_pct` (providers with zero successful queries this run
  are omitted, not shown at 0%); **by query** = share of successfully-
  answering providers that mentioned E100, per query; **by competitor** =
  each of `agg.top_competitors` plus E100's own `mentioned_count`,
  normalized to % of all brand mentions in the run.
- Provider bars reuse the fixed `--provider-*` colors from the trend
  charts. Competitors intentionally do **not** get per-competitor color
  identity (this is a one-off snapshot, not something tracked run over
  run like providers are): E100 is `--accent`, every competitor is the
  same muted `--text-secondary`, disambiguated by their on-chart label
  instead of color.

### Errors, compactly

The dashboard groups `Ошибки провайдеров` by provider instead of one line
per failed query:

- If every failure for a provider is "environment variable ... is not
  set" (the provider just isn't wired up with a key yet), it collapses to
  one neutral line: **provider name + "API не подключён"** -- an expected
  state, not an alarm.
- Otherwise: **provider name + a red "N ошибок из M запросов" badge** and
  the first error message as a preview.
- Either way, click the line (a native `<details>`/`<summary>`, no extra
  JS) to expand the full original per-query error log underneath.

The same logic collapses each failed row in the big observations table to
a single badge ("API не подключён" / "ошибка") instead of repeating the
raw message 18 times -- hover the badge (`title` attribute) for the full
text. Only the *rendering* changed; `runs.json`/`export-web` still carry
every individual error message, nothing is dropped.

### Запуск прогона из интерфейса

The **"Запустить прогон"** button calls a Cloudflare Pages Function
(`functions/api/trigger-run.js`) that dispatches `weekly-run.yml` via
GitHub's `workflow_dispatch` API -- no separate backend. **This file must
stay at the repo root** (`functions/api/...`), not inside `web/`: Cloudflare
Pages only looks for Functions in a `/functions` directory at the project
root, never inside the configured build output directory (`web/` here) --
see the comment at the top of that file.

One-time setup (without this, the button returns a clear error -- that is
expected until you do this, not a bug):

1. **Create a fine-grained GitHub PAT**, scoped as narrowly as possible:
   [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
   -> **Generate new token** -> **Repository access**: only `llm_tracker`
   -> **Permissions**: **Actions** -> **Read and write** *and* **Contents**
   -> **Read and write** (the latter is for the "Редактирование вопросов"
   feature below), everything else left at "No access". Copy the token
   value (shown once).
2. **Add it to Cloudflare Pages**: project `llm-tracker` -> **Settings** ->
   **Environment variables** -> add a variable named exactly
   `GITHUB_DISPATCH_TOKEN`, paste the token as its value, and mark it
   **Secret/Encrypt** (not plaintext). Apply to the Production environment
   (and Preview too, if you want the button to work on preview deploys).
3. Redeploy (or just wait for the next push) so the Function picks up the
   new environment variable.

The button disables itself and shows "Запускаем..." while the request is
in flight, stays disabled for ~60s after a successful dispatch (a simple
"don't double-click" guard, not real rate limiting -- fine for an internal
tool), and re-enables immediately with an inline error message (never
`alert()`, never the raw GitHub response or the token) on failure.

### Редактирование вопросов из интерфейса

The **"Вопросы для отслеживания"** collapsible card (loads lazily on
first expand) lets you edit `queries/poland.txt` directly from the
dashboard, through another Pages Function,
`functions/api/queries.js` -- same repo-root placement rule as
`trigger-run.js` (see above), same `GITHUB_DISPATCH_TOKEN`, no new
environment variable.

- `GET /api/queries` reads the file via GitHub's Contents API and returns
  `{content, sha}`. `PUT /api/queries` writes `{content, sha}` back
  (base64-encoded internally) with that same `sha`, so GitHub can detect
  if someone/something else (e.g. a teammate, or `export-web`'s own
  history commits touching unrelated files) changed the file since you
  loaded it.
- **The file path is hardcoded in `queries.js` and never accepted from the
  client** -- this endpoint can only ever touch `queries/poland.txt`, by
  design, even though the token it uses now has broader Contents access.
  Editing a different file needs a new, separate function, not a path
  parameter added to this one.
- A stale `sha` (someone else saved in between) gets a GitHub `409`,
  surfaced verbatim as "Файл изменился, обновите страницу и попробуйте
  снова" -- no automatic merge is attempted. Any error, including this
  one, leaves your typed text in the textarea untouched so you don't lose
  edits.
- The old "+ Добавить вопрос" GitHub-editor link still works exactly as
  before; it's now the fallback ("или редактировать на GitHub напрямую")
  for when this Function is unavailable or you don't have the dashboard
  open.

**If you already created the PAT for "Запустить прогон" before this
feature existed**, it only has `Actions: Read and write` -- `PUT
/api/queries` will fail with a 403 until you add `Contents: Read and
write` to it too:

- Fine-grained tokens usually let you **edit permissions in place**
  (open the token on
  [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens),
  add the Contents permission, save) **without changing the token's
  value** -- if so, nothing else to do, the existing
  `GITHUB_DISPATCH_TOKEN` in Cloudflare Pages keeps working.
- If GitHub instead forces a **regenerate** to change permissions (this
  has varied across GitHub's UI versions), the token value *does*
  change -- copy the new value and update the `GITHUB_DISPATCH_TOKEN`
  environment variable in Cloudflare Pages to match, or every request
  (both this feature and "Запустить прогон") will start failing with
  401/403 using the old value.

## Manual browser-based spot-check (not part of the pipeline)

The brief requires official APIs as the only mechanism in the automated
pipeline. To eyeball how a chat UI (e.g. chatgpt.com) answers a query
outside of the API -- useful for sanity-checking a suspicious result --
open it manually in a browser and compare by hand. There is no scripted
browser automation in this repo, by design.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Covers: config validation, provider-error isolation (`fetch_all`), the
heuristic extractor on fixed example answers (brand absent, brand present
only as a bare domain, empty/truncated answer, alias false-positive
rejection, explicit numbered ranking vs. first-occurrence order, caveat/
negative sentiment, Cyrillic alias variant), the LLM analyzer's JSON
parsing and fallback, SQLite round-tripping, aggregation math (SoV, average
position, top competitors, trend direction), report rendering, and a full
CLI run against a fake in-process provider (including the second-run trend
section and the `report` subcommand).

## Secrets

API keys are read from environment variables named by
`[[providers]].api_key_env` in the config (see `.env.example`). Never
hardcoded, never logged: provider adapters only reference
`os.environ[...]`, and errors are truncated to the response body, never the
request headers.

## Scheduled runs (GitHub Actions)

`.github/workflows/weekly-run.yml` runs the pipeline automatically every
Monday at 06:00 UTC (a comment in the file points at the one line to edit
for a different schedule) and commits the updated history back to the
repo -- Actions runners are ephemeral, so this is how the history survives
between runs instead of a local disk.

Setup, one-time:

1. In the repo's GitHub settings: **Settings -> Secrets and variables ->
   Actions -> New repository secret**, add `OPENAI_API_KEY`,
   `GEMINI_API_KEY`, `PERPLEXITY_API_KEY`.
2. That's it -- the workflow reads `config.ci.toml` (committed, see above),
   which already names these exact variables.

Steps: checkout -> install -> `e100-visibility run --config config.ci.toml`
-> `e100-visibility export-web --config config.ci.toml --out web/data` ->
commit `data/history.sqlite3` + `web/data/runs.json` as `github-actions[bot]`
and push to `main`. If one provider fails that week, the job still succeeds
(the pipeline itself isolates provider errors -- see `fetch.py`); the
failure is visible in that step's log output and in the run's
"Ошибки провайдеров" section in both the report and the dashboard.

You can also trigger it by hand from the Actions tab (`workflow_dispatch`)
to test it without waiting for Monday.
