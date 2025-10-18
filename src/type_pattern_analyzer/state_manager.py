"""
State Manager - Handles repo queue and state persistence
Refactored to support processing a directory of local repositories.
"""

import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Union
from datetime import datetime

import pandas as pd
import yaml


class StateManager:
    """Manages repository queue and state transitions."""

    def __init__(self, config_path: str = "./config.yaml"):
        """Initialize state manager with configuration."""
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Setup paths
        self.data_dir = Path(self.config["data_dir"])
        self.patterns_dir = Path(self.config["patterns_dir"])
        self.backup_dir = Path(self.config["backup_dir"])
        self.repo_queue_file = Path(self.config["repo_queue_file"])

        # Create directories
        self.data_dir.mkdir(exist_ok=True)
        self.patterns_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)

    def queue_exists(self) -> bool:
        """Check if queue file exists."""
        return self.repo_queue_file.exists()

    def initialize_from_local_directory(self, force: bool = False) -> pd.DataFrame:
        """
        Initialize repo_queue.pkl by scanning a directory of local repos.

        Args:
            force: If True, recreate queue even if it exists.

        Returns:
            DataFrame with the initialized queue.
        """
        if self.queue_exists() and not force:
            print(f"✓ Queue already exists: {self.repo_queue_file}")
            print("   Use force=True to recreate.")
            return self.load_queue()

        local_repos_path_str = self.config.get("local_repos_dir")
        if not local_repos_path_str:
            raise ValueError("✗ `local_repos_dir` not set in config.yaml")

        local_repos_path = Path(local_repos_path_str)
        if not local_repos_path.is_dir():
            raise FileNotFoundError(f"✗ local_repos_dir not found: {local_repos_path}")

        print(f"📂 Scanning for repositories in {local_repos_path}...")
        repo_paths = sorted([d for d in local_repos_path.iterdir() if d.is_dir()])

        if not repo_paths:
            raise FileNotFoundError(f"✗ No subdirectories found in {local_repos_path}")

        # Create queue DataFrame with the full required schema
        df_queue = pd.DataFrame({
            "repo_id": range(1, len(repo_paths) + 1),
            "name": [p.name for p in repo_paths],
            "local_path": [str(p.resolve()) for p in repo_paths],
            "url": None,  # URL is now optional metadata
            "status": "pending",
            "attempt_count": 0,
            "last_attempt": pd.NaT,
            "type_coverage_pct": pd.NA,
            "typed_files_count": pd.NA,
            "transform_errors": pd.NA,
            "files_processed": pd.NA,
            "files_skipped": pd.NA,
            "parse_errors": pd.NA,
            "skip_reasons_json": None,
            "patterns_extracted": pd.NA,
            "total_frequency": pd.NA,
            "analysis_duration_sec": pd.NA,
            "error_message": None,
            "checkpoint_batch": pd.NA,
        })

        self.save_queue(df_queue)
        print(f"✅ Initialized queue with {len(df_queue)} local repositories.")
        print(f"💾 Saved to {self.repo_queue_file}")
        return df_queue

    def load_queue(self) -> pd.DataFrame:
        """Load queue from disk."""
        if not self.queue_exists():
            raise FileNotFoundError(f"✗ Queue not found: {self.repo_queue_file}")
        return pd.read_pickle(self.repo_queue_file)

    def save_queue(self, df_queue: pd.DataFrame) -> None:
        """Save queue to disk with atomic write."""
        tmp_file = self.repo_queue_file.with_suffix(".tmp")
        df_queue.to_pickle(tmp_file)
        tmp_file.replace(self.repo_queue_file)

    def get_next_pending(self, df_queue: pd.DataFrame) -> Optional[pd.Series]:
        """Get next pending repository to process."""
        pending = df_queue[df_queue["status"] == "pending"]
        return pending.iloc[0] if not pending.empty else None

    def mark_processing(self, df_queue: pd.DataFrame, repo_path: Path) -> None:
        """Mark repo as currently processing using its local path."""
        mask = df_queue["local_path"] == str(repo_path)
        df_queue.loc[mask, "status"] = "processing"
        df_queue.loc[mask, "last_attempt"] = pd.Timestamp.now()
        df_queue.loc[mask, "attempt_count"] += 1
        self.save_queue(df_queue)

    def mark_completed(self, df_queue: pd.DataFrame, repo_path: Path, stats: Dict[str, Any]) -> None:
        """Mark repo as completed with statistics using its local path."""
        mask = df_queue["local_path"] == str(repo_path)
        df_queue.loc[mask, "status"] = "completed"
        df_queue.loc[mask, "type_coverage_pct"] = stats.get("type_coverage_pct", pd.NA)
        df_queue.loc[mask, "typed_files_count"] = stats.get("typed_files_count", 0)
        df_queue.loc[mask, "transform_errors"] = stats.get("transform_errors", 0)
        df_queue.loc[mask, "files_processed"] = stats.get("files_processed", 0)
        df_queue.loc[mask, "files_skipped"] = stats.get("files_skipped", 0)
        df_queue.loc[mask, "parse_errors"] = stats.get("parse_errors", 0)
        df_queue.loc[mask, "skip_reasons_json"] = json.dumps(stats.get("skip_reasons", {}))
        df_queue.loc[mask, "patterns_extracted"] = stats.get("patterns_extracted", 0)
        df_queue.loc[mask, "total_frequency"] = stats.get("total_frequency", 0)
        df_queue.loc[mask, "analysis_duration_sec"] = stats.get("duration", 0)
        self.save_queue(df_queue)

    def mark_failed(self, df_queue: pd.DataFrame, repo_path: Path, error: str) -> None:
        """Mark repo as failed using its local path."""
        mask = df_queue["local_path"] == str(repo_path)
        attempt_count = df_queue.loc[mask, "attempt_count"].iloc[0]
        max_attempts = self.config.get("retry_attempts", 3)

        if attempt_count < max_attempts:
            df_queue.loc[mask, "status"] = "pending"
            print(f"   ⚠️  Will retry ({attempt_count}/{max_attempts})")
        else:
            df_queue.loc[mask, "status"] = "failed"
            df_queue.loc[mask, "error_message"] = error[:500]
            print(f"   ✗ Failed after {max_attempts} attempts")
        self.save_queue(df_queue)

    def recover_stuck_repos(self, timeout_hours: Optional[int] = None) -> int:
        """Reset repos stuck in 'processing' state."""
        if timeout_hours is None:
            timeout_hours = self.config.get("stuck_timeout_hours", 2)

        df_queue = self.load_queue()
        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=timeout_hours)
        stuck_mask = (df_queue["status"] == "processing") & (df_queue["last_attempt"] < cutoff)
        stuck_count = stuck_mask.sum()

        if stuck_count > 0:
            df_queue.loc[stuck_mask, "status"] = "pending"
            self.save_queue(df_queue)
            print(f"🔄 Recovered {stuck_count} stuck repos")
        return stuck_count

    def save_repo_patterns(self, repo_id: int, repo_name: str, df_patterns: pd.DataFrame) -> Path:
        """Save pattern DataFrame for a repository."""
        safe_name = repo_name.replace("/", "_").replace("\\", "_")
        filename = f"repo_{repo_id:03d}_{safe_name}.pkl"
        filepath = self.patterns_dir / filename
        df_patterns.to_pickle(filepath)
        return filepath

    def get_progress_stats(self) -> Dict[str, int]:
        """Get current progress statistics."""
        df_queue = self.load_queue()
        status_counts = df_queue["status"].value_counts().to_dict()
        return {
            "total": len(df_queue),
            "completed": status_counts.get("completed", 0),
            "pending": status_counts.get("pending", 0),
            "failed": status_counts.get("failed", 0),
            "processing": status_counts.get("processing", 0),
        }

    def create_backup(self) -> Path:
        """Create timestamped backup of repo_queue.pkl."""
        if not self.queue_exists():
            raise FileNotFoundError("✗ No queue to backup")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"repo_queue_backup_{timestamp}.pkl"
        shutil.copy2(self.repo_queue_file, backup_file)
        return backup_file

    def get_failed_repos(self) -> pd.DataFrame:
        """Get all failed repositories with error messages."""
        df_queue = self.load_queue()
        return df_queue[df_queue["status"] == "failed"][
            ["repo_id", "name", "local_path", "attempt_count", "error_message"]
        ]

    def reset_repo(self, repo_identifier: Union[str, Path]) -> None:
        """Reset a specific repo to pending status using its local path."""
        df_queue = self.load_queue()
        mask = df_queue["local_path"] == str(repo_identifier)
        if not mask.any():
            raise ValueError(f"✗ Repo not found: {repo_identifier}")
        df_queue.loc[mask, "status"] = "pending"
        df_queue.loc[mask, "attempt_count"] = 0
        df_queue.loc[mask, "error_message"] = None
        self.save_queue(df_queue)
        print(f"🔄 Reset repo: {df_queue.loc[mask, 'name'].iloc[0]}")

    def initialize_from_pickle(self, force: bool = False):
        """
        DEPRECATED: This method is for the old git-clone workflow.
        Use initialize_from_local_directory() instead.
        """
        print("⚠️  WARNING: `initialize_from_pickle` is deprecated.")
        print("   Please use `initialize_from_local_directory` for the new workflow.")
        # You can add the old logic here if you need to maintain backward compatibility
        # For now, we'll just raise an error to enforce the new workflow.
        raise NotImplementedError(
            "The git-clone workflow is deprecated. "
            "Configure `local_repos_dir` in config.yaml and run the orchestrator."
        )