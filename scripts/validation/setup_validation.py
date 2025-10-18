"""
Foundation Validation Script - Updated for Local Repository Workflow
Checks that all configuration and dependencies are correctly set up.
"""

import sys
from pathlib import Path
import subprocess
import importlib
import platform
import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def check_python_dependencies():
    """Check that all Python dependencies are installed"""
    print("\n" + "=" * 70)
    print("🐍 Checking Python Dependencies")
    print("=" * 70)
    # ... (This function remains unchanged)
    required = {"pandas": "2.0.0", "numpy": "1.24.0", "yaml": "6.0"}
    all_ok = True
    for module_name, min_version in required.items():
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {module_name:20s} {version}")
        except ImportError:
            print(f"❌ {module_name:20s} NOT INSTALLED (required)")
            all_ok = False
    return all_ok


def check_node_environment():
    """Check Node.js and TypeScript setup"""
    print("\n" + "=" * 70)
    print("📦 Checking Node.js Environment")
    print("=" * 70)
    # ... (This function remains unchanged)
    is_windows = platform.system() == "Windows"
    checks = {"node": ["node", "--version"], "npm": ["npm", "--version"], "ts-node": ["ts-node", "--version"]}
    all_ok = True
    for name, cmd in checks.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, shell=is_windows)
            if result.returncode == 0:
                print(f"✅ {name:20s} {result.stdout.strip()}")
            else:
                print(f"❌ {name:20s} command failed")
                all_ok = False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"❌ {name:20s} NOT FOUND")
            all_ok = False
    return all_ok


def check_config_files():
    """Check that configuration files exist and are valid for local processing."""
    print("\n" + "=" * 70)
    print("⚙️  Checking Configuration Files")
    print("=" * 70)
    all_ok = True
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            # UPDATED: Check for the new required key
            required_keys = ["local_repos_dir", "patterns_dir", "ts_script_path"]
            missing = [k for k in required_keys if k not in config]
            if missing:
                print(f"❌ config.yaml missing keys: {missing}")
                all_ok = False
            else:
                print(f"✅ config.yaml (valid, {len(config)} settings)")
        except Exception as e:
            print(f"❌ config.yaml error: {e}")
            all_ok = False
    else:
        print("❌ config.yaml NOT FOUND")
        all_ok = False
    # ... (package.json and requirements.txt checks remain the same)
    return all_ok


def check_input_data():
    """Check if the local_repos_dir is configured and valid."""
    print("\n" + "=" * 70)
    print("📊 Checking Input Data (Local Repositories)")
    print("=" * 70)
    config_path = PROJECT_ROOT / "config.yaml"
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        local_dir_str = config.get("local_repos_dir")
        if not local_dir_str:
            print("❌ `local_repos_dir` is not set in config.yaml")
            return False
            
        local_dir = Path(local_dir_str)
        print(f"   Configured path: {local_dir}")

        if not local_dir.exists():
            print(f"❌ Directory NOT FOUND: {local_dir}")
            return False
        
        if not local_dir.is_dir():
            print(f"❌ Path is not a directory: {local_dir}")
            return False

        # Check for at least one subdirectory
        subdirs = [d for d in local_dir.iterdir() if d.is_dir()]
        if not subdirs:
            print(f"⚠️  No repository subdirectories found in {local_dir}")
            print("   The directory is empty or contains only files.")
            return False # Treat as failure since there's nothing to process

        print(f"✅ Found {len(subdirs)} potential repositories.")
        print(f"   First repo found: {subdirs[0].name}")
        return True

    except Exception as e:
        print(f"❌ Error checking input data: {e}")
        return False


def main():
    """Run all validation checks"""
    print("\n" + "=" * 70)
    print("🔍 TYPE-AWARE PATTERN MINING - FOUNDATION VALIDATION")
    print("=" * 70)
    
    checks = [
        ("Python Dependencies", check_python_dependencies),
        ("Node.js Environment", check_node_environment),
        ("Configuration Files", check_config_files),
        ("Input Data", check_input_data),
    ]

    results = {}
    for name, check_func in checks:
        results[name] = check_func()

    print("\n" + "=" * 70)
    print("📋 VALIDATION SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10s} {name}")

    all_passed = all(results.values())
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Ready to run the pipeline!")
    else:
        print("❌ SOME CHECKS FAILED - Please fix the issues above.")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())