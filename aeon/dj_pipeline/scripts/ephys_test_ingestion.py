import sys
print(f"DEBUG: Python interpreter: {sys.executable}")
print(f"DEBUG: Python version: {sys.version}")

import uuid
import pandas as pd
from pathlib import Path
from datetime import datetime

from aeon.dj_pipeline import acquisition, ephys, spike_sorting

# Constants
experiment_name = 'social-ephys0.1-aeon3'
probe_name = 'NP2004-001'
probe_type = 'neuropixels - NP2004'
electrode_config_name = '0-383'


# ---- Probe Configuration Check/Setup ----

# ProbeType - Neuropixels 2.0 Single-Shank
if not (ephys.ProbeType & {"probe_type": "neuropixels - NP2004"}):
    ephys.create_probe_type("neuropixels - NP2004",
                            manufacturer="neuropixels",
                            probe_name="NP2004")
# ProbeType - Neuropixels 2.0 Multi-Shank
if not (ephys.ProbeType & {"probe_type": "neuropixels - NP2014"}):
    ephys.create_probe_type("neuropixels - NP2014",
                            manufacturer="neuropixels",
                            probe_name="NP2014")

# Probe
ephys.Probe.insert1(
    dict(
        probe=probe_name,
        probe_type=probe_type,
        probe_comment='',
    ),
    skip_duplicates=True
)

# ElectrodeConfig
ephys.ElectrodeConfig.insert1(
    dict(
        probe_type=probe_type,
        electrode_config_name=electrode_config_name,
        electrode_config_description='',
        electrode_config_hash=uuid.uuid4(),
    ),
    skip_duplicates=True
)

# Check if electrode entries already exist before inserting
electrode_config_key = {
    "probe_type": probe_type,
    "electrode_config_name": electrode_config_name
}
existing_electrode_count = len(ephys.ElectrodeConfig.Electrode & electrode_config_key)
if existing_electrode_count < 384:
    ephys.ElectrodeConfig.Electrode.insert(
        (
            dict(
                probe_type=probe_type,
                electrode_config_name=electrode_config_name,
                electrode=elec,
            )
            for elec in range(384)
        ),
        skip_duplicates=True
    )


# ---- Experiment Setup ----

acquisition.Experiment.insert1(
    {'experiment_name': experiment_name,
     'experiment_start_time': "2024-06-01 06:00:00",
     'experiment_description': 'social ephys experiment 0.1 - AEON3',
     'arena_name': 'circle-2m',
     'lab': 'SWC',
     'location': 'AEON3',
     'experiment_type': 'social'},
    skip_duplicates=True
)
acquisition.Experiment.Directory.insert(
    [{'experiment_name': experiment_name,
      'directory_type': 'ingest',
      'repository_name': 'ceph_aeon',
      'directory_path': 'aeon/data/ingest/AEONX1/social-ephys0.1',
      'load_order': 1},
     {'experiment_name': experiment_name,
      'directory_type': 'raw',
      'repository_name': 'ceph_aeon',
      'directory_path': 'aeon/data/raw/AEONX1/social-ephys0.1',
      'load_order': 0}],
    skip_duplicates=True
)


# ---- Ephys Chunk Ingestion ----

# ephys.EphysChunk.ingest_chunks(experiment_name)

# Check actual chunk time range
exp_key = {"experiment_name": experiment_name, "probe": probe_name}
chunk_starts, chunk_ends = (ephys.EphysChunk & exp_key).fetch("chunk_start", "chunk_end")
if len(chunk_starts) > 0:
    actual_start = pd.Timestamp(min(chunk_starts))
    actual_end = pd.Timestamp(max(chunk_ends))
    print(f"\nActual ephys data range from EphysChunk:")
    print(f"  Start: {actual_start}")
    print(f"  End: {actual_end}")
else:
    raise ValueError(f"No ephys chunks found for {experiment_name}, {probe_name}. Cannot proceed with block creation.")


# ---- Create 30-Hour Overlapping EphysBlocks ----

block_start = pd.Timestamp('2024-06-04 11:00:00')
experiment_end = pd.Timestamp('2024-06-10 12:00:00')
blocks = []

