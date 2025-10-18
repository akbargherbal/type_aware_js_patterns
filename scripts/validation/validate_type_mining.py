"""
Validate Type-Aware Pattern Mining Pipeline (Session 3, Task 4)

End-to-end validation of the complete pipeline:
- RepoCloner → TypeTransformer → PatternExtractor → StateManager

Tests on a small sample (1-3 repos) to verify:
1. All components integrate correctly
2. New state_manager columns work properly
3. Pattern schema matches expectations
4. Stats are tracked correctly
"""

import sys
from pathlib import Path
import time
import pandas as pd
import yaml
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.type_pattern_analyzer.orchestrator import Orchestrator
from src.type_pattern_analyzer.state_manager import StateManager


def print_header(title: str):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"🔍 {title}")
    print("=" * 70)


def print_result(label: str, value, status: str = "info"):
    """Print formatted result line"""
    icons = {"pass": "✅", "fail": "❌", "warn": "⚠️", "info": "ℹ️"}
    icon = icons.get(status, "•")
    print(f"{icon} {label}: {value}")


def validate_config():
    """Validate configuration is set up for testing"""
    print_header("Validating Configuration")
    
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print_result("config.yaml", "NOT FOUND", "fail")
        return False
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Check critical settings
    checks = {
        "enable_type_inference": config.get("enable_type_inference", False),
        "patterns_dir": config.get("patterns_dir"),
        "repo_queue_file": config.get("repo_queue_file"),
        "type_coverage_threshold": config.get("type_coverage_threshold", 30),
    }
    
    all_passed = True
    for key, value in checks.items():
        if value:
            print_result(key, value, "pass")
        else:
            print_result(key, "NOT SET", "fail")
            all_passed = False
    
    return all_passed


def create_test_queue(state: StateManager, num_repos: int = 3):
    """Create a minimal test queue with first N repos"""
    print_header(f"Creating Test Queue ({num_repos} repos)")
    
    # Load original repo links
    repo_links_file = project_root / "data" / "DF_REPO_LINKS.pkl"
    if not repo_links_file.exists():
        print_result("DF_REPO_LINKS.pkl", "NOT FOUND", "fail")
        return False
    
    df_links = pd.read_pickle(repo_links_file)
    print_result("Total repos available", len(df_links), "info")
    
    # Take first N repos
    df_sample = df_links.head(num_repos).copy()
    
    # Extract repo names
    def extract_name(url):
        parts = url.rstrip(".git").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return url
    
    # Create test queue
    df_queue = pd.DataFrame({
        "repo_id": range(1, len(df_sample) + 1),
        "url": df_sample["REPO"].values,
        "name": df_sample["REPO"].apply(extract_name).values,
        "status": "pending",
        "attempt_count": 0,
        "last_attempt": pd.NaT,
        # Type transformation stats
        "type_coverage_pct": pd.NA,
        "typed_files_count": pd.NA,
        "transform_errors": pd.NA,
        # Mining stats
        "files_processed": pd.NA,
        "files_skipped": pd.NA,
        "parse_errors": pd.NA,
        "skip_reasons_json": None,
        # Aggregated stats
        "patterns_extracted": pd.NA,
        "total_frequency": pd.NA,
        "analysis_duration_sec": pd.NA,
        "error_message": None,
        "checkpoint_batch": pd.NA,
    })
    
    # Save test queue
    state.save_queue(df_queue)
    
    print_result("Test queue created", f"{len(df_queue)} repos", "pass")
    for idx, row in df_queue.iterrows():
        print(f"   {row['repo_id']}. {row['name']}")
    
    return True


def run_pipeline_test(max_repos: int = 3):
    """Run the orchestrator on test repos"""
    print_header(f"Running Pipeline Test ({max_repos} repos)")
    
    # Temporarily override max_repos in config
    config_path = project_root / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    original_max = config.get("max_repos")
    config["max_repos"] = max_repos
    
    # Write temporary config
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    
    try:
        print(f"⚙️  Starting orchestrator (max_repos={max_repos})...")
        start_time = time.time()
        
        orchestrator = Orchestrator(str(config_path))
        orchestrator.run()
        
        duration = time.time() - start_time
        print_result("Pipeline execution", f"{duration:.2f}s", "pass")
        
        return True
        
    except Exception as e:
        print_result("Pipeline execution", f"FAILED: {e}", "fail")
        return False
        
    finally:
        # Restore original config
        config["max_repos"] = original_max
        with open(config_path, "w") as f:
            yaml.dump(config, f)


