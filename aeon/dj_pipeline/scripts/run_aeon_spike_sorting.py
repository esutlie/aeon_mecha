"""
This is a one-off script to test run the spike sorting pipeline on a specific dataset (key).
Run script from the root directory of the aeon_mecha repository
Run in the conda environment with aeon_mecha (ephys-branch) installed

Change the value of `key` below if you want to run spike sorting on a different dataset.
"""

import datajoint as dj
from aeon.dj_pipeline import acquisition, ephys, spike_sorting

# Specify which table to populate: "PreProcessing", "SpikeSorting", or "PostProcessing"
table_name = "SpikeSorting"
# Specify the key to be populated
# # First 30 hour test block
# key = {'experiment_name': 'social-ephys0.1-aeon3',
#        'probe': 'NP2004-001',
#        'block_start': "2024-06-04 11:00:00",
#        'block_end': "2024-06-05 17:00:00",
#        'probe_type': 'neuropixels - NP2004',
#        'electrode_config_name': '0-383',
#        'electrode_group': '0-95',
#        'paramset_id': '400'}


# # Block 1 job 2263514
# key = {'experiment_name': 'social-ephys0.1-aeon3',
#        'probe': 'NP2004-001',
#        'block_start': "2024-06-04 11:00:00",
#        'block_end': "2024-06-04 14:00:00",
#        'probe_type': 'neuropixels - NP2004',
#        'electrode_config_name': '0-383',
#        'electrode_group': '0-95',
#        'paramset_id': '400'}

# # Block 2 job 2263702
# key = {'experiment_name': 'social-ephys0.1-aeon3',
#        'probe': 'NP2004-001',
#        'block_start': "2024-06-04 13:00:00",
#        'block_end': "2024-06-04 16:00:00",
#        'probe_type': 'neuropixels - NP2004',
#        'electrode_config_name': '0-383',
#        'electrode_group': '0-95',
#        'paramset_id': '400'}

# Block 3 job 2264184
key = {'experiment_name': 'social-ephys0.1-aeon3',
       'probe': 'NP2004-001',
       'block_start': "2024-06-04 15:00:00",
       'block_end': "2024-06-04 18:00:00",
       'probe_type': 'neuropixels - NP2004',
       'electrode_config_name': '0-383',
       'electrode_group': '0-95',
       'paramset_id': '400'}
"""
Then use these lines to submit the job to slurm from the hpc
cd ProjectAeon/aeon_mecha
sbatch run_aeon_spike_sorting.sh
"""
_CLEAR_JOB = True  # Whether to clear any existing 'error' job for this key before populating


def clear_job(dj_table):
    """
    Clear this `key` from the jobs table (if any) to allow re-running the job 
    E.g. if this job previously failed with `error` status
    """
    (spike_sorting.schema.jobs & {
        "table_name": dj_table.table_name,
        "key_hash": dj.key_hash(key),
        "status": "error"}).delete()


def main():
    populate_table = {
        "PreProcessing": spike_sorting.PreProcessing,
        "SpikeSorting": spike_sorting.SpikeSorting,
        "PostProcessing": spike_sorting.PostProcessing,
    }[table_name]

    if _CLEAR_JOB:
        clear_job(populate_table)
    populate_table.populate(key, reserve_jobs=True, display_progress=True)


if __name__ == '__main__':
    main()
