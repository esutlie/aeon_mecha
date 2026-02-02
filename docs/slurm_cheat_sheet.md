# SLURM Cheat Sheet for AEON Spike Sorting

A quick reference guide for monitoring and troubleshooting the AEON spike sorting job running via `run_aeon_spike_sorting.sh`.

## Connecting to the HPC

Before you can submit or monitor jobs, you need to connect to the HPC:

1. **Open PowerShell** (or your preferred terminal)

2. **Connect to the HPC**:
   ```powershell
   ssh aeon-hpc
   ```

3. **Enter your password** (you will be prompted twice)

4. **Navigate to the project directory**:
   ```bash
   cd ProjectAeon/aeon_mecha
   ```

After connecting and navigating to the directory, you can proceed with submitting and monitoring jobs.

## Job Submission

```bash
# Submit the spike sorting job
sbatch run_aeon_spike_sorting.sh

# Submit and capture the job ID
JOBID=$(sbatch run_aeon_spike_sorting.sh | awk '{print $4}')
echo "Job ID: $JOBID"

# Check the job was submitted
squeue -u $USER
```

## Monitoring the Spike Sorting Job

### View Job Status

```bash
# View all your jobs
squeue -u $USER

# View only the spike sorting jobs (job name: aeon-spike-sorting)
squeue -n aeon-spike-sorting

# View specific job by ID
squeue -j <job_id>

# Continuous monitoring (updates every second)
watch -n 1 'squeue -n aeon-spike-sorting'

# View detailed job information
scontrol show job <job_id>
```

### Job Configuration

The spike sorting job uses:
- **Job Name**: `aeon-spike-sorting`
- **Partition**: `gpu` (or `cpu` if modified)
- **GPU**: 1x A100 (for GPU mode)
- **Memory**: 128GB
- **Time Limit**: 7 days, 1 hour (7-01:00:00)
- **Output Directory**: `slurm_output/`

### Job Status Codes

When checking job status with `squeue`:
- `PD` (PENDING) - Waiting for GPU/CPU resources
- `R` (RUNNING) - Currently processing spike sorting
- `CG` (COMPLETING) - Finishing up
- `CD` (COMPLETED) - Successfully completed
- `F` (FAILED) - Job failed (check error log)
- `CA` (CANCELLED) - Job was cancelled
- `TO` (TIMEOUT) - Exceeded 7-day time limit
- `NF` (NODE_FAIL) - Node failure occurred

### Historical Job Information

```bash
# Show accounting information for all your spike sorting jobs
sacct -n aeon-spike-sorting

# Show specific job details including exit code
sacct -j <job_id> --format=JobID,JobName,Partition,State,ExitCode,Start,End,Elapsed,MaxRSS,NodeList

# Show only failed spike sorting jobs
sacct -n aeon-spike-sorting --state=FAILED

# Show all your jobs with resource usage
sacct -u $USER --format=JobID,JobName,State,ExitCode,MaxRSS,Elapsed
```

### Real-time Resource Monitoring

```bash
# Show current resource usage for running job
sstat -j <job_id> --format=JobID,MaxRSS,MaxRSSNode,MaxRSSTask,AveCPU,TotalCPU

# Monitor resource usage continuously (updates every 5 seconds)
watch -n 5 'sstat -j <job_id> --format=JobID,MaxRSS,AveCPU,TotalCPU'

# Check memory usage (job requests 128GB)
sstat -j <job_id> --format=MaxRSS,MaxRSSNode,ReqMem,AllocCPUS
```

## Checking Log Files

### Log File Location and Naming

Log files are located in `slurm_output/` and follow the pattern:
- **Output**: `slurm_output/<NODE_NAME>_<JOB_ID>.out`
- **Error**: `slurm_output/<NODE_NAME>_<JOB_ID>.err`
- **Resource Usage**: `slurm_output/resource_use_<JOB_ID>.csv`

