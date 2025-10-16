"""
State Manager - Handles repo queue and state persistence
"""

import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

import pandas as pd
import yaml


class StateManager:
    """Manages repository queue and state transitions."""

    def __init__(self, config_path: str = "./config.yaml"):
        """Initialize state manager with configuration."""
        # Load config
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Setup paths
        self.data_dir = Path(self.config["data_dir"])
        self.patterns_dir = Path(self.config["patterns_dir"])
        self.backup_dir = Path(self.config["backup_dir"])
        self.checkpoint_dir = Path(self.config["checkpoint_dir"])

        self.repo_links_file = Path(self.config["repo_links_file"])
        self.repo_queue_file = Path(self.config["repo_queue_file"])

        # Create directories
        self.data_dir.mkdir(exist_ok=True)
        self.patterns_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def queue_exists(self) -> bool:
        """Check if queue file exists."""
        return self.repo_queue_file.exists()

    def initialize_from_pickle(self, force: bool = False) -> pd.DataFrame:
        """
        Initialize repo_queue.pkl from DF_REPO_LINKS.pkl

        Args:
            force: If True, recreate queue even if it exists

        Returns:
            DataFrame with initialized queue
        """
        if self.queue_exists() and not force:
            print(f"âœ… Queue already exists: {self.repo_queue_file}")
            print("   Use force=True to recreate")
            return self.load_queue()

        if not self.repo_links_file.exists():
            raise FileNotFoundError(f"❌ Input file not found: {self.repo_links_file}")

        # Load repo links
        print(f"📂 Loading repo links from {self.repo_links_file}...")
        df_links = pd.read_pickle(self.repo_links_file)

        # Validate structure
        if "REPO" not in df_links.columns:
            raise ValueError("❌ Input DataFrame must have 'REPO' column")

        # Extract repo names from URLs
        def extract_name(url):
            # https://github.com/facebook/react.git -> facebook/react
            parts = url.rstrip(".git").split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
            return url

        # Create queue DataFrame
        df_queue = pd.DataFrame(
            {
                "repo_id": range(1, len(df_links) + 1),
                "url": df_links["REPO"].values,
                "name": df_links["REPO"].apply(extract_name).values,
                "status": "pending",
                "attempt_count": 0,
                "last_attempt": pd.NaT,
                # Mining stats (filled after processing)
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
            }
        )

        # Save queue
        self.save_queue(df_queue)

        print(f"✅ Initialized queue with {len(df_queue)} repositories")
        print(f"💾 Saved to {self.repo_queue_file}")

        return df_queue

    def load_queue(self) -> pd.DataFrame:
        """Load queue from disk."""
        if not self.queue_exists():
            raise FileNotFoundError(f"❌ Queue not found: {self.repo_queue_file}")

        return pd.read_pickle(self.repo_queue_file)

    def save_queue(self, df_queue: pd.DataFrame) -> None:
        """Save queue to disk with atomic write."""
        # Write to temp file first
        tmp_file = self.repo_queue_file.with_suffix(".tmp")
        df_queue.to_pickle(tmp_file)

        # Atomic rename
        tmp_file.replace(self.repo_queue_file)

    def get_next_pending(self, df_queue: pd.DataFrame) -> Optional[pd.Series]:
        """
        Get next pending repository to process.

        Returns:
            Series with repo info, or None if no pending repos
        """
        pending = df_queue[df_queue["status"] == "pending"]

        if len(pending) == 0:
            return None

        # Return first pending repo
        return pending.iloc[0]

    def mark_processing(self, df_queue: pd.DataFrame, repo_url: str) -> None:
        """Mark repo as currently processing."""
        mask = df_queue["url"] == repo_url
        df_queue.loc[mask, "status"] = "processing"
        df_queue.loc[mask, "last_attempt"] = pd.Timestamp.now()
        df_queue.loc[mask, "attempt_count"] += 1

        self.save_queue(df_queue)

    def mark_completed(
        self, df_queue: pd.DataFrame, repo_url: str, stats: Dict[str, Any]
    ) -> None:
        """
        Mark repo as completed with mining statistics.

        Args:
            df_queue: Queue DataFrame
            repo_url: Repository URL
            stats: Dictionary with mining statistics
        """
        mask = df_queue["url"] == repo_url

        df_queue.loc[mask, "status"] = "completed"
        df_queue.loc[mask, "files_processed"] = stats.get("files_processed", 0)
        df_queue.loc[mask, "files_skipped"] = stats.get("files_skipped", 0)
        df_queue.loc[mask, "parse_errors"] = stats.get("parse_errors", 0)
        df_queue.loc[mask, "skip_reasons_json"] = json.dumps(
            stats.get("skip_reasons", {})
        )
        df_queue.loc[mask, "patterns_extracted"] = stats.get("patterns_extracted", 0)
        df_queue.loc[mask, "total_frequency"] = stats.get("total_frequency", 0)
        df_queue.loc[mask, "analysis_duration_sec"] = stats.get("duration", 0)

        self.save_queue(df_queue)

    def mark_failed(self, df_queue: pd.DataFrame, repo_url: str, error: str) -> None:
        """
        Mark repo as failed.

        If attempt_count < max_attempts, status is set to 'pending' for retry.
        Otherwise, status is set to 'failed'.
        """
        mask = df_queue["url"] == repo_url
        attempt_count = df_queue.loc[mask, "attempt_count"].iloc[0]
        max_attempts = self.config["retry_attempts"]

        if attempt_count < max_attempts:
            # Retry
            df_queue.loc[mask, "status"] = "pending"
            print(f"   ⚠️  Will retry ({attempt_count}/{max_attempts})")
        else:
            # Give up
            df_queue.loc[mask, "status"] = "failed"
            df_queue.loc[mask, "error_message"] = error[:500]  # Truncate
            print(f"   ❌ Failed after {max_attempts} attempts")

        self.save_queue(df_queue)

    def recover_stuck_repos(self, timeout_hours: Optional[int] = None) -> int:
        """
        Reset repos stuck in 'processing' state.

        Args:
            timeout_hours: Consider stuck after this duration (default from config)

        Returns:
            Number of repos recovered
        """
        if timeout_hours is None:
            timeout_hours = self.config["stuck_timeout_hours"]

        df_queue = self.load_queue()

        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=timeout_hours)
        stuck_mask = (df_queue["status"] == "processing") & (
            df_queue["last_attempt"] < cutoff
        )

        stuck_count = stuck_mask.sum()

        if stuck_count > 0:
            df_queue.loc[stuck_mask, "status"] = "pending"
            self.save_queue(df_queue)
            print(f"🔄 Recovered {stuck_count} stuck repos")

        return stuck_count

    def save_repo_patterns(
        self, repo_id: int, repo_name: str, df_patterns: pd.DataFrame
    ) -> Path:
        """
        Save pattern DataFrame for a repository.

        Args:
            repo_id: Repository ID
            repo_name: Repository name (e.g., 'facebook/react')
            df_patterns: DataFrame with patterns

        Returns:
            Path to saved file
        """
        # Sanitize filename
        safe_name = repo_name.replace("/", "_").replace("\\", "_")
        filename = f"repo_{repo_id:03d}_{safe_name}.pkl"
        filepath = self.patterns_dir / filename

        # Save
        df_patterns.to_pickle(filepath)

        return filepath

    def get_progress_stats(self) -> Dict[str, int]:
        """
        Get current progress statistics.

        Returns:
            Dictionary with counts by status
        """
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
        """
        Create timestamped backup of repo_queue.pkl

        Returns:
            Path to backup file
        """
        if not self.queue_exists():
            raise FileNotFoundError("❌ No queue to backup")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"repo_queue_backup_{timestamp}.pkl"

        shutil.copy2(self.repo_queue_file, backup_file)

        return backup_file

    def get_failed_repos(self) -> pd.DataFrame:
        """Get all failed repositories with error messages."""
        df_queue = self.load_queue()
        return df_queue[df_queue["status"] == "failed"][
            ["repo_id", "name", "attempt_count", "error_message"]
        ]

    def reset_repo(self, repo_url: str) -> None:
        """Reset a specific repo to pending status (for manual retry)."""
        df_queue = self.load_queue()
        mask = df_queue["url"] == repo_url

        if not mask.any():
            raise ValueError(f"❌ Repo not found: {repo_url}")

        df_queue.loc[mask, "status"] = "pending"
        df_queue.loc[mask, "attempt_count"] = 0
        df_queue.loc[mask, "error_message"] = None

        self.save_queue(df_queue)
        print(f"🔄 Reset repo: {df_queue.loc[mask, 'name'].iloc[0]}")
