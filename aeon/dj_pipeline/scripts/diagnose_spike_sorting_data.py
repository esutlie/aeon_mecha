#!/usr/bin/env python
"""
Diagnostic script to investigate data corruption or mishandling in spike sorting pipeline.

This script checks:
1. Preprocessed recording object integrity
2. Binary file integrity and dtype consistency
3. Data statistics (mean, std, min, max, zeros)
4. Channel selection correctness
5. Preprocessing effects
6. Visual inspection of sample traces
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import datajoint as dj
import spikeinterface as si
import spikeinterface.extractors as se
from aeon.dj_pipeline import spike_sorting, acquisition


def get_sorting_task_key_from_error_path(error_path: str) -> Optional[Dict[str, Any]]:
    """Extract sorting task key from error log path.
    
    Example path: /ceph/aeon/aeon/dj_store/ephys-processed/social-ephys0.1-aeon3/ephys_blocks/2024-06-04T11-00-00_2024-06-05T17-00-00/0-95/kilosort4_400/
    """
    path = Path(error_path)
    parts = path.parts
    
    # Find ephys_blocks in path
    try:
        ephys_idx = parts.index('ephys_blocks')
        experiment_name = parts[ephys_idx - 1]
        block_str = parts[ephys_idx + 1]  # e.g., "2024-06-04T11-00-00_2024-06-05T17-00-00"
        electrode_group = parts[ephys_idx + 2]  # e.g., "0-95"
        method_param = parts[ephys_idx + 3]  # e.g., "kilosort4_400"
    except (ValueError, IndexError) as e:
        print(f"Could not parse path: {error_path}")
        print(f"Error: {e}")
        return None
    
    # Parse block times
    start_str, end_str = block_str.split('_')
    block_start = pd.Timestamp(start_str.replace('T', ' '))
    block_end = pd.Timestamp(end_str.replace('T', ' '))
    
    # Parse paramset_id from method_param
    paramset_id = int(method_param.split('_')[-1])
    
    return {
        'experiment_name': experiment_name,
        'block_start': block_start,
        'block_end': block_end,
        'electrode_group': electrode_group,
        'paramset_id': paramset_id,
    }


def check_recording_basic_info(recording: si.BaseRecording, name: str = "Recording"):
    """Check basic recording properties."""
    print(f"\n{'='*60}")
    print(f"{name} Basic Information")
    print(f"{'='*60}")
    print(f"Number of channels: {recording.get_num_channels()}")
    print(f"Number of samples: {recording.get_num_samples():,}")
    print(f"Sampling frequency: {recording.get_sampling_frequency()} Hz")
    print(f"Duration: {recording.get_num_samples() / recording.get_sampling_frequency():.2f} seconds")
    print(f"Channel IDs: {recording.get_channel_ids()[:10]}..." if len(recording.get_channel_ids()) > 10 else f"Channel IDs: {recording.get_channel_ids()}")
    
    # Check probe
    probe = recording.get_probe()
    if probe is not None:
        print(f"Probe has geometry: {probe.contact_positions is not None}")
        if probe.contact_positions is not None:
            print(f"Number of contact positions: {len(probe.contact_positions)}")
    else:
        print("WARNING: No probe geometry attached!")


def check_data_statistics(recording: si.BaseRecording, name: str = "Recording", 
                         sample_size: int = 100000):
    """Check data statistics by sampling a portion of the recording."""
    print(f"\n{'='*60}")
    print(f"{name} Data Statistics (sampling {sample_size:,} samples)")
    print(f"{'='*60}")
    
    # Get a chunk of data
    num_samples = recording.get_num_samples()
    start_sample = min(1000000, num_samples // 4)  # Start 1M samples in or 1/4 through
    end_sample = min(start_sample + sample_size, num_samples)
    
    print(f"Sampling from sample {start_sample:,} to {end_sample:,}")
    
    try:
        traces = recording.get_traces(start_frame=start_sample, end_frame=end_sample)
        print(f"Traces shape: {traces.shape}")
        print(f"Data dtype: {traces.dtype}")
        
        # Overall statistics
        print(f"\nOverall Statistics:")
        print(f"  Mean: {np.mean(traces):.2f}")
        print(f"  Std: {np.std(traces):.2f}")
        print(f"  Min: {np.min(traces):.2f}")
        print(f"  Max: {np.max(traces):.2f}")
        print(f"  Median: {np.median(traces):.2f}")
        
        # Check for zeros
        zero_count = np.sum(traces == 0)
        zero_pct = 100 * zero_count / traces.size
        print(f"  Zeros: {zero_count:,} ({zero_pct:.2f}%)")
        
        # Check for constant channels
        channel_stds = np.std(traces, axis=0)
        constant_channels = np.sum(channel_stds < 1e-6)
        if constant_channels > 0:
            print(f"  WARNING: {constant_channels} channels have near-zero std (< 1e-6)")
        
        # Per-channel statistics (sample a few channels)
        num_channels = traces.shape[1]
        sample_channels = min(5, num_channels)
        print(f"\nPer-Channel Statistics (showing first {sample_channels} channels):")
        for ch_idx in range(sample_channels):
            ch_traces = traces[:, ch_idx]
            print(f"  Channel {ch_idx}: mean={np.mean(ch_traces):.2f}, "
                  f"std={np.std(ch_traces):.2f}, "
                  f"min={np.min(ch_traces):.2f}, max={np.max(ch_traces):.2f}")
        
        return traces
        
    except Exception as e:
        print(f"ERROR getting traces: {e}")
        import traceback
        traceback.print_exc()
        return None


def check_binary_file(binary_file_path: Path, recording: si.BaseRecording):
    """Check binary file integrity and compare with recording object."""
    print(f"\n{'='*60}")
    print(f"Binary File Check: {binary_file_path}")
    print(f"{'='*60}")
    
    if not binary_file_path.exists():
        print(f"ERROR: Binary file does not exist!")
        return None
    
    # Check file size
    file_size = binary_file_path.stat().st_size
    print(f"File size: {file_size:,} bytes ({file_size / 1e9:.2f} GB)")
    
    # Expected size: num_samples * num_channels * dtype_size
    expected_size_int16 = recording.get_num_samples() * recording.get_num_channels() * 2
    expected_size_uint16 = recording.get_num_samples() * recording.get_num_channels() * 2
    print(f"Expected size (int16/uint16): {expected_size_int16:,} bytes ({expected_size_int16 / 1e9:.2f} GB)")
    
    if abs(file_size - expected_size_int16) > 1000:  # Allow 1KB tolerance
        print(f"WARNING: File size mismatch! Difference: {abs(file_size - expected_size_int16):,} bytes")
    
    # Try reading as int16 (how it was written)
    print(f"\nTrying to read as int16 (how it was written)...")
    try:
        binary_rec_int16 = se.read_binary(
            binary_file_path,
            sampling_frequency=recording.get_sampling_frequency(),
            dtype=np.int16,
            num_channels=recording.get_num_channels(),
            gain_to_uV=recording.get_channel_gains()[0] if len(recording.get_channel_gains()) > 0 else 1.0
        )
        print(f"  Successfully read as int16")
        print(f"  Samples: {binary_rec_int16.get_num_samples():,}")
        print(f"  Channels: {binary_rec_int16.get_num_channels()}")
        
        # Check a sample of data
        sample_traces_int16 = binary_rec_int16.get_traces(start_frame=0, end_frame=1000)
        print(f"  Sample data shape: {sample_traces_int16.shape}")
        print(f"  Sample data dtype: {sample_traces_int16.dtype}")
        print(f"  Sample mean: {np.mean(sample_traces_int16):.2f}, std: {np.std(sample_traces_int16):.2f}")
        
    except Exception as e:
        print(f"  ERROR reading as int16: {e}")
        binary_rec_int16 = None
    
    # Try reading as uint16 (how load_and_verify_binary_file reads it - POTENTIAL BUG!)
    print(f"\nTrying to read as uint16 (how load_and_verify_binary_file reads it)...")
    try:
        binary_rec_uint16 = se.read_binary(
            binary_file_path,
            sampling_frequency=recording.get_sampling_frequency(),
            dtype=np.uint16,
            num_channels=recording.get_num_channels(),
            gain_to_uV=recording.get_channel_gains()[0] if len(recording.get_channel_gains()) > 0 else 1.0
        )
        print(f"  Successfully read as uint16")
        print(f"  Samples: {binary_rec_uint16.get_num_samples():,}")
        print(f"  Channels: {binary_rec_uint16.get_num_channels()}")
        
        # Check a sample of data
        sample_traces_uint16 = binary_rec_uint16.get_traces(start_frame=0, end_frame=1000)
        print(f"  Sample data shape: {sample_traces_uint16.shape}")
        print(f"  Sample data dtype: {sample_traces_uint16.dtype}")
        print(f"  Sample mean: {np.mean(sample_traces_uint16):.2f}, std: {np.std(sample_traces_uint16):.2f}")
        
        # Compare with int16 version
        if binary_rec_int16 is not None:
            sample_traces_int16_comp = binary_rec_int16.get_traces(start_frame=0, end_frame=1000)
            print(f"\n  COMPARISON (first 1000 samples):")
            print(f"    int16 mean: {np.mean(sample_traces_int16_comp):.2f}")
            print(f"    uint16 mean: {np.mean(sample_traces_uint16):.2f}")
            print(f"    Difference: {np.mean(np.abs(sample_traces_int16_comp - sample_traces_uint16)):.2f}")
            if np.mean(np.abs(sample_traces_int16_comp - sample_traces_uint16)) > 100:
                print(f"    *** WARNING: Large difference! This is the dtype mismatch bug! ***")
        
    except Exception as e:
        print(f"  ERROR reading as uint16: {e}")
        binary_rec_uint16 = None
    
    return binary_rec_int16, binary_rec_uint16


def compare_recordings(rec1: si.BaseRecording, rec2: si.BaseRecording, 
                      name1: str = "Recording 1", name2: str = "Recording 2",
                      sample_size: int = 10000):
    """Compare two recordings."""
    print(f"\n{'='*60}")
    print(f"Comparing {name1} vs {name2}")
    print(f"{'='*60}")
    
    # Check basic properties
    print(f"\nBasic Properties:")
    print(f"  {name1}: {rec1.get_num_samples():,} samples, {rec1.get_num_channels()} channels")
    print(f"  {name2}: {rec2.get_num_samples():,} samples, {rec2.get_num_channels()} channels")
    
    if rec1.get_num_samples() != rec2.get_num_samples():
        print(f"  *** MISMATCH: Sample counts differ! ***")
    
    if rec1.get_num_channels() != rec2.get_num_channels():
        print(f"  *** MISMATCH: Channel counts differ! ***")
    
    # Compare data
    try:
        start_sample = min(100000, rec1.get_num_samples() // 4)
        end_sample = min(start_sample + sample_size, rec1.get_num_samples())
        
        traces1 = rec1.get_traces(start_frame=start_sample, end_frame=end_sample)
        traces2 = rec2.get_traces(start_frame=start_sample, end_frame=end_sample)
        
        print(f"\nData Comparison (samples {start_sample:,} to {end_sample:,}):")
        print(f"  {name1} shape: {traces1.shape}, dtype: {traces1.dtype}")
        print(f"  {name2} shape: {traces2.shape}, dtype: {traces2.dtype}")
        
        if traces1.shape == traces2.shape:
            diff = np.abs(traces1 - traces2)
            print(f"  Mean absolute difference: {np.mean(diff):.2f}")
            print(f"  Max absolute difference: {np.max(diff):.2f}")
            print(f"  Mean relative difference: {np.mean(diff / (np.abs(traces1) + 1e-10)) * 100:.2f}%")
            
            if np.mean(diff) > 100:
                print(f"  *** WARNING: Large differences detected! ***")
        else:
            print(f"  *** ERROR: Shape mismatch! Cannot compare. ***")
            
    except Exception as e:
        print(f"  ERROR comparing data: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main diagnostic function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Diagnose spike sorting data integrity")
    parser.add_argument("--key", type=str, help="Sorting task key as dict string or path to error log")
    parser.add_argument("--output-dir", type=str, help="Direct path to output directory")
    args = parser.parse_args()
    
    # Get sorting task key
    if args.output_dir:
        output_dir = Path(args.output_dir)
        # Try to infer key from path
        key = get_sorting_task_key_from_error_path(str(output_dir))
        if key is None:
            print("Could not infer key from output_dir. Please provide --key instead.")
            return
    elif args.key:
        # Try to parse as dict or path
        if Path(args.key).exists():
            key = get_sorting_task_key_from_error_path(args.key)
        else:
            import ast
            key = ast.literal_eval(args.key)
    else:
        # Try to get from the error log path mentioned in the error
        error_path = "/ceph/aeon/aeon/dj_store/ephys-processed/social-ephys0.1-aeon3/ephys_blocks/2024-06-04T11-00-00_2024-06-05T17-00-00/0-95/kilosort4_400"
        key = get_sorting_task_key_from_error_path(error_path)
        if key is None:
            print("Please provide --key or --output-dir")
            parser.print_help()
            return
    
    print(f"Sorting Task Key: {key}")
    
    # Get output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = spike_sorting.PreProcessing.infer_output_dir(key)
        output_dir = Path(spike_sorting.get_sorting_root_dir()) / output_dir
    
    print(f"\nOutput Directory: {output_dir}")
    
    # Check if preprocessing completed
    try:
        preproc_entry = (spike_sorting.PreProcessing & key).fetch1()
        print(f"\nPreProcessing entry found (execution time: {preproc_entry['execution_time']})")
    except dj.DataJointError as e:
        print(f"\nWARNING: Could not fetch PreProcessing entry: {e}")
        print("Will try to load files directly from output directory...")
    
    # Find recording file
    recording_file = output_dir / "si_recording.pkl"
    if not recording_file.exists():
        # Try to find it via database
        try:
            recording_file = (spike_sorting.PreProcessing.File 
                            & key & "file_name LIKE '%si_recording.pkl'").fetch1("file")
            recording_file = Path(recording_file)
        except dj.DataJointError:
            print(f"ERROR: Could not find recording file!")
            return
    
    print(f"\nRecording file: {recording_file}")
    
    # Load recording
    print(f"\nLoading preprocessed recording...")
    try:
        si_recording = si.load(recording_file, base_folder=output_dir)
        print("Successfully loaded recording")
    except Exception as e:
        print(f"ERROR loading recording: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Check recording
    check_recording_basic_info(si_recording, "Preprocessed Recording")
    check_data_statistics(si_recording, "Preprocessed Recording")
    
    # Check binary file
    binary_file_path = recording_file.parent / "recording.dat"
    binary_rec_int16, binary_rec_uint16 = check_binary_file(binary_file_path, si_recording)
    
    # Compare binary files with recording
    if binary_rec_int16 is not None:
        compare_recordings(si_recording, binary_rec_int16, 
                          "Preprocessed Recording", "Binary File (int16)")
    
    if binary_rec_uint16 is not None:
        compare_recordings(si_recording, binary_rec_uint16,
                          "Preprocessed Recording", "Binary File (uint16)")
        if binary_rec_int16 is not None:
            compare_recordings(binary_rec_int16, binary_rec_uint16,
                             "Binary File (int16)", "Binary File (uint16)")
    
    print(f"\n{'='*60}")
    print("Diagnostic Summary")
    print(f"{'='*60}")
    print("\nKey findings:")
    print("1. Check if data statistics look reasonable (non-zero std, reasonable ranges)")
    print("2. Check if binary file dtype matches how it's read")
    print("3. Check if there are large differences between recording and binary file")
    print("\nIf you see dtype mismatches or large differences, that's likely the issue!")


if __name__ == "__main__":
    main()

