# Setting Up Cursor/VS Code with Conda Environment

This guide explains how to configure Cursor (or VS Code) to use a conda environment for running and debugging Python scripts, especially on HPC systems where system Python has restrictions.

## Problem

When running Python scripts in Cursor, you may encounter errors like:
- `ModuleNotFoundError: No module named 'probeinterface'`
- `error: externally-managed-environment` when trying to install packages
- Scripts running with system Python instead of your conda environment

This happens because Cursor needs to be explicitly told which Python interpreter to use.

## Solution

### Step 1: Create/Activate Your Conda Environment

```bash
# Load miniconda module (if on HPC)
module load miniconda/23.10.0

# Initialize conda
source "$(conda info --base)/etc/profile.d/conda.sh"

# Create a new conda environment (if needed)
conda create -n your_env_name python=3.11

# Activate the environment
conda activate your_env_name

# Install your project with optional dependencies
cd /path/to/your/project
pip install -e ".[your_optional_deps]"
```

**Note:** Use Python 3.11 (not 3.12) if you have dependencies like `numba` that don't support Python 3.12 yet.

### Step 2: Get the Python Interpreter Path

Find the full path to your conda Python interpreter:

```bash
# With conda activated
which python
# Should output something like: /nfs/nhome/live/username/.conda/envs/env_name/bin/python
```

Or:

```bash
conda activate your_env_name
python -c "import sys; print(sys.executable)"
```

### Step 3: Configure Cursor/VS Code

Create `.vscode/settings.json` in your project root with the following content:

```json
{
    "python.defaultInterpreterPath": "/full/path/to/your/conda/env/bin/python",
    "python.terminal.activateEnvironment": true,
    "python.terminal.activateEnvInCurrentTerminal": true,
    "terminal.integrated.env.linux": {
        "PATH": "/full/path/to/your/conda/env/bin:${env:PATH}"
    },
    "python.analysis.extraPaths": [
        "${workspaceFolder}"
    ]
}
```

**Replace** `/full/path/to/your/conda/env/bin/python` with the actual path from Step 2.

### Step 4: Configure Debug Settings (Optional but Recommended)

Create `.vscode/launch.json` in your project root:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "justMyCode": true,
            "python": "/full/path/to/your/conda/env/bin/python"
        }
    ]
}
```

**Replace** `/full/path/to/your/conda/env/bin/python` with the actual path from Step 2.

### Step 5: Manually Select the Interpreter in Cursor

Even with `settings.json` configured, you should manually verify/select the interpreter:

1. **Check the bottom-right corner** of Cursor - it should show your Python version
2. If it doesn't show the conda Python:
   - Click on the Python version in the bottom-right, OR
   - Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
   - Type "Python: Select Interpreter"
   - Choose your conda environment Python (should show path and "conda" label)

### Step 6: Verify It's Working

Add these debug lines at the top of your Python script:

```python
import sys
print(f"DEBUG: Python interpreter: {sys.executable}")
print(f"DEBUG: Python version: {sys.version}")
```

When you run the script, verify:
- `DEBUG: Python interpreter:` should show your conda path
- `DEBUG: Python version:` should show Python 3.11.x (or whatever version you installed)

You can also test importing a package that's only in your conda environment:

```python
import probeinterface  # or whatever package you need
print("SUCCESS: Package imported from conda environment")
```

## Troubleshooting

### Issue: Still getting `ModuleNotFoundError` after setup

**Check:**
1. Is the package installed in the conda environment?
   ```bash
   conda activate your_env_name
   python -c "import probeinterface; print('OK')"
   ```

2. Is Cursor using the correct interpreter?
   - Look at the bottom-right corner of Cursor
   - Check the debug output from your script
   - Manually select the interpreter again (Step 5)

3. Did you reload Cursor after changing `settings.json`?
   - Close and reopen Cursor, OR
   - Press `Ctrl+Shift+P` → "Developer: Reload Window"

### Issue: `error: externally-managed-environment` when installing packages

**Cause:** You're trying to install into system Python, not your conda environment.

**Solution:**
1. Make sure conda is activated: `conda activate your_env_name`
2. Verify you're using conda Python: `which python` should show conda path
3. Install packages: `pip install package_name` (should now work)

### Issue: Cursor can't find the conda interpreter in the selection menu

**Solution:**
1. Make sure conda is initialized in your shell
2. In Cursor's terminal, manually activate conda:
   ```bash
   source "$(conda info --base)/etc/profile.d/conda.sh"
   conda activate your_env_name
   ```
3. Then select the interpreter - it should now appear in the list

### Issue: Settings aren't being picked up

**Check:**
1. Is `.vscode/settings.json` in the project root? (not in a subdirectory)
2. Did you use the full absolute path (not a relative path)?
3. Try reloading Cursor (`Ctrl+Shift+P` → "Developer: Reload Window")
4. Try manually selecting the interpreter (Step 5)

### Issue: On HPC, need to load modules before running scripts

If your conda requires modules to be loaded (e.g., `module load miniconda/23.10.0`), you may need to:

1. **For terminal execution:** Run this before executing your script:
   ```bash
   module load miniconda/23.10.0
   source "$(conda info --base)/etc/profile.d/conda.sh"
   conda activate your_env_name
   python your_script.py
   ```

2. **For Cursor debugger:** The debugger may not load modules automatically. You might need to:
   - Use the integrated terminal to run scripts instead of the debugger, OR
   - Create a wrapper script that loads modules and runs your script

## Quick Reference

**Most Important Steps:**
1. Get conda Python path: `conda activate env && which python`
2. Add path to `.vscode/settings.json`
3. Manually select interpreter in Cursor (bottom-right)
4. Verify with debug output in your script

**Files to Create:**
- `.vscode/settings.json` - Python interpreter configuration
- `.vscode/launch.json` - Debug configuration (optional)

**Commands to Remember:**
```bash
# Activate conda
conda activate your_env_name

# Find Python path
which python

# Verify package installation
python -c "import package_name; print('OK')"

# Install project with extras
pip install -e ".[optional_deps]"
```

## Example: Complete Setup for New Project

```bash
# 1. Create conda environment
module load miniconda/23.10.0
source "$(conda info --base)/etc/profile.d/conda.sh"
conda create -n myproject python=3.11
conda activate myproject

# 2. Navigate to project
cd /path/to/myproject

# 3. Install project with optional dependencies
pip install -e ".[spike_sorting]"

# 4. Get Python path
which python
# Output: /nfs/nhome/live/username/.conda/envs/myproject/bin/python

# 5. Create .vscode/settings.json with that path
# (see Step 3 above)

# 6. Open Cursor and select the interpreter (bottom-right)

# 7. Add debug lines to script and verify it's using conda Python
```

