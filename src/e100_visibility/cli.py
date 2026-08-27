"""Command-line entry point.

    e100-visibility run --config config.toml
    e100-visibility report --config config.toml --run-id 3
    e100-visibility export-web --config config.toml --out web/data

Meant to be invoked once per execution (by hand, or from cron/any external
scheduler) -- this tool itself has no built-in scheduling loop, per the
brief: "выполнение по расписанию настраивает пользователь снаружи."
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .analysis import analyze
from .config import AppConfig, ConfigError, load_config
from .export import export_all_runs
from .fetch import fetch_all
from .models import Observation
from .providers import build_provider
from .report import build_aggregate, render_report
from .storage import RunStore


def _load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE .env loader (no python-dotenv dependency).
    Existing environment variables always win, so real env still overrides.
    """
    import os

    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _select_providers(config: AppConfig, only: list[str] | None) -> AppConfig:
    if not only:
        return config
    wanted = set(only)
    providers = tuple(replace(p, enabled=p.enabled and p.name in wanted) for p in config.providers)
    return replace(config, providers=providers)


def _build_analyzer_provider(config: AppConfig):
    if config.analysis.method != "llm":
        return None
    for provider_cfg in config.providers:
        if provider_cfg.name == config.analysis.provider:
            return build_provider(
                provider_cfg.kind,
                name=provider_cfg.name,
                model=provider_cfg.model,
                api_key_env=provider_cfg.api_key_env,
                timeout_seconds=provider_cfg.timeout_seconds,
            )
    raise ConfigError(
        f"analysis.provider = '{config.analysis.provider}' does not match any configured [[providers]] name"
    )


def run_pipeline(config: AppConfig) -> tuple[int, list[Observation], list[Observation] | None]:
    """Fetch -> analyze -> store. Returns (run_id, current_observations, previous_observations)."""
    started_at = datetime.now(timezone.utc).isoformat()
    analyzer_provider = _build_analyzer_provider(config)

    fetch_results = fetch_all(config)

    with RunStore(config.storage.path) as store:
        run_id = store.start_run(
            started_at=started_at, language=config.market.language, country=config.market.country
        )
        previous_run_id = store.previous_run_id(
            language=config.market.language, country=config.market.country, before_run_id=run_id
        )
        previous_observations = store.observations_for_run(previous_run_id) if previous_run_id else None

        current_observations: list[Observation] = []
        for result in fetch_results:
            if result.ok:
                citations = tuple(result.response.citations)
                analysis = analyze(
                    config=config,
                    analyzer_provider=analyzer_provider,
                    query=result.query,
                    answer_text=result.response.answer_text,
                    citations=citations,
                    platform=result.provider,
                )
                observation = Observation(
                    run_id=run_id,
                    timestamp=started_at,
                    provider=result.provider,
                    model=result.model,
                    query=result.query,
                    language=config.market.language,
                    country=config.market.country,
                    answer_text=result.response.answer_text,
                    citations=citations,
                    raw=result.response.raw,
                    fetch_error=None,
                    analysis=analysis,
                )
            else:
                observation = Observation(
                    run_id=run_id,
                    timestamp=started_at,
                    provider=result.provider,
                    model=result.model,
                    query=result.query,
                    language=config.market.language,
                    country=config.market.country,
                    answer_text=None,
                    fetch_error=result.error,
                    analysis=None,
                )
            store.save_observation(observation)
            current_observations.append(observation)

    return run_id, current_observations, previous_observations


def cmd_run(args: argparse.Namespace) -> int:
    if args.env_file:
        _load_env_file(Path(args.env_file))

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    config = _select_providers(config, args.providers)
    if not config.enabled_providers():
        print("no enabled providers to query (check --providers / config.toml)", file=sys.stderr)
        return 1

    try:
        run_id, current, previous = run_pipeline(config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    aggregate = build_aggregate(
        brand_name=config.brand.name, current_observations=current, previous_observations=previous
    )
    report_text = render_report(
        brand=config.brand,
        market=config.market,
        generated_at=current[0].timestamp if current else datetime.now(timezone.utc).isoformat(),
        observations=current,
        aggregate=aggregate,
    )

    output_dir = Path(args.out or config.report.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"report_run{run_id}.txt"
    report_path.write_text(report_text, encoding="utf-8")

    print(report_text)
    print(f"\n(run #{run_id}; report saved to {report_path}; history in {config.storage.path})", file=sys.stderr)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    with RunStore(config.storage.path) as store:
        current = store.observations_for_run(args.run_id)
        if not current:
            print(f"no observations found for run #{args.run_id}", file=sys.stderr)
            return 1
        previous_run_id = store.previous_run_id(
            language=config.market.language, country=config.market.country, before_run_id=args.run_id
        )
        previous = store.observations_for_run(previous_run_id) if previous_run_id else None

    aggregate = build_aggregate(
        brand_name=config.brand.name, current_observations=current, previous_observations=previous
    )
    report_text = render_report(
        brand=config.brand,
        market=config.market,
        generated_at=current[0].timestamp,
        observations=current,
        aggregate=aggregate,
    )
    print(report_text)
    return 0


def cmd_export_web(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    runs = export_all_runs(config)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / "runs.json"
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"exported {len(runs)} run(s) to {runs_path}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="e100-visibility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="fetch answers from all providers, analyze, store, report")
    run_parser.add_argument("--config", default="config.toml", help="path to config TOML file")
    run_parser.add_argument("--env-file", default=None, help="path to a .env file with provider API keys")
    run_parser.add_argument("--out", default=None, help="override [report] output_dir from config")
    run_parser.add_argument(
        "--providers", nargs="*", default=None, help="restrict this run to these provider names (config-defined)"
    )
    run_parser.set_defaults(func=cmd_run)

    report_parser = subparsers.add_parser("report", help="re-render the report for an already-stored run")
    report_parser.add_argument("--config", default="config.toml", help="path to config TOML file")
    report_parser.add_argument("--run-id", type=int, required=True)
    report_parser.set_defaults(func=cmd_report)

    export_parser = subparsers.add_parser(
        "export-web", help="export the full run history to JSON for the web dashboard (never raw answers/payloads)"
    )
    export_parser.add_argument("--config", default="config.toml", help="path to config TOML file")
    export_parser.add_argument("--out", required=True, help="directory to write runs.json into")
    export_parser.set_defaults(func=cmd_export_web)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
