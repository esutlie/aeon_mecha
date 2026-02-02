"""
Script to wipe ephys schema tables for a specific experiment.

This script deletes all ephys-related data for a given experiment, including:
- Spike sorting pipeline tables (PreProcessing, SpikeSorting, PostProcessing, etc.)
- Ephys blocks and chunks
- All associated part tables

DataJoint will cascade deletes to all dependent tables.

WARNING: This permanently deletes data from the database. The associated files
in ephys-processed should be deleted separately (manually or via filesystem commands).

Run script from the root directory of the aeon_mecha repository
Run in the conda environment with aeon_mecha installed
"""

import datajoint as dj
from aeon.dj_pipeline import ephys, acquisition

# acquisition.Experiment & {"experiment_name": "social-ephys0.1-aeon3"}

# Specify the experiment to wipe
experiment_name = 'social-ephys0.1-aeon3'


def wipe_ephys_data(experiment_name: str):
    """
    Delete all ephys schema data for the specified experiment.
    
    Args:
        experiment_name: Name of the experiment to wipe
    """
    exp_key = {"experiment_name": experiment_name}
    
    print(f"Wiping ephys data for experiment: {experiment_name}")
    
    # Delete EphysBlock - will cascade to EphysBlockInfo and SortingTask (and all downstream)
    print("\nDeleting ephys blocks (cascades to block info and sorting tasks)...")
    (ephys.EphysBlock & exp_key).delete(safemode=False)
    print("  ✓ EphysBlock (and all dependent tables)")
    
    # Delete EphysChunk (independent, doesn't cascade from EphysBlock)
    print("\nDeleting ephys chunks...")
    (ephys.EphysChunk & exp_key).delete(safemode=False)
    print("  ✓ EphysChunk")
    
    print("\n✓ Ephys data wiped successfully!")
    print("\nNOTE: Files in ephys-processed directory are NOT deleted by this script.")
    print("      Delete them separately using filesystem commands.")


if __name__ == '__main__':
    print(f"\n⚠️  WARNING: This will permanently delete all ephys processing data for experiment: {experiment_name}")
    print("This includes all ephys blocks, chunks, and spike sorting pipeline data.")
    print("\nTo confirm deletion, type 'delete' (case-insensitive):")
    confirmation = input("> ").strip().lower()
    
    if confirmation == 'delete':
        wipe_ephys_data(experiment_name)
    else:
        print("\n✗ Deletion cancelled. No data was deleted.")
