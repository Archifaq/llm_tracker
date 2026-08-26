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
  analyzer call itself also goes through the search-enabled model above --
  slightly slower/pricier per analysis call, functionally harmless.

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
