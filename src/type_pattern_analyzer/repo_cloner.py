import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import time
import os
import stat


class RepoCloner:
    """Handles git clone and cleanup operations."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the RepoCloner with configuration.

        Args:
            config: Configuration dictionary, typically from config.yaml
        """
        self.clone_timeout = config.get("clone_timeout_sec", 300)
        self.clone_depth = config.get("clone_depth", 1)
        self.temp_dir = Path(config.get("temp_dir", "./temp"))
        self.temp_dir.mkdir(exist_ok=True)

    def clone(self, repo_url: str, repo_id: int) -> Tuple[Path, Optional[str]]:
        """
        Clones a repository into a temporary directory.

        Args:
            repo_url: The git URL of the repository.
            repo_id: A unique ID for the repository.

        Returns:
            A tuple of (path_to_repo, error_message).
            If successful, error_message is None.
            If failed, path_to_repo is the path that was attempted.
        """
        target_dir = self.temp_dir / f"repo_{repo_id}"

        try:
            # Clean up previous attempt if it exists
            if target_dir.exists():
                self.cleanup(target_dir)

            command = [
                "git",
                "clone",
                "--depth",
                str(self.clone_depth),
                repo_url,
                str(target_dir),
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.clone_timeout,
                check=False,  # Don't raise exception on non-zero exit
            )

            if result.returncode != 0:
                error = f"Clone failed with exit code {result.returncode}.\n"
                error += f"Stderr: {result.stderr[:500]}"
                return target_dir, error

            return target_dir, None

        except subprocess.TimeoutExpired:
            return target_dir, f"Clone timed out after {self.clone_timeout} seconds."
        except Exception as e:
            return target_dir, f"An unexpected error occurred during clone: {e}"

    def _fix_permissions(self, directory: Path):
        """Walks a directory and makes all files writable to fix PermissionErrors."""
        for root, dirs, files in os.walk(directory):
            for name in files:
                filepath = os.path.join(root, name)
                try:
                    os.chmod(filepath, stat.S_IWRITE)
                except Exception:
                    pass  # Ignore errors, this is a best-effort fix

    def cleanup(self, repo_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Safely removes a directory tree with retry logic for Windows.

        Args:
            repo_path: The path to the directory to remove.

        Returns:
            A tuple of (success, error_message).
        """
        if not repo_path.exists():
            return True, None

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                shutil.rmtree(repo_path)
                return True, None
            except PermissionError as e:
                if attempt < max_attempts - 1:
                    time.sleep(1)  # Wait for 1 second
                    self._fix_permissions(repo_path)  # Attempt to fix permissions
                else:
                    error = f"Failed to remove directory {repo_path} after {max_attempts} attempts: {e}"
                    return False, error

        # Fallback in case loop finishes unexpectedly
        return False, f"Cleanup failed for {repo_path} after all attempts."
