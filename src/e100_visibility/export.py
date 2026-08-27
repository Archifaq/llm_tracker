"""Exports the entire run history (every stored run, not just the latest)
to the JSON shape the static web dashboard fetches.
"""

from __future__ import annotations

from .config import AppConfig
from .report.aggregate import build_aggregate
from .report.serialize import run_to_dict
from .storage import RunStore


def export_all_runs(config: AppConfig) -> list[dict]:
    with RunStore(config.storage.path) as store:
        runs_meta = store.list_runs()
        exported = []
        for run in runs_meta:
            observations = store.observations_for_run(run["id"])
            previous_id = store.previous_run_id(
                language=run["language"], country=run["country"], before_run_id=run["id"]
            )
            previous_observations = store.observations_for_run(previous_id) if previous_id else None

            aggregate = build_aggregate(
                brand_name=config.brand.name,
                current_observations=observations,
                previous_observations=previous_observations,
            )

            if run["language"] == config.market.language and run["country"] == config.market.country:
                label = config.market.label or config.market.country
            else:
                label = f"{run['language']}/{run['country']}"

            exported.append(
                run_to_dict(
                    run_id=run["id"],
                    timestamp=run["started_at"],
                    language=run["language"],
                    country=run["country"],
                    label=label,
                    aggregate=aggregate,
                    observations=observations,
                )
            )
        return exported