def validate_queue_state(state: StateManager):
    """Validate the queue state after processing"""
    print_header("Validating Queue State")
    
    df_queue = state.load_queue()
    
    # Check status distribution
    status_counts = df_queue["status"].value_counts().to_dict()
    print("\n📊 Status Distribution:")
    for status, count in status_counts.items():
        print(f"   {status}: {count}")
    
    # Check completed repos
    completed = df_queue[df_queue["status"] == "completed"]
    print(f"\n✅ Completed Repos: {len(completed)}")
    
    if len(completed) == 0:
        print_result("Completed repos", "NONE", "fail")
        return False
    
    # Validate new columns have data
    print("\n🔍 Validating New Columns:")
    
    checks = {
        "type_coverage_pct": completed["type_coverage_pct"].notna().all(),
        "typed_files_count": completed["typed_files_count"].notna().all(),
        "transform_errors": completed["transform_errors"].notna().all(),
    }
    
    all_passed = True
    for col, has_data in checks.items():
        if has_data:
            print_result(col, "HAS DATA", "pass")
            # Show sample values
            sample_val = completed[col].iloc[0]
            print(f"      Sample value: {sample_val}")
        else:
            print_result(col, "MISSING DATA", "fail")
            all_passed = False
    
    # Show detailed stats for first completed repo
    if len(completed) > 0:
        print("\n📋 Sample Repo Stats (First Completed):")
        first = completed.iloc[0]
        print(f"   Repo: {first['name']}")
        print(f"   Type Coverage: {first['type_coverage_pct']:.1f}%")
        print(f"   Typed Files: {first['typed_files_count']}")
        print(f"   Transform Errors: {first['transform_errors']}")
        print(f"   Patterns Extracted: {first['patterns_extracted']}")
        print(f"   Total Frequency: {first['total_frequency']}")
        print(f"   Duration: {first['analysis_duration_sec']:.2f}s")
    
    return all_passed


def validate_pattern_files(state: StateManager):
    """Validate pattern files were created and have correct schema"""
    print_header("Validating Pattern Files")
    
    patterns_dir = Path(state.config["patterns_dir"])
    
    if not patterns_dir.exists():
        print_result("Patterns directory", "NOT FOUND", "fail")
        return False
    
    pattern_files = list(patterns_dir.glob("repo_*.pkl"))
    print_result("Pattern files found", len(pattern_files), "info")
    
    if len(pattern_files) == 0:
        print_result("Pattern files", "NONE CREATED", "fail")
        return False
    
    # Validate schema of first file
    print("\n🔍 Validating Pattern Schema:")
    first_file = pattern_files[0]
    print(f"   Checking: {first_file.name}")
    
    df_patterns = pd.read_pickle(first_file)
    print_result("Rows in DataFrame", len(df_patterns), "info")
    
    # Check required columns
    required_cols = [
        "pattern_hash",
        "typed_signature",
        "base_type",
        "method",
        "abstract_signature",
        "semantic_signature",
        "node_type",
        "category",
        "frequency",
        "examples_json",
    ]
    
    missing_cols = [col for col in required_cols if col not in df_patterns.columns]
    
    if missing_cols:
        print_result("Schema validation", f"MISSING COLUMNS: {missing_cols}", "fail")
        return False
    else:
        print_result("Schema validation", "ALL COLUMNS PRESENT", "pass")
    
    # Show sample pattern
    if len(df_patterns) > 0:
        print("\n📋 Sample Pattern:")
        sample = df_patterns.iloc[0]
        print(f"   Typed Signature: {sample['typed_signature']}")
        print(f"   Base Type: {sample['base_type']}")
        print(f"   Method: {sample['method']}")
        print(f"   Category: {sample['category']}")
        print(f"   Frequency: {sample['frequency']}")
        
        # Validate examples_json is valid JSON
        try:
            examples = json.loads(sample['examples_json'])
            print_result("examples_json format", f"VALID ({len(examples)} examples)", "pass")
        except:
            print_result("examples_json format", "INVALID JSON", "fail")
            return False
    
    return True


