"""
Run spike sorting post-processing steps for all available sorting tasks.

This script is intended to be used after PreProcessing has run and SpikeSorting
results have been generated (or are being generated). It will attempt to
populate the tables downstream of SpikeSorting that are needed to bring the
pipeline to a manual-curation-ready state.

Tables populated (in order):
    1. SpikeSorting
    2. PostProcessing
    3. SIExport
    4. SortedSpikes

Run from the root of the aeon_mecha repository in the appropriate environment.
"""

from __future__ import annotations

import pprint
import time

from aeon.dj_pipeline import spike_sorting


# -------------------------
# User-configurable options
# -------------------------

# Which tables to populate. You can comment out any you don't want to run.
TABLES_TO_POPULATE = [
    "PostProcessing",
    "SIExport",
    "SortedSpikes",
]

# Whether to use the DataJoint jobs table to reserve work (recommended for Slurm)
RESERVE_JOBS = True

# Whether to show progress bars/logging from DataJoint
DISPLAY_PROGRESS = True


def clear_error_jobs(dj_table) -> None:
    """
    Clear any 'error' jobs for this table from the jobs table, to allow re-runs.

    This is similar to the helper in run_aeon_spike_sorting.py.
    """
    (spike_sorting.schema.jobs & {
        "table_name": dj_table.table_name,
        "status": "error",
    }).delete()


def main() -> None:
    table_map = {
        "PostProcessing": spike_sorting.PostProcessing,
        "SIExport": spike_sorting.SIExport,
        "SortedSpikes": spike_sorting.SortedSpikes,
    }
    # Key sources (upstream tables) to estimate how many keys/sessions we will process.
    source_map = {
        "PostProcessing": spike_sorting.SpikeSorting,
        "SIExport": spike_sorting.PostProcessing,
        "SortedSpikes": spike_sorting.PostProcessing,
    }

    summary = []

    for name in TABLES_TO_POPULATE:
        dj_table = table_map[name]
        source_table = source_map.get(name)

        print(f"\n=== Populating {name} ===")

        # Estimate how many keys and sessions remain before running populate
        num_keys = 0
        num_sessions = 0
        keys_to_do = []
        if source_table is not None:
            # Use dj_table.proj() so subtraction is done on the shared primary key
            # only. This avoids join-compatibility issues on dependent attributes
            # (e.g. execution_duration) in legacy DataJoint (0.14).
            keys_to_do = (source_table - dj_table.proj()).fetch("KEY")
            num_keys = len(keys_to_do)
            session_ids = {
                (k.get("experiment_name"), k.get("probe")) for k in keys_to_do
                if "experiment_name" in k and "probe" in k
            }
            num_sessions = len(session_ids)

        print(
            f"{name}: {num_keys} key(s) remaining across {num_sessions} session(s) "
            "(experiment_name, probe)."
        )
        if keys_to_do:
            print(f"Keys to be processed:")
            for key in keys_to_do:
                print(f"  {pprint.pformat(key)}")

        # Clear any previous error jobs so failed keys can be retried.
        clear_error_jobs(dj_table)

        start = time.time()
        # Note: no key restriction here; this will attempt to process all missing keys.
        dj_table.populate(reserve_jobs=RESERVE_JOBS, display_progress=DISPLAY_PROGRESS)
        elapsed_h = (time.time() - start) / 3600.0

        per_session_h = elapsed_h / num_sessions if num_sessions > 0 else float("nan")
        per_key_h = elapsed_h / num_keys if num_keys > 0 else float("nan")

        print(
            f"{name} populate wall time: {elapsed_h:.3f} hours "
            f"(~{per_session_h:.3f} h/session, ~{per_key_h:.3f} h/key)."
        )
        summary.append(
            (name, elapsed_h, num_sessions, num_keys, per_session_h, per_key_h)
        )

    if summary:
        print("\n=== Post-processing timing summary ===")
        for name, elapsed_h, num_sessions, num_keys, per_session_h, per_key_h in summary:
            print(
                f"{name}: {elapsed_h:.3f} h total, "
                f"{num_sessions} session(s), {num_keys} key(s), "
                f"{per_session_h:.3f} h/session, {per_key_h:.3f} h/key"
            )

    print("\nAll requested post-processing tables have been populated.")


if __name__ == "__main__":
    main()


