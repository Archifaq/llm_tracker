"""Orchestrates calling every enabled provider for every query.

One failing provider or one failing query must not abort the run -- each
call is isolated and its outcome (success or error) is recorded so the rest
of the pipeline (analysis, storage, reporting) can carry on and the failure
still shows up in the final report.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

from .config import AppConfig, ProviderConfig
from .providers import ProviderError, ProviderResponse, build_provider


@dataclass(frozen=True)
class FetchResult:
    provider: str
    model: str
    query: str
    response: ProviderResponse | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


def fetch_all(config: AppConfig, *, log=lambda msg: print(msg, file=sys.stderr)) -> list[FetchResult]:
    results: list[FetchResult] = []
    for provider_cfg in config.enabled_providers():
        try:
            provider = build_provider(
                provider_cfg.kind,
                name=provider_cfg.name,
                model=provider_cfg.model,
                api_key_env=provider_cfg.api_key_env,
                timeout_seconds=provider_cfg.timeout_seconds,
            )
        except ValueError as exc:
            log(f"skipping provider '{provider_cfg.name}': {exc}")
            for query in config.queries:
                results.append(FetchResult(provider_cfg.name, provider_cfg.model, query, None, str(exc)))
            continue

        for query in config.queries:
            try:
                response = provider.ask(query, language=config.market.language, country=config.market.country)
            except ProviderError as exc:
                log(f"provider error: {exc}")
                results.append(FetchResult(provider_cfg.name, provider_cfg.model, query, None, exc.message))
            except Exception as exc:  # noqa: BLE001 -- adapters must not be able to kill the run
                log(f"unexpected error calling '{provider_cfg.name}': {exc}")
                results.append(FetchResult(provider_cfg.name, provider_cfg.model, query, None, str(exc)))
            else:
                results.append(FetchResult(provider_cfg.name, provider_cfg.model, query, response, None))
            time.sleep(4)
    return results
