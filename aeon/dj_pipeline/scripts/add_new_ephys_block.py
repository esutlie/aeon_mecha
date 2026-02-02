"""
Add one or more new EphysBlock(s) for an existing experiment/probe, then create
SortingTask entries and run PreProcessing.populate() for each new block.

Intended use: after a schema wipe + re-ingestion (e.g. via ephys_test_ingestion.py),
incrementally add additional blocks to spike sort (e.g. 3h blocks with 1h overlap).

Run from the repo root, inside the aeon_mecha environment.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import time

import pandas as pd

from aeon.dj_pipeline import ephys, spike_sorting

# -------------------------
# User variables (edit me)
# -------------------------

"""
Some notes on timing:
For a 3 hour block (1 hour overlap)
Preprocessing took 5 - 10 minutes
Sorting took 1.5 - 2 hours
Postprocessing took 30 minutes
SIExport took 3 minutes
SortedSpikes took 4 minutes
"""
# Same session defaults as aeon/dj_pipeline/scripts/ephys_test_ingestion.py
experiment_name = "social-ephys0.1-aeon3"
probe = "NP2004-001"

# ElectrodeGroup key (required to create SortingTask)
probe_type = "neuropixels - NP2004"
electrode_config_name = "0-383"
electrode_group = "0-95"

# SortingParamSet key (required to create SortingTask)
paramset_id = "400"

# Block generation
block_start = "2024-06-04 11:00:00"  # inclusive
block_duration_hours = 3.0
block_overlap_hours = 1.0  # step size = duration - overlap (default: 2h)

# Choose exactly one:
block_end_limit: Optional[str] = None  # e.g. "2024-06-05 11:00:00"
n_blocks: Optional[int] = 3

# Execution options
dry_run = False
reserve_jobs = True
display_progress = True


def _require_exactly_one(spec_a: Any, spec_b: Any, name_a: str, name_b: str) -> None:
    a_set = spec_a is not None
    b_set = spec_b is not None
    if a_set == b_set:
        raise ValueError(f"Specify exactly one of {name_a} or {name_b}")


def _to_ts(x: str) -> pd.Timestamp:
    ts = pd.Timestamp(x)
    if ts.tzinfo is not None:
        # Pipeline uses naive datetimes; keep it consistent.
        ts = ts.tz_convert(None)
    return ts


def _build_blocks(
    start: pd.Timestamp,
    duration_h: float,
    overlap_h: float,
    *,
    end_limit: Optional[pd.Timestamp],
    n_blocks: Optional[int],
) -> List[Dict[str, Any]]:
    if duration_h <= 0:
        raise ValueError("block_duration_hours must be > 0")
    if overlap_h < 0:
        raise ValueError("block_overlap_hours must be >= 0")
    if overlap_h >= duration_h:
        raise ValueError("block_overlap_hours must be < block_duration_hours")

    step_h = duration_h - overlap_h
    duration = pd.Timedelta(hours=duration_h)
    step = pd.Timedelta(hours=step_h)

    blocks: List[Dict[str, Any]] = []
    cur = start

    if n_blocks is not None:
        for _ in range(int(n_blocks)):
            blocks.append({"block_start": cur, "block_end": cur + duration})
            cur = cur + step
        return blocks

    if end_limit is None:
        raise ValueError("end_limit cannot be None when n_blocks is None")

    while cur + duration <= end_limit:
        blocks.append({"block_start": cur, "block_end": cur + duration})
        cur = cur + step

    return blocks


def main() -> None:
    _require_exactly_one(block_end_limit, n_blocks, "block_end_limit", "n_blocks")

    start_ts = _to_ts(block_start)
    end_limit_ts = _to_ts(block_end_limit) if block_end_limit is not None else None

    blocks = _build_blocks(
        start_ts,
        block_duration_hours,
        block_overlap_hours,
        end_limit=end_limit_ts,
        n_blocks=n_blocks,
    )
    if not blocks:
        raise ValueError("No blocks to create (check start/end/duration/overlap).")

    step_h = block_duration_hours - block_overlap_hours
    print(
        f"Will create {len(blocks)} block(s) with duration={block_duration_hours}h, "
        f"overlap={block_overlap_hours}h (step={step_h}h)"
    )
    for i, b in enumerate(blocks, start=1):
        print(f"  {i:02d}: {b['block_start']} -> {b['block_end']}")

    # Validate downstream lookup tables exist
    eg_key = {
        "probe_type": probe_type,
        "electrode_config_name": electrode_config_name,
        "electrode_group": electrode_group,
    }
    if not (spike_sorting.ElectrodeGroup & eg_key):  # type: ignore[operator]
        raise ValueError(
            f"ElectrodeGroup missing for key={eg_key}. "
            "Create it first (e.g. via ephys_test_ingestion.py)."
        )

    ps_key = {"paramset_id": str(paramset_id)}
    if not (spike_sorting.SortingParamSet & ps_key):  # type: ignore[operator]
        raise ValueError(
            f"SortingParamSet missing for paramset_id={paramset_id}. "
            "Create it first (e.g. via ephys_test_ingestion.py)."
        )

    preproc_durations: List[float] = []

    for idx, b in enumerate(blocks, start=1):
        block_key = {
            "experiment_name": experiment_name,
            "probe": probe,
            "block_start": b["block_start"],
            "block_end": b["block_end"],
        }

        sorting_task_key = {
            **block_key,
            "probe_type": probe_type,
            "electrode_config_name": electrode_config_name,
            "electrode_group": electrode_group,
            "paramset_id": str(paramset_id),
        }

        print("\n---")
        print(f"Block {idx}: {block_key['block_start']} -> {block_key['block_end']}")
        print(f"SortingTask: electrode_group={electrode_group}, paramset_id={paramset_id}")

        if dry_run:
            print("DRY RUN: would insert EphysBlock, populate EphysBlockInfo, insert SortingTask, populate PreProcessing")
            continue

        # Insert EphysBlock + populate EphysBlockInfo
        ephys.EphysBlock.insert1(block_key, skip_duplicates=True)
        ephys.EphysBlockInfo.populate(block_key)

        if not (ephys.EphysBlockInfo & block_key):  # type: ignore[operator]
            raise RuntimeError(f"EphysBlockInfo.populate() failed for block {block_key}")
        chunk_count = len(ephys.EphysBlockInfo.Chunk & block_key)  # type: ignore[operator]
        if chunk_count == 0:
            raise RuntimeError(f"EphysBlockInfo.populate() succeeded but found no chunks for block {block_key}")

        # Insert SortingTask + run preprocessing
        spike_sorting.SortingTask.insert1(sorting_task_key, skip_duplicates=True)

        start_wall = time.time()
        spike_sorting.PreProcessing.populate(
            sorting_task_key,
            reserve_jobs=reserve_jobs,
            display_progress=display_progress,
        )

        elapsed_h = (time.time() - start_wall) / 3600.0
        preproc_durations.append(elapsed_h)

        block_hours = (b["block_end"] - b["block_start"]).total_seconds() / 3600.0
        print(
            f"Block {idx} ({block_hours:.2f} hour recording): "
            f"PreProcessing duration = {elapsed_h:.2f} hours"
        )

    if not dry_run and preproc_durations:
        avg_h = sum(preproc_durations) / len(preproc_durations)
        print("\nPreProcessing durations per block (hours):")
        for i, d in enumerate(preproc_durations, start=1):
            print(f"  Block {i}: {d:.3f}")
        print(f"Average PreProcessing duration: {avg_h:.3f} hours")

        # Helper output: ready-to-paste key definitions for run_aeon_spike_sorting.py
        print("\nCopy-paste these key definitions into aeon/dj_pipeline/scripts/run_aeon_spike_sorting.py:")
        for i, b in enumerate(blocks, start=1):
            bs = b["block_start"].strftime("%Y-%m-%d %H:%M:%S")
            be = b["block_end"].strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n# Block {i}")
            print("key = {'experiment_name': '%s'," % experiment_name)
            print("       'probe': '%s'," % probe)
            print("       'block_start': \"%s\"," % bs)
            print("       'block_end': \"%s\"," % be)
            print("       'probe_type': '%s'," % probe_type)
            print("       'electrode_config_name': '%s'," % electrode_config_name)
            print("       'electrode_group': '%s'," % electrode_group)
            print("       'paramset_id': '%s'}" % str(paramset_id))
    print("Done!")


if __name__ == "__main__":
    main()


