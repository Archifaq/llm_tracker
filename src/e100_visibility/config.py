"""Loads the TOML config file into typed, validated dataclasses.

Everything that varies between runs -- market/language, the query pool, the
list of providers, the competitor dictionary used by the heuristic analyzer --
lives in this file, not in code, per the brief's "configurable, not hardcoded"
requirement.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised for a malformed or incomplete config file."""


@dataclass(frozen=True)
class MarketConfig:
    language: str
    country: str
    label: str = ""


@dataclass(frozen=True)
class BrandConfig:
    name: str
    domain: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class CompetitorConfig:
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    kind: str
    model: str
    api_key_env: str
    enabled: bool = True
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class AnalysisConfig:
    method: str = "heuristic"  # "heuristic" or "llm"
    provider: str | None = None  # name of a configured ProviderConfig to reuse for the LLM analyzer


@dataclass(frozen=True)
class StorageConfig:
    path: str = "output/history.sqlite3"


@dataclass(frozen=True)
class ReportConfig:
    output_dir: str = "output"


@dataclass(frozen=True)
class AppConfig:
    market: MarketConfig
    brand: BrandConfig
    competitors: tuple[CompetitorConfig, ...]
    providers: tuple[ProviderConfig, ...]
    analysis: AnalysisConfig
    storage: StorageConfig
    report: ReportConfig
    queries: tuple[str, ...]

    def enabled_providers(self) -> tuple[ProviderConfig, ...]:
        return tuple(p for p in self.providers if p.enabled)


def _load_queries_file(path: Path) -> tuple[str, ...]:
    """One query per line; blank lines and lines starting with '#' are
    comments and are skipped. Lets the query pool be edited (e.g. via the
    GitHub web editor) without touching the TOML config at all.
    """
    queries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        queries.append(stripped)
    return tuple(queries)


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with path.open("rb") as f:
        raw = tomllib.load(f)

    try:
        market_raw = raw["market"]
        market = MarketConfig(
            language=market_raw["language"],
            country=market_raw["country"],
            label=market_raw.get("label", ""),
        )

        brand_raw = raw["brand"]
        brand = BrandConfig(
            name=brand_raw["name"],
            domain=brand_raw["domain"],
            aliases=tuple(brand_raw["aliases"]),
        )

        competitors = tuple(
            CompetitorConfig(name=c["name"], aliases=tuple(c["aliases"]))
            for c in raw.get("competitors", [])
        )

        providers = tuple(
            ProviderConfig(
                name=p["name"],
                kind=p.get("kind", p["name"]),
                model=p["model"],
                api_key_env=p["api_key_env"],
                enabled=p.get("enabled", True),
                timeout_seconds=float(p.get("timeout_seconds", 60.0)),
            )
            for p in raw.get("providers", [])
        )

        analysis_raw = raw.get("analysis", {})
        analysis = AnalysisConfig(
            method=analysis_raw.get("method", "heuristic"),
            provider=analysis_raw.get("provider"),
        )
        if analysis.method not in ("heuristic", "llm"):
            raise ConfigError(f"analysis.method must be 'heuristic' or 'llm', got {analysis.method!r}")
        if analysis.method == "llm" and not analysis.provider:
            raise ConfigError("analysis.provider is required when analysis.method = 'llm'")

        storage = StorageConfig(path=raw.get("storage", {}).get("path", "output/history.sqlite3"))
        report = ReportConfig(output_dir=raw.get("report", {}).get("output_dir", "output"))

        queries_file = raw.get("queries_file")
        if queries_file:
            # queries_file takes priority over an inline `queries` array when
            # both are present -- the inline array is only a fallback for
            # configs (like config.example.toml) that don't use a file.
            queries_path = path.parent / queries_file
            if not queries_path.exists():
                raise ConfigError(f"queries_file not found: {queries_path}")
            queries = _load_queries_file(queries_path)
        else:
            queries = tuple(raw.get("queries", []))

        if not queries:
            raise ConfigError(
                "config must define queries via a non-empty 'queries_file' or a non-empty "
                "top-level 'queries' array"
            )
        if not providers:
            raise ConfigError("config must define at least one [[providers]] entry")

    except KeyError as exc:
        raise ConfigError(f"missing required config key: {exc}") from exc

    return AppConfig(
        market=market,
        brand=brand,
        competitors=competitors,
        providers=providers,
        analysis=analysis,
        storage=storage,
        report=report,
        queries=queries,
    )