while block_start + pd.Timedelta(hours=30) <= experiment_end:
    block_end = block_start + pd.Timedelta(hours=30)
    block_key = dict(
        experiment_name=experiment_name,
        probe=probe_name,
        block_start=block_start,
        block_end=block_end
    )
    ephys.EphysBlock.insert1(block_key, skip_duplicates=True)
    ephys.EphysBlockInfo.populate(block_key)
    
    # Verify EphysBlockInfo was populated and contains chunks
    if not (ephys.EphysBlockInfo & block_key):
        raise RuntimeError(f"EphysBlockInfo.populate() failed for block {block_key}")
    chunk_count = len(ephys.EphysBlockInfo.Chunk & block_key)
    if chunk_count == 0:
        raise RuntimeError(f"EphysBlockInfo.populate() succeeded but found no chunks for block {block_key}")
    
    blocks.append(block_key)
    block_start = block_start + pd.Timedelta(hours=24)  # 24 = 30 - 6 overlap

# Add final block if there's remaining data (at least 6 hours to be worth it)
if block_start < experiment_end:
    remaining_time = experiment_end - block_start
    if remaining_time >= pd.Timedelta(hours=6):  # Only add if >= overlap duration
        block_key = dict(
            experiment_name=experiment_name,
            probe=probe_name,
            block_start=block_start,
            block_end=experiment_end
        )
        ephys.EphysBlock.insert1(block_key, skip_duplicates=True)
        ephys.EphysBlockInfo.populate(block_key)
        
        # Verify EphysBlockInfo was populated and contains chunks
        if not (ephys.EphysBlockInfo & block_key):
            raise RuntimeError(f"EphysBlockInfo.populate() failed for final block {block_key}")
        chunk_count = len(ephys.EphysBlockInfo.Chunk & block_key)
        if chunk_count == 0:
            raise RuntimeError(f"EphysBlockInfo.populate() succeeded but found no chunks for final block {block_key}")
        
        blocks.append(block_key)


# ---- Create Electrode Groups (4 Equal Parts) ----

# Get electrodes from ElectrodeConfig (these are the ones actually used)
config_electrodes = (ephys.ElectrodeConfig.Electrode & electrode_config_key).fetch(
    "electrode", order_by="electrode"
)

# Divide into 4 equal groups (single-shank probe, so no shank-based grouping needed)
group_size = len(config_electrodes) // 4  # 96 electrodes per group (384 total)
electrode_groups = [
    (f"{config_electrodes[i * group_size]}-{config_electrodes[(i + 1) * group_size - 1]}", 
     list(config_electrodes[i * group_size:(i + 1) * group_size]))
    for i in range(4)
]

# Insert electrode groups
for group_name, group_electrodes in electrode_groups:
    spike_sorting.ElectrodeGroup.insert1(
        dict(
            probe_type=probe_type,
            electrode_config_name=electrode_config_name,
            electrode_group=group_name,
            electrode_group_description=f'electrodes {group_name}',
            electrode_count=len(group_electrodes),
        ),
        skip_duplicates=True
    )
    spike_sorting.ElectrodeGroup.Electrode.insert(
        (
            dict(
                probe_type=probe_type,
                electrode_config_name=electrode_config_name,
                electrode_group=group_name,
                electrode=elec,
            )
            for elec in group_electrodes
        ),
        skip_duplicates=True
    )


# ---- Check/Create Sorting Param Sets ----

# kilosort 2.5
if not (spike_sorting.SortingParamSet & {"paramset_id": 250}):
    params = {}
    params["SI_PREPROCESSING_METHOD"] = "ephys_preproc"
    params["SI_SORTING_PARAMS"] = {
        "minfr_goodchannels": 0.1,
        "lam": 10,
        "AUCsplit": 0.9,
        "minFR": 0.02,
        "sigmaMask": 30,
        "nfilt_factor": 4,
        "ntbuff": 64,
        "scaleproc": 200,
        "nPCs": 3,
        'do_correction': True,
        "keep_good_only": True
    }
    params["SI_POSTPROCESSING_PARAMS"] = {
        "extensions": {
            "random_spikes": {},
            "waveforms": {},
            "templates": {},
            "noise_levels": {},
            "correlograms": {},
            "isi_histograms": {},
            "principal_components": {"n_components": 5, "mode": "by_channel_local"},
            "spike_amplitudes": {},
            "spike_locations": {},
            "template_metrics": {"include_multi_channel_metrics": True},
            "template_similarity": {},
            "unit_locations": {},
            "quality_metrics": {},
        },
        "job_kwargs": {"n_jobs": 0.8, "chunk_duration": "1s"},
        "export_to_phy": False,
        "export_report": True,
    }
    spike_sorting.SortingParamSet.insert1(
        dict(
            paramset_id=250,
            sorting_method='kilosort2.5',
            paramset_description='Kilosort2.5 - default params',
            params=params,
        ),
        skip_duplicates=True
    )