Example: `gpu-sr670-20_2097343.out` (node: `gpu-sr670-20`, job ID: `2097343`)

### View Log Files

```bash
# View full output log
cat slurm_output/<node_name>_<job_id>.out

# View full error log
cat slurm_output/<node_name>_<job_id>.err

# View last 50 lines of output (most recent activity)
tail -n 50 slurm_output/<node_name>_<job_id>.out

# View last 50 lines of error log
tail -n 50 slurm_output/<node_name>_<job_id>.err

# Follow output log in real-time (live monitoring)
tail -f slurm_output/<node_name>_<job_id>.out

# Follow error log in real-time
tail -f slurm_output/<node_name>_<job_id>.err

# Follow both logs simultaneously
tail -f slurm_output/<node_name>_<job_id>.out slurm_output/<node_name>_<job_id>.err
```

### Find Latest Log Files

```bash
# Find most recent output file
ls -t slurm_output/*.out | head -1

# Find most recent error file
ls -t slurm_output/*.err | head -1

# View latest output file (useful after submitting)
tail -f $(ls -t slurm_output/*.out | head -1)

# View latest error file
tail -f $(ls -t slurm_output/*.err | head -1)
```

### Search Log Files for Issues

```bash
# Search for errors in output log
grep -i error slurm_output/<node_name>_<job_id>.out

# Search for errors in error log (most important)
grep -i error slurm_output/<node_name>_<job_id>.err

# Search for Python exceptions/tracebacks
grep -i -E "exception|traceback|error" slurm_output/<node_name>_<job_id>.err

# Search for DataJoint errors
grep -i "datajoint\|ERROR" slurm_output/<node_name>_<job_id>.err

# Search for conda environment issues
grep -i -E "conda|environment|aeon_env" slurm_output/<node_name>_<job_id>.err

# Search for missing module errors
grep -i "ModuleNotFoundError\|ImportError" slurm_output/<node_name>_<job_id>.err

# Search with context (show 10 lines before and after)
grep -i -C 10 error slurm_output/<node_name>_<job_id>.err

# Search all error logs for common issues
grep -i "ERROR\|Exception\|Failed" slurm_output/*.err
```

### Check Resource Profiler Output

The script also creates a CSV file with resource usage over time:

```bash
# View resource usage CSV (if job completed)
cat slurm_output/resource_use_<job_id>.csv

# Check if resource profiler is working (should exist for running jobs)
ls -lht slurm_output/resource_use_*.csv | head -5
```

## Job Control

### Cancel Spike Sorting Jobs

```bash
# Cancel a specific job
scancel <job_id>

# Cancel all spike sorting jobs by name
scancel --name=aeon-spike-sorting

# Cancel all your jobs
scancel -u $USER

# Cancel only pending spike sorting jobs
scancel --name=aeon-spike-sorting -t PENDING
```

### Modify Running Jobs

```bash
# Extend time limit (if job is running and needs more time)
scontrol update job=<job_id> TimeLimit=<new_time_limit>

# Example: Extend to 10 days
scontrol update job=<job_id> TimeLimit=10-00:00:00
```

## Common Issues and Troubleshooting

### Cannot Submit Job - SLURM Temporarily Unable to Accept Job

**Error**: `sbatch: error: Slurm temporarily unable to accept job, sleeping and retrying`

**Cause**: This is a temporary issue with the SLURM controller, typically occurring when:
- The SLURM controller is overloaded or processing many requests
- The SLURM daemon is restarting or updating
- There's a brief network issue between the login node and SLURM controller

**Solution**: 
- **Wait**: `sbatch` will automatically retry the submission (it says "sleeping and retrying")
- Usually resolves within a few seconds to a minute
- The job will be submitted automatically once SLURM is ready
- **Do NOT** keep submitting - let the automatic retry work

```bash
# Check if SLURM is responding
sinfo

# Check SLURM controller status (if you have access)
scontrol show cluster

# If it keeps failing after several minutes, contact your HPC administrator
```

