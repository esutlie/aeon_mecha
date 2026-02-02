#!/usr/bin/env python
"""
Quick diagnostic script to check data integrity for a failed spike sorting job.

Usage:
    uv run python aeon/dj_pipeline/scripts/quick_data_check.py

Or with specific key:
    uv run python aeon/dj_pipeline/scripts/quick_data_check.py --experiment social-ephys0.1-aeon3 --block-start "2024-06-04 11:00:00" --block-end "2024-06-05 17:00:00" --electrode-group "0-95" --paramset-id 400
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import datajoint as dj
import spikeinterface as si
import spikeinterface.extractors as se
from aeon.dj_pipeline import spike_sorting


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Quick data integrity check")
    parser.add_argument("--experiment", type=str, default="social-ephys0.1-aeon3")
    parser.add_argument("--block-start", type=str, default="2024-06-04 11:00:00")
    parser.add_argument("--block-end", type=str, default="2024-06-05 17:00:00")
    parser.add_argument("--electrode-group", type=str, default="0-95")
    parser.add_argument("--paramset-id", type=int, default=400)
    
    args = parser.parse_args()
    
    # Build key
    key = {
        'experiment_name': args.experiment,
        'block_start': pd.Timestamp(args.block_start),
        'block_end': pd.Timestamp(args.block_end),
        'electrode_group': args.electrode_group,
        'paramset_id': args.paramset_id,
    }
    
    print("="*70)
    print("SPIKE SORTING DATA INTEGRITY CHECK")
    print("="*70)
    print(f"\nSorting Task Key:")
    for k, v in key.items():
        print(f"  {k}: {v}")
    
    # Get output directory
    try:
        output_dir = spike_sorting.PreProcessing.infer_output_dir(key)
        output_dir = Path(spike_sorting.get_sorting_root_dir()) / output_dir
        print(f"\nOutput Directory: {output_dir}")
    except Exception as e:
        print(f"\nERROR getting output directory: {e}")
        return
    
    if not output_dir.exists():
        print(f"\nERROR: Output directory does not exist!")
        return
    
    # Find recording file
    recording_file = output_dir / "si_recording.pkl"
    if not recording_file.exists():
        try:
            recording_file = (spike_sorting.PreProcessing.File 
                            & key & "file_name LIKE '%si_recording.pkl'").fetch1("file")
            recording_file = Path(recording_file)
        except dj.DataJointError:
            print(f"\nERROR: Could not find recording file!")
            return
    
    print(f"\nRecording file: {recording_file}")
    
    # Load recording
    print("\n" + "="*70)
    print("1. LOADING PREPROCESSED RECORDING")
    print("="*70)
    try:
        si_recording = si.load(recording_file, base_folder=output_dir)
        print("✓ Successfully loaded")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Basic info
    print(f"\nRecording Properties:")
    print(f"  Channels: {si_recording.get_num_channels()}")
    print(f"  Samples: {si_recording.get_num_samples():,}")
    print(f"  Duration: {si_recording.get_num_samples() / si_recording.get_sampling_frequency():.2f} seconds")
    print(f"  Sampling rate: {si_recording.get_sampling_frequency()} Hz")
    
    # Check data
    print("\n" + "="*70)
    print("2. CHECKING DATA STATISTICS")
    print("="*70)
    try:
        # Sample 100k samples from middle of recording
        num_samples = si_recording.get_num_samples()
        start = num_samples // 4
        end = min(start + 100000, num_samples)
        
        traces = si_recording.get_traces(start_frame=start, end_frame=end)
        print(f"\nSampled {end-start:,} samples (from {start:,} to {end:,})")
        print(f"Data shape: {traces.shape}, dtype: {traces.dtype}")
        
        print(f"\nStatistics:")
        print(f"  Mean: {np.mean(traces):.2f}")
        print(f"  Std: {np.std(traces):.2f}")
        print(f"  Min: {np.min(traces):.2f}")
        print(f"  Max: {np.max(traces):.2f}")
        print(f"  Median: {np.median(traces):.2f}")
        
        # Check for issues
        zero_pct = 100 * np.sum(traces == 0) / traces.size
        print(f"  Zeros: {zero_pct:.2f}%")
        
        channel_stds = np.std(traces, axis=0)
        dead_channels = np.sum(channel_stds < 1e-6)
        if dead_channels > 0:
            print(f"\n  ⚠ WARNING: {dead_channels} channels have near-zero std (dead channels?)")
        
        if np.std(traces) < 1:
            print(f"\n  ⚠ WARNING: Very low overall std ({np.std(traces):.2f}) - data may be corrupted!")
        
        if zero_pct > 50:
            print(f"\n  ⚠ WARNING: High percentage of zeros ({zero_pct:.2f}%) - data may be corrupted!")
            
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Check binary file
    print("\n" + "="*70)
    print("3. CHECKING BINARY FILE")
    print("="*70)
    binary_file_path = recording_file.parent / "recording.dat"
    print(f"\nBinary file: {binary_file_path}")
    
    if not binary_file_path.exists():
        print("✗ ERROR: Binary file does not exist!")
        return
    
    file_size = binary_file_path.stat().st_size
    expected_size = si_recording.get_num_samples() * si_recording.get_num_channels() * 2
    print(f"File size: {file_size:,} bytes ({file_size / 1e9:.2f} GB)")
    print(f"Expected size: {expected_size:,} bytes ({expected_size / 1e9:.2f} GB)")
    
    if abs(file_size - expected_size) > 1000:
        print(f"⚠ WARNING: Size mismatch! Difference: {abs(file_size - expected_size):,} bytes")
    else:
        print("✓ File size matches expected")
    
    # Check dtype mismatch bug
    print("\n" + "="*70)
    print("4. CHECKING FOR DTYPE MISMATCH BUG")
    print("="*70)
    print("\n⚠ POTENTIAL BUG DETECTED:")
    print("  Binary file is written as 'int16' but read as 'uint16' in load_and_verify_binary_file()")
    print("  This could cause data corruption!")
    
    print("\nTesting both dtypes...")
    
    # Read as int16 (how it was written)
    try:
        binary_int16 = se.read_binary(
            binary_file_path,
            sampling_frequency=si_recording.get_sampling_frequency(),
            dtype=np.int16,
            num_channels=si_recording.get_num_channels(),
            gain_to_uV=si_recording.get_channel_gains()[0] if len(si_recording.get_channel_gains()) > 0 else 1.0
        )
        sample_int16 = binary_int16.get_traces(start_frame=start, end_frame=end)
        print(f"  ✓ Read as int16: mean={np.mean(sample_int16):.2f}, std={np.std(sample_int16):.2f}")
    except Exception as e:
        print(f"  ✗ Error reading as int16: {e}")
        sample_int16 = None
    
    # Read as uint16 (how load_and_verify_binary_file reads it)
    try:
        binary_uint16 = se.read_binary(
            binary_file_path,
            sampling_frequency=si_recording.get_sampling_frequency(),
            dtype=np.uint16,
            num_channels=si_recording.get_num_channels(),
            gain_to_uV=si_recording.get_channel_gains()[0] if len(si_recording.get_channel_gains()) > 0 else 1.0
        )
        sample_uint16 = binary_uint16.get_traces(start_frame=start, end_frame=end)
        print(f"  ✓ Read as uint16: mean={np.mean(sample_uint16):.2f}, std={np.std(sample_uint16):.2f}")
    except Exception as e:
        print(f"  ✗ Error reading as uint16: {e}")
        sample_uint16 = None
    
    # Compare
    if sample_int16 is not None and sample_uint16 is not None:
        diff = np.abs(sample_int16 - sample_uint16)
        mean_diff = np.mean(diff)
        max_diff = np.max(diff)
        print(f"\n  Comparison:")
        print(f"    Mean absolute difference: {mean_diff:.2f}")
        print(f"    Max absolute difference: {max_diff:.2f}")
        
        if mean_diff > 100:
            print(f"\n  ⚠⚠⚠ CRITICAL: Large difference detected!")
            print(f"     This dtype mismatch is likely corrupting your data!")
            print(f"     Kilosort4 is reading corrupted data, which could explain")
            print(f"     why no spikes are detected!")
        else:
            print(f"  ✓ Differences are small (likely just interpretation differences)")
    
    # Compare binary with recording
    print("\n" + "="*70)
    print("5. COMPARING BINARY FILE WITH RECORDING")
    print("="*70)
    
    if sample_int16 is not None:
        if traces.shape == sample_int16.shape:
            diff = np.abs(traces - sample_int16)
            print(f"\nRecording vs Binary (int16):")
            print(f"  Mean absolute difference: {np.mean(diff):.2f}")
            print(f"  Max absolute difference: {np.max(diff):.2f}")
            
            if np.mean(diff) > 100:
                print(f"\n  ⚠ WARNING: Large differences between recording and binary file!")
            else:
                print(f"  ✓ Recording and binary file match well")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("\nNext steps:")
    print("1. If you see dtype mismatch issues, fix load_and_verify_binary_file()")
    print("2. If data statistics look wrong, check preprocessing pipeline")
    print("3. If binary file doesn't match recording, check write_binary_recording()")
    print("4. If everything looks fine, the issue may be Kilosort4 parameters")


if __name__ == "__main__":
    main()

