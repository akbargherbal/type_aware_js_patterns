"""
Orchestrator - Updated for Type-Aware Pattern Mining (Session 3)
Main controller for the repository processing pipeline
"""

import time
from pathlib import Path
import yaml
import pandas as pd

from .state_manager import StateManager
from .repo_cloner import RepoCloner
from .type_transformer import TypeTransformer
from .pattern_extractor import PatternExtractor


class Orchestrator:
    """Main controller for the repository processing pipeline."""

    def __init__(self, config_path: str = "./config.yaml"):
        """Initialize the orchestrator."""
        print("Initializing Orchestrator...")
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.state = StateManager(config_path)
        self.cloner = RepoCloner(self.config)
        
        # NEW: Initialize type transformer and pattern extractor
        self.transformer = TypeTransformer(self.config)
        self.extractor = PatternExtractor(self.config)
        
        # Check if type inference is enabled
        self.enable_type_inference = self.config.get("enable_type_inference", True)

        # Ensure the queue is initialized
        if not self.state.queue_exists():
            print("Queue not found. Initializing from pickle file...")
            self.state.initialize_from_pickle()

    def run(self):
        """Run the main processing loop."""
        print("Starting orchestration process...")
        print(f"Type inference: {'ENABLED' if self.enable_type_inference else 'DISABLED'}")

        # Recover any jobs that got stuck from a previous run
        self.state.recover_stuck_repos()

        max_repos = self.config.get("max_repos")
        processed_count = 0

        while True:
            if max_repos is not None and processed_count >= max_repos:
                print(f"Reached max_repos limit of {max_repos}. Stopping.")
                break

            df_queue = self.state.load_queue()
            next_repo = self.state.get_next_pending(df_queue)

            if next_repo is None:
                print("No more pending repositories. Process complete.")
                break

            self._process_repo(next_repo)
            processed_count += 1

            # Checkpoint backup
            if processed_count % self.config.get("checkpoint_frequency", 10) == 0:
                print("Creating checkpoint backup...")
                self.state.create_backup()

    def _process_repo(self, repo_info: pd.Series):
        """Process a single repository with type transformation."""
        repo_id = repo_info["repo_id"]
        repo_url = repo_info["url"]
        repo_name = repo_info["name"]

        print("\n" + "=" * 70)
        print(f"Processing Repo #{repo_id}: {repo_name}")
        print(f"URL: {repo_url}")
        print("=" * 70)

        # 1. Mark as processing
        df_queue = self.state.load_queue()
        self.state.mark_processing(df_queue, repo_url)

        repo_path = None
        start_time = time.time()

        try:
            # 2. Clone repository
            print(f"🔄 Cloning repository...")
            repo_path, error = self.cloner.clone(repo_url, repo_id)
            if error:
                raise RuntimeError(f"Clone failed: {error}")
            print(f"✅ Cloned successfully to {repo_path}")

            # 3. NEW: Type transformation step
            transform_result = None
            typed_repo_dir = None
            
            if self.enable_type_inference:
                print(f"🔧 Transforming code with type inference...")
                transform_result = self.transformer.transform_repository(repo_path)
                
                print(f"   Files transformed: {transform_result.files_typed}/{transform_result.files_attempted}")
                print(f"   Type coverage: {transform_result.avg_coverage_pct:.1f}%")
                
                # Check if we should skip this repo
                should_skip, reason = self.transformer.should_skip_repo(transform_result)
                if should_skip:
                    print(f"⚠️  Skipping repo: {reason}")
                    raise RuntimeError(f"Type coverage too low: {reason}")
                
                typed_repo_dir = Path(transform_result.typed_output_dir)
            else:
                # Skip transformation, use original repo
                print(f"⚠️  Type inference disabled, using original code")
                typed_repo_dir = repo_path

            # 4. Extract patterns (from typed code if transformed)
            print("🔍 Extracting patterns...")
            df_patterns, stats = self.extractor.extract_from_repository(
                typed_repo_dir=typed_repo_dir,
                repo_path=repo_path
            )
            
            duration = time.time() - start_time
            stats["duration"] = duration
            
            # Add type transformation stats to stats dict
            if transform_result:
                stats["type_coverage_pct"] = transform_result.avg_coverage_pct
                stats["typed_files_count"] = transform_result.files_typed
                stats["transform_errors"] = transform_result.files_failed
            else:
                stats["type_coverage_pct"] = 0.0
                stats["typed_files_count"] = 0
                stats["transform_errors"] = 0
            
            print(f"✅ Pattern extraction complete in {duration:.2f}s. Found {len(df_patterns)} unique patterns.")

            # 5. Save patterns
            self.state.save_repo_patterns(repo_id, repo_name, df_patterns)
            print(f"💾 Patterns saved for {repo_name}")

            # 6. Mark as completed
            df_queue = self.state.load_queue()
            self.state.mark_completed(df_queue, repo_url, stats)
            print(f"✅ Successfully processed {repo_name}")

        except Exception as e:
            # Handle any failure
            print(f"❌ FAILED to process {repo_name}: {e}")
            df_queue = self.state.load_queue()
            self.state.mark_failed(df_queue, repo_url, str(e))

        finally:
            # 7. Cleanup
            if repo_path:
                print(f"🧹 Cleaning up {repo_path}...")
                success, error = self.cloner.cleanup(repo_path)
                if not success:
                    print(f"⚠️  Cleanup failed for {repo_path}: {error}")

        self._print_progress()

    def _print_progress(self):
        """Print the current progress statistics."""
        stats = self.state.get_progress_stats()
        total = stats["total"]
        done = stats["completed"] + stats["failed"]
        pct = (done / total * 100) if total > 0 else 0

        print("\n--- Progress ---")
        print(
            f"Completed: {stats['completed']}, Failed: {stats['failed']}, Pending: {stats['pending']}"
        )
        print(f"{done}/{total} ({pct:.1f}%) complete.")
        print("----------------\n")