**If it persists**:
- Wait a few minutes and try submitting again
- Check if the cluster is undergoing maintenance
- Contact HPC support if the issue continues

### Job Failed - Check Common Error Patterns

```bash
# View the error log
cat slurm_output/<node_name>_<job_id>.err

# Check exit code
sacct -j <job_id> --format=JobID,State,ExitCode
```

#### Conda Environment Activation Failed

**Error**: `ERROR: Failed to activate conda environment 'aeon_env'`

**Solution**: 
- Check that `aeon_env` conda environment exists
- Verify environment name in the script matches your actual environment

```bash
# Check for this error
grep -i "Failed to activate conda environment" slurm_output/<node_name>_<job_id>.err
```

#### Missing Python Module (e.g., spikeinterface)

**Error**: `ModuleNotFoundError: No module named 'spikeinterface'`

**Cause**: The `aeon_env` conda environment was installed without the `spike_sorting` optional dependencies. The `spikeinterface` module is part of the optional `spike_sorting` extra in `pyproject.toml`.

**Solution**: 
Install the package with the `spike_sorting` extra in the `aeon_env` environment:

```bash
# 1. Connect to HPC (if not already connected)
ssh aeon-hpc

# 2. Navigate to project directory
cd ProjectAeon/aeon_mecha

# 3. Load miniconda module
module load miniconda

# 4. Initialize conda
source "$(conda info --base)/etc/profile.d/conda.sh"

# 5. Activate the aeon_env environment
conda activate aeon_env

# 6. Install the package with spike_sorting dependencies
pip install -e ".[spike_sorting]"

# 7. Verify spikeinterface is installed
python -c "import spikeinterface; print('spikeinterface installed successfully')"
```

**Note**: This will install `spikeinterface[full]`, `spython`, and `cuda-python` as defined in the `spike_sorting` optional dependencies. The installation may take several minutes.

```bash
# Check for missing modules in error logs
grep -i "ModuleNotFoundError\|ImportError" slurm_output/<node_name>_<job_id>.err
```

#### ImportError from swc.aeon.schema (e.g., cannot import name 'Stream')

**Error**: `ImportError: cannot import name 'Stream' from 'swc.aeon.schema'`

**Cause**: The `swc-aeon` package is outdated. Since `swc-aeon` is installed from a git repository, the installed version may not have the latest changes that include required classes like `Stream`.

**Solution**: 
Update the `swc-aeon` package (or reinstall the entire project) to get the latest version:

```bash
# 1. Connect to HPC (if not already connected)
ssh aeon-hpc

# 2. Navigate to project directory
cd ProjectAeon/aeon_mecha

# 3. Load miniconda module
module load miniconda

# 4. Initialize conda
source "$(conda info --base)/etc/profile.d/conda.sh"

# 5. Activate the aeon_env environment
conda activate aeon_env

# Option A: Update just swc-aeon package
pip install --upgrade --force-reinstall "swc-aeon @ git+https://github.com/SainsburyWellcomeCentre/aeon_api.git"

# Option B: Reinstall the entire project (this will also update swc-aeon and other dependencies)
# If you have spike_sorting extras installed:
pip install --upgrade --force-reinstall -e ".[spike_sorting]"
# Or without extras:
pip install --upgrade --force-reinstall -e .

# 6. Verify the import works
python -c "from swc.aeon.schema import Stream; print('Stream imported successfully')"
```

**Note**: If you installed with `spike_sorting` extras, make sure to include them again when reinstalling (`-e ".[spike_sorting]"`).

```bash
# Check for import errors in error logs
grep -i "ImportError.*swc.aeon" slurm_output/<node_name>_<job_id>.err
```

#### Python Script Not Found

**Error**: `ERROR: Python script not found: ./aeon/dj_pipeline/scripts/run_aeon_spike_sorting.py`

**Solution**: 
- Verify the script path is correct
- Check you're running from the project root directory

