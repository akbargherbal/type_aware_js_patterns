"""
Foundation Validation Script - Fixed for Windows
Checks that all configuration and dependencies are correctly set up
Run this after completing Session 1 setup
"""

import sys
from pathlib import Path
import subprocess
import importlib
import platform

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def check_python_dependencies():
    """Check that all Python dependencies are installed"""
    print("\n" + "=" * 70)
    print("🐍 Checking Python Dependencies")
    print("=" * 70)

    required = {
        "pandas": "2.0.0",
        "numpy": "1.24.0",
        "yaml": "6.0",  # PyYAML imports as 'yaml'
    }

    optional = {
        "joblib": "1.3.0",
        "pyarrow": "12.0.0",
        "tqdm": "4.66.0",
    }

    all_ok = True

    for module_name, min_version in required.items():
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {module_name:20s} {version}")
        except ImportError:
            print(f"❌ {module_name:20s} NOT INSTALLED (required)")
            all_ok = False

    print("\nOptional dependencies:")
    for module_name, min_version in optional.items():
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {module_name:20s} {version}")
        except ImportError:
            print(f"⚠️  {module_name:20s} not installed (optional)")

    return all_ok


def check_node_environment():
    """Check Node.js and TypeScript setup - Windows compatible"""
    print("\n" + "=" * 70)
    print("📦 Checking Node.js Environment")
    print("=" * 70)

    is_windows = platform.system() == "Windows"

    checks = {
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "ts-node": ["ts-node", "--version"],
    }

    all_ok = True

    for name, cmd in checks.items():
        try:
            # On Windows, we need shell=True for npm/ts-node
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                shell=is_windows,  # This fixes Windows detection
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"✅ {name:20s} {version}")
            else:
                print(f"❌ {name:20s} command failed")
                all_ok = False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"❌ {name:20s} NOT FOUND")
            all_ok = False

    return all_ok


def check_directory_structure():
    """Check that all required directories exist"""
    print("\n" + "=" * 70)
    print("📁 Checking Directory Structure")
    print("=" * 70)

    required_dirs = [
        "data",
        "results",
        "temp",
        "logs",
        "src/type_pattern_analyzer",
        "src/type_pattern_analyzer/ts_scripts",
        "scripts/setup",
        "scripts/validation",
    ]

    all_ok = True

    for dir_path in required_dirs:
        full_path = PROJECT_ROOT / dir_path
        if full_path.exists():
            print(f"✅ {dir_path}")
        else:
            print(f"❌ {dir_path} MISSING")
            all_ok = False

    return all_ok


def check_config_files():
    """Check that configuration files exist and are valid"""
    print("\n" + "=" * 70)
    print("⚙️  Checking Configuration Files")
    print("=" * 70)

    all_ok = True

    # Check config.yaml
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f)

            required_keys = [
                "data_dir",
                "patterns_dir",
                "temp_dir",
                "enable_type_inference",
                "type_coverage_threshold",
                "ts_script_path",
                "min_pattern_frequency",
            ]

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

    # Check package.json
    package_path = PROJECT_ROOT / "package.json"
    if package_path.exists():
        try:
            import json

            with open(package_path) as f:
                package = json.load(f)

            if "typescript" in package.get("dependencies", {}):
                print(f"✅ package.json (has TypeScript)")
            else:
                print(f"⚠️  package.json missing TypeScript dependency")
        except Exception as e:
            print(f"❌ package.json error: {e}")
            all_ok = False
    else:
        print("❌ package.json NOT FOUND")
        all_ok = False

    # Check requirements.txt
    req_path = PROJECT_ROOT / "requirements.txt"
    if req_path.exists():
        print(f"✅ requirements.txt ({req_path.stat().st_size} bytes)")
    else:
        print("❌ requirements.txt NOT FOUND")
        all_ok = False

    return all_ok


def check_typescript_scripts():
    """Check that TypeScript POC scripts exist"""
    print("\n" + "=" * 70)
    print("📜 Checking TypeScript Scripts")
    print("=" * 70)

    required_scripts = [
        "src/type_pattern_analyzer/ts_scripts/type_transform_poc.ts",
        "src/type_pattern_analyzer/ts_scripts/poc_validation.ts",
    ]

    all_ok = True

    for script_path in required_scripts:
        full_path = PROJECT_ROOT / script_path
        if full_path.exists():
            size_kb = full_path.stat().st_size / 1024
            print(f"✅ {script_path} ({size_kb:.1f} KB)")
        else:
            print(f"❌ {script_path} MISSING")
            all_ok = False

    return all_ok


def check_input_data():
    """Check if DF_REPO_LINKS.pkl exists"""
    print("\n" + "=" * 70)
    print("📊 Checking Input Data")
    print("=" * 70)

    input_file = PROJECT_ROOT / "data" / "DF_REPO_LINKS.pkl"

    if input_file.exists():
        try:
            import pandas as pd

            df = pd.read_pickle(input_file)
            if "REPO" in df.columns:
                print(f"✅ DF_REPO_LINKS.pkl ({len(df)} repositories)")
                print(f"   First repo: {df['REPO'].iloc[0]}")
                return True
            else:
                print(f"❌ DF_REPO_LINKS.pkl missing 'REPO' column")
                return False
        except Exception as e:
            print(f"❌ DF_REPO_LINKS.pkl error: {e}")
            return False
    else:
        print(f"⚠️  DF_REPO_LINKS.pkl NOT FOUND")
        print(f"   Run: python scripts/setup/setup_repo_links.py")
        return False


def main():
    """Run all validation checks"""
    print("\n" + "=" * 70)
    print("🔍 TYPE-AWARE PATTERN MINING - FOUNDATION VALIDATION")
    print("=" * 70)
    print(f"\nProject Root: {PROJECT_ROOT}")
    print(f"Platform: {platform.system()} {platform.release()}")

    checks = [
        ("Python Dependencies", check_python_dependencies),
        ("Node.js Environment", check_node_environment),
        ("Directory Structure", check_directory_structure),
        ("Configuration Files", check_config_files),
        ("TypeScript Scripts", check_typescript_scripts),
        ("Input Data", check_input_data),
    ]

    results = {}
    for name, check_func in checks:
        results[name] = check_func()

    # Summary
    print("\n" + "=" * 70)
    print("📋 VALIDATION SUMMARY")
    print("=" * 70)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10s} {name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Ready to proceed!")
        print("=" * 70)
        print("\n🚀 SESSION 1 COMPLETE!")
        print("\nNext Steps (Session 2):")
        print("  1. Build type_transformer.py")
        print("  2. Test transformation on sample repos")
        print("  3. Validate type coverage statistics")
    else:
        print("❌ SOME CHECKS FAILED - Please fix issues above")
        print("=" * 70)
        print("\nTroubleshooting:")
        print("  - Missing directories: mkdir temp && mkdir logs")
        print("  - Python deps: pip install -r requirements.txt")
        print("  - Node deps: npm install")
        print("  - Input data: python scripts/setup/setup_repo_links.py")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