def validate_transform_stats(state: StateManager):
    """Validate type transformation statistics summary"""
    print_header("Validating Transform Statistics Summary")
    
    try:
        stats = state.get_transform_stats_summary()
        
        print("\n📊 Aggregate Transform Stats:")
        print(f"   Repos Completed: {stats['repos_completed']}")
        print(f"   Avg Type Coverage: {stats['avg_type_coverage_pct']:.1f}%")
        print(f"   Median Type Coverage: {stats['median_type_coverage_pct']:.1f}%")
        print(f"   Total Typed Files: {stats['total_typed_files']}")
        print(f"   Total Transform Errors: {stats['total_transform_errors']}")
        print(f"   Repos Below Threshold ({stats['threshold_pct']}%): {stats['repos_below_threshold']}")
        
        # Validate stats make sense
        if stats['repos_completed'] > 0:
            print_result("Transform stats", "VALID", "pass")
            return True
        else:
            print_result("Transform stats", "NO DATA", "fail")
            return False
            
    except Exception as e:
        print_result("Transform stats", f"ERROR: {e}", "fail")
        return False


def generate_validation_report(all_results: dict):
    """Generate final validation report"""
    print_header("VALIDATION REPORT")
    
    print("\n📋 Test Results:")
    total_tests = len(all_results)
    passed_tests = sum(1 for v in all_results.values() if v)
    
    for test_name, passed in all_results.items():
        status = "pass" if passed else "fail"
        print_result(test_name, "PASS" if passed else "FAIL", status)
    
    print(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n" + "=" * 70)
        print("✅ ALL VALIDATION TESTS PASSED!")
        print("=" * 70)
        print("\n🎉 Pipeline is ready for Task 5: Test on 5-10 repos")
        print("\nNext steps:")
        print("  1. Review results in data/typed_patterns_by_repo/")
        print("  2. Run orchestrator on 5-10 repos")
        print("  3. Proceed to Session 4: Aggregation")
        return True
    else:
        print("\n" + "=" * 70)
        print("❌ VALIDATION FAILED")
        print("=" * 70)
        print("\nPlease fix the issues above before proceeding.")
        return False


def main():
    """Main validation flow"""
    print("=" * 70)
    print("🧪 TYPE-AWARE PATTERN MINING - END-TO-END VALIDATION")
    print("=" * 70)
    print(f"\nProject Root: {project_root}")
    print("Platform: Windows" if sys.platform == "win32" else "Platform: Unix-like")
    
    # Initialize state manager
    state = StateManager(str(project_root / "config.yaml"))
    
    # Test configuration
    num_test_repos = 2  # Start with 2 repos for quick validation
    
    results = {}
    
    # Step 1: Validate config
    results["Config Validation"] = validate_config()
    if not results["Config Validation"]:
        print("\n❌ Config validation failed. Cannot proceed.")
        return False
    
    # Step 2: Create test queue
    results["Test Queue Creation"] = create_test_queue(state, num_test_repos)
    if not results["Test Queue Creation"]:
        print("\n❌ Failed to create test queue. Cannot proceed.")
        return False
    
    # Step 3: Run pipeline
    print("\n⚠️  WARNING: This will process real repositories and may take several minutes.")
    response = input("Proceed with pipeline test? (y/N): ").strip().lower()
    
    if response != 'y':
        print("\n❌ Validation cancelled by user.")
        return False
    
    results["Pipeline Execution"] = run_pipeline_test(num_test_repos)
    if not results["Pipeline Execution"]:
        print("\n❌ Pipeline execution failed.")
        # Continue to validate what we can
    
    # Step 4: Validate queue state
    results["Queue State Validation"] = validate_queue_state(state)
    
    # Step 5: Validate pattern files
    results["Pattern Files Validation"] = validate_pattern_files(state)
    
    # Step 6: Validate transform stats
    results["Transform Stats Validation"] = validate_transform_stats(state)
    
    # Step 7: Generate report
    success = generate_validation_report(results)
    
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Validation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