```bash
# Check for this error
grep -i "Python script not found" slurm_output/<node_name>_<job_id>.err
```

### Job Stuck in PENDING

```bash
# Check why job is pending
scontrol show job <job_id>

# Check GPU partition availability
squeue -p gpu

# Check node availability
sinfo -p gpu
```

The job may be pending because:
- GPU resources are fully allocated
- Waiting for a GPU node to become available
- Other jobs have higher priority

### Monitor Job Progress

The output log shows progress bars for spike sorting:

```bash
# View current progress in output log
tail -n 20 slurm_output/<node_name>_<job_id>.out

# Look for progress indicators like:
# SpikeSorting:  45%|████▌     | 123/274 [01:23<01:45,  1.43it/s]
```

## Useful Aliases and Functions

Add these to your `~/.bashrc` for convenience:

```bash
# View your spike sorting jobs
alias sortjobs='squeue -n aeon-spike-sorting'

# View recent log files
alias sortlogs='ls -lt slurm_output/*.{out,err} | head -10'

# Function to view latest output for spike sorting
viewsortout() {
    LATEST=$(ls -t slurm_output/*.out | head -1)
    if [ -n "$LATEST" ]; then
        echo "Viewing: $LATEST"
        tail -f "$LATEST"
    else
        echo "No output files found in slurm_output/"
    fi
}

# Function to view latest error for spike sorting
viewsorterr() {
    LATEST=$(ls -t slurm_output/*.err | head -1)
    if [ -n "$LATEST" ]; then
        echo "Viewing: $LATEST"
        tail -f "$LATEST"
    else
        echo "No error files found in slurm_output/"
    fi
}

# Function to get spike sorting job details
sortinfo() {
    if [ -z "$1" ]; then
        echo "Usage: sortinfo <job_id>"
        return 1
    fi
    scontrol show job $1
}

# Function to cancel spike sorting job
cancelsort() {
    if [ -z "$1" ]; then
        echo "Usage: cancelsort <job_id>"
        return 1
    fi
    scancel $1
    echo "Cancelled job $1"
}

# Function to check for errors in latest log
checkerrors() {
    LATEST=$(ls -t slurm_output/*.err | head -1)
    if [ -n "$LATEST" ]; then
        echo "Checking: $LATEST"
        grep -i -E "error|exception|failed|ModuleNotFoundError" "$LATEST"
    else
        echo "No error files found"
    fi
}
```

## Quick Reference

### Most Common Commands for Spike Sorting

```bash
# Submit the job
sbatch run_aeon_spike_sorting.sh

# Check job status
squeue -n aeon-spike-sorting

# View latest output log (live)
tail -f $(ls -t slurm_output/*.out | head -1)

# View latest error log (live)
tail -f $(ls -t slurm_output/*.err | head -1)

# Check for errors
grep -i error $(ls -t slurm_output/*.err | head -1)

# Cancel job
scancel <job_id>

# View job history
sacct -n aeon-spike-sorting
```

### Typical Workflow

1. **Submit the job**:
   ```bash
   sbatch run_aeon_spike_sorting.sh
   # Note the job ID from the output
   ```

2. **Monitor job status**:
   ```bash
   squeue -n aeon-spike-sorting
   ```

3. **Watch the output in real-time**:
   ```bash
   tail -f slurm_output/<node_name>_<job_id>.out
   ```

4. **If job fails, check error log**:
   ```bash
   cat slurm_output/<node_name>_<job_id>.err
   grep -i error slurm_output/<node_name>_<job_id>.err
   ```

5. **Check job completion**:
   ```bash
   sacct -j <job_id> --format=JobID,State,ExitCode,Elapsed
   ```

## Additional Resources

- SLURM documentation: https://slurm.schedmd.com/
- `man squeue` - Manual page for squeue
- `man scontrol` - Manual page for scontrol
- `man sacct` - Manual page for sacct
- `man scancel` - Manual page for scancel