import time
from pathlib import Path
import yaml
import pandas as pd

from .state_manager import StateManager
from .repo_cloner import RepoCloner
from .pattern_miner_wrapper import mine_repository_to_dataframe


class Orchestrator:
    """Main controller for the repository processing pipeline."""

    def __init__(self, config_path: str = "./config.yaml"):
        """Initialize the orchestrator."""
        print("Initializing Orchestrator...")
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.state = StateManager(config_path)
        self.cloner = RepoCloner(self.config)

        # Ensure the queue is initialized
        if not self.state.queue_exists():
            print("Queue not found. Initializing from pickle file...")
            self.state.initialize_from_pickle()

    def run(self):
        """Run the main processing loop."""
        print("Starting orchestration process...")

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
        """Process a single repository."""
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
            print(f"Cloning repository...")
            repo_path, error = self.cloner.clone(repo_url, repo_id)
            if error:
                raise RuntimeError(f"Clone failed: {error}")
            print(f"Cloned successfully to {repo_path}")

            # 3. Mine patterns
            print("Mining patterns...")
            df_patterns, stats = mine_repository_to_dataframe(
                repo_path,
                max_file_size_mb=self.config.get("max_file_size_mb", 2.0),
                min_freq=self.config.get("min_pattern_frequency", 2),
            )
            duration = time.time() - start_time
            stats["duration"] = duration
            print(
                f"Mining complete in {duration:.2f}s. Found {len(df_patterns)} unique patterns."
            )

            # 4. Save patterns
            self.state.save_repo_patterns(repo_id, repo_name, df_patterns)
            print(f"Patterns saved for {repo_name}")

            # 5. Mark as completed
            df_queue = self.state.load_queue()
            self.state.mark_completed(df_queue, repo_url, stats)
            print(f"✅ Successfully processed {repo_name}")

        except Exception as e:
            # Handle any failure
            print(f"❌ FAILED to process {repo_name}: {e}")
            df_queue = self.state.load_queue()
            self.state.mark_failed(df_queue, repo_url, str(e))

        finally:
            # 6. Cleanup
            if repo_path:
                print(f"Cleaning up {repo_path}...")
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