# kilosort 3
if not (spike_sorting.SortingParamSet & {"paramset_id": 300}):
    params = {}
    params["SI_PREPROCESSING_METHOD"] = "ephys_preproc"
    params["SI_SORTING_PARAMS"] = {
        "minfr_goodchannels": 0.1,
        "lam": 10,
        "AUCsplit": 0.9,
        "minFR": 0.02,
        "sigmaMask": 30,
        "nfilt_factor": 4,
        "ntbuff": 64,
        "scaleproc": 200,
        "nPCs": 3,
        'do_correction': True,
        "keep_good_only": True
    }
    params["SI_POSTPROCESSING_PARAMS"] = {
        "extensions": {
            "random_spikes": {},
            "waveforms": {},
            "templates": {},
            "noise_levels": {},
            "correlograms": {},
            "isi_histograms": {},
            "principal_components": {"n_components": 5, "mode": "by_channel_local"},
            "spike_amplitudes": {},
            "spike_locations": {},
            "template_metrics": {"include_multi_channel_metrics": True},
            "template_similarity": {},
            "unit_locations": {},
            "quality_metrics": {},
        },
        "job_kwargs": {"n_jobs": 0.8, "chunk_duration": "1s"},
        "export_to_phy": False,
        "export_report": True,
    }
    spike_sorting.SortingParamSet.insert1(
        dict(
            paramset_id=300,
            sorting_method='kilosort3',
            paramset_description='Kilosort3 - Drift Correction disabled',
            params=params,
        ),
        skip_duplicates=True
    )

# kilosort 4
if not (spike_sorting.SortingParamSet & {"paramset_id": 400}):
    params = {}
    params["SI_PREPROCESSING_METHOD"] = "ephys_preproc"
    params["SI_SORTING_PARAMS"] = {
        "n_pcs": 3,
        "do_CAR": False,
        "keep_good_only": True,
        "use_binary_file": True,
    }
    params["SI_POSTPROCESSING_PARAMS"] = {
        "extensions": {
            "random_spikes": {},
            "waveforms": {},
            "templates": {},
            "noise_levels": {},
            "correlograms": {},
            "isi_histograms": {},
            "principal_components": {"n_components": 5, "mode": "by_channel_local"},
            "spike_amplitudes": {},
            "spike_locations": {},
            "template_metrics": {"include_multi_channel_metrics": True},
            "template_similarity": {},
            "unit_locations": {},
            "quality_metrics": {},
        },
        "job_kwargs": {"n_jobs": 0.8, "chunk_duration": "1s"},
        "export_to_phy": False,
        "export_report": True,
    }
    spike_sorting.SortingParamSet.insert1(
        dict(
            paramset_id=400,
            sorting_method='kilosort4',
            paramset_description='Default parameter set for Kilosort4 with SpikeInterface',
            params=params,
        ),
        skip_duplicates=True
    )


# ---- Create SortingTask ----

if len(blocks) == 0:
    raise ValueError("No blocks created. Cannot create SortingTask.")

first_block = blocks[0]
first_electrode_group = electrode_groups[0][0]  # Get the group name

sorting_task_key = dict(
    **first_block,
    probe_type=probe_type,
    electrode_config_name=electrode_config_name,
    electrode_group=first_electrode_group,
    paramset_id=400,
)

spike_sorting.SortingTask.insert1(sorting_task_key, skip_duplicates=True)


# ---- Populate Spike Sorting Pipeline Tables ----

print("\nPopulating PreProcessing...")
spike_sorting.PreProcessing.populate(sorting_task_key, display_progress=True)

