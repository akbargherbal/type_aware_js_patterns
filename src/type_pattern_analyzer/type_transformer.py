"""
Type Transformer - Session 2 (FIXED for Windows Unicode)
Python wrapper for TypeScript type inference POC
Handles subprocess management, parallelization, and error handling
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import platform

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class FileTransformResult:
    """Result of transforming a single file"""
    file_path: str
    success: bool
    coverage_pct: float  # 0-100
    variables_total: int
    variables_typed: int
    error_message: Optional[str] = None
    duration_sec: float = 0.0


@dataclass
class RepoTransformResult:
    """Result of transforming entire repository"""
    repo_path: str
    typed_output_dir: str
    files_attempted: int
    files_typed: int
    files_failed: int
    avg_coverage_pct: float  # Average across all files
    errors: List[str]
    duration_sec: float


class TypeTransformer:
    """Manages type transformation using TypeScript Compiler API"""
    
    def __init__(self, config: Dict):
        """
        Initialize TypeTransformer with configuration.
        
        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        self.ts_node_exec = config.get("ts_node_executable", "ts-node")
        self.ts_script_path = Path(config.get("ts_script_path", 
            "./src/type_pattern_analyzer/ts_scripts/type_transform_poc.ts"))
        self.transform_timeout = config.get("transform_timeout_sec", 60)
        self.max_workers = config.get("transform_workers", 5)
        self.typed_output_subdir = config.get("typed_output_subdir", "_typed")
        
        # Detect platform for Windows compatibility
        self.is_windows = platform.system() == "Windows"
        
        # Validate TypeScript script exists
        if not self.ts_script_path.exists():
            raise FileNotFoundError(f"TypeScript script not found: {self.ts_script_path}")
    
    def transform_file(self, input_file: Path, output_file: Path) -> FileTransformResult:
        """
        Transform a single JavaScript/TypeScript file.
        
        Args:
            input_file: Path to input JS/TS file
            output_file: Path to output transformed file
            
        Returns:
            FileTransformResult with statistics
        """
        start_time = time.time()
        
        if not input_file.exists():
            return FileTransformResult(
                file_path=str(input_file),
                success=False,
                coverage_pct=0.0,
                variables_total=0,
                variables_typed=0,
                error_message="Input file not found",
                duration_sec=0.0
            )
        
        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Build command
            cmd = [
                self.ts_node_exec,
                str(self.ts_script_path.absolute()),
                str(input_file.absolute()),
                str(output_file.absolute())
            ]
            
            # CRITICAL FIX: Force UTF-8 encoding for subprocess output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',  # ← FIX: Explicit UTF-8 encoding
                errors='replace',   # ← FIX: Replace invalid chars instead of crashing
                timeout=self.transform_timeout,
                cwd=self.ts_script_path.parent,
                shell=self.is_windows
            )
            
            duration = time.time() - start_time
            
            # Check if transformation succeeded
            if result.returncode != 0:
                error_msg = result.stderr[:500] if result.stderr else "Unknown error"
                return FileTransformResult(
                    file_path=str(input_file),
                    success=False,
                    coverage_pct=0.0,
                    variables_total=0,
                    variables_typed=0,
                    error_message=f"Transform failed: {error_msg}",
                    duration_sec=duration
                )
            
            # Parse statistics from stdout
            stats = self._parse_transform_output(result.stdout)
            
            # Verify output file was created
            if not output_file.exists():
                return FileTransformResult(
                    file_path=str(input_file),
                    success=False,
                    coverage_pct=0.0,
                    variables_total=0,
                    variables_typed=0,
                    error_message="Output file not created",
                    duration_sec=duration
                )
            
            return FileTransformResult(
                file_path=str(input_file),
                success=True,
                coverage_pct=stats["coverage_pct"],
                variables_total=stats["variables_total"],
                variables_typed=stats["variables_typed"],
                error_message=None,
                duration_sec=duration
            )
            
        except subprocess.TimeoutExpired:
            return FileTransformResult(
                file_path=str(input_file),
                success=False,
                coverage_pct=0.0,
                variables_total=0,
                variables_typed=0,
                error_message=f"Timeout after {self.transform_timeout}s",
                duration_sec=self.transform_timeout
            )
        except Exception as e:
            return FileTransformResult(
                file_path=str(input_file),
                success=False,
                coverage_pct=0.0,
                variables_total=0,
                variables_typed=0,
                error_message=str(e),
                duration_sec=time.time() - start_time
            )
    
    def _parse_transform_output(self, stdout: str) -> Dict[str, int]:
        """
        Parse statistics from TypeScript script output.
        
        The TypeScript script outputs lines like:
        "  myVar → string → String"
        "  ⚠️  Skipping unknownVar (type: any)"
        
        Args:
            stdout: Standard output from ts-node execution
            
        Returns:
            Dictionary with coverage statistics
        """
        variables_total = 0
        variables_typed = 0
        
        for line in stdout.splitlines():
            line = line.strip()
            
            # Count successful type mappings: "originalName → type → sanitizedType"
            if "→" in line and not line.startswith("⚠️"):
                variables_total += 1
                variables_typed += 1
            
            # Count skipped variables: "⚠️  Skipping varName (type: any)"
            elif "Skipping" in line and "(type:" in line:
                variables_total += 1
        
        coverage_pct = (variables_typed / variables_total * 100) if variables_total > 0 else 0.0
        
        return {
            "variables_total": variables_total,
            "variables_typed": variables_typed,
            "coverage_pct": round(coverage_pct, 2)
        }
    
    def _find_js_files(self, repo_path: Path) -> List[Path]:
        """
        Find all JavaScript/TypeScript files in repository.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            List of file paths
        """
        extensions = self.config.get("pattern_file_extensions", 
            [".js", ".jsx", ".ts", ".tsx"])
        
        files = []
        for ext in extensions:
            files.extend(repo_path.rglob(f"*{ext}"))
        
        # Filter out node_modules and other common excludes
        exclude_patterns = ["node_modules", "dist", "build", ".git", "vendor"]
        
        filtered = []
        for f in files:
            if not any(pattern in f.parts for pattern in exclude_patterns):
                # Check file size
                max_size = self.config.get("max_file_size_mb", 2.0) * 1024 * 1024
                if f.stat().st_size <= max_size:
                    filtered.append(f)
        
        return filtered
    
    def transform_repository(self, repo_path: Path, output_dir: Optional[Path] = None) -> RepoTransformResult:
        """
        Transform all files in a repository (parallel processing).
        
        Args:
            repo_path: Path to cloned repository
            output_dir: Optional custom output directory (default: repo_path/_typed)
            
        Returns:
            RepoTransformResult with aggregated statistics
        """
        start_time = time.time()
        
        if output_dir is None:
            output_dir = repo_path / self.typed_output_subdir
        
        output_dir.mkdir(exist_ok=True)
        
        logger.info(f"🔍 Finding JS/TS files in {repo_path}")
        js_files = self._find_js_files(repo_path)
        
        if not js_files:
            logger.warning(f"⚠️  No JS/TS files found in {repo_path}")
            return RepoTransformResult(
                repo_path=str(repo_path),
                typed_output_dir=str(output_dir),
                files_attempted=0,
                files_typed=0,
                files_failed=0,
                avg_coverage_pct=0.0,
                errors=["No JS/TS files found"],
                duration_sec=time.time() - start_time
            )
        
        logger.info(f"📊 Found {len(js_files)} files to transform")
        
        # Prepare file pairs (input, output)
        file_pairs = []
        for input_file in js_files:
            # Preserve directory structure in output
            rel_path = input_file.relative_to(repo_path)
            output_file = output_dir / rel_path
            file_pairs.append((input_file, output_file))
        
        # Transform files in parallel
        results: List[FileTransformResult] = []
        errors: List[str] = []
        
        logger.info(f"⚙️  Transforming with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self.transform_file, input_f, output_f): (input_f, output_f)
                for input_f, output_f in file_pairs
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_file):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if not result.success:
                        errors.append(f"{result.file_path}: {result.error_message}")
                    
                    # Log progress every 10 files
                    if len(results) % 10 == 0:
                        logger.info(f"   Progress: {len(results)}/{len(file_pairs)} files")
                
                except Exception as e:
                    input_f, output_f = future_to_file[future]
                    errors.append(f"{input_f}: {str(e)}")
        
        # Aggregate statistics
        files_attempted = len(results)
        files_typed = sum(1 for r in results if r.success)
        files_failed = sum(1 for r in results if not r.success)
        
        # Calculate average coverage (only from successful transformations)
        successful_results = [r for r in results if r.success]
        avg_coverage_pct = (
            sum(r.coverage_pct for r in successful_results) / len(successful_results)
            if successful_results else 0.0
        )
        
        duration = time.time() - start_time
        
        logger.info(f"✅ Transformation complete in {duration:.2f}s")
        logger.info(f"   Success: {files_typed}/{files_attempted} files")
        logger.info(f"   Avg coverage: {avg_coverage_pct:.1f}%")
        
        return RepoTransformResult(
            repo_path=str(repo_path),
            typed_output_dir=str(output_dir),
            files_attempted=files_attempted,
            files_typed=files_typed,
            files_failed=files_failed,
            avg_coverage_pct=round(avg_coverage_pct, 2),
            errors=errors[:10],  # Keep only first 10 errors
            duration_sec=round(duration, 2)
        )
    
    def should_skip_repo(self, transform_result: RepoTransformResult) -> Tuple[bool, str]:
        """
        Determine if repository should be skipped based on transform results.
        
        Args:
            transform_result: Result from transform_repository()
            
        Returns:
            Tuple of (should_skip, reason)
        """
        # Check type coverage threshold
        threshold = self.config.get("type_coverage_threshold", 30)
        
        if transform_result.avg_coverage_pct < threshold:
            return True, f"Type coverage {transform_result.avg_coverage_pct:.1f}% below threshold {threshold}%"
        
        # Check max transform errors
        max_errors = self.config.get("max_transform_errors", 10)
        
        if transform_result.files_failed > max_errors:
            return True, f"Too many failed files: {transform_result.files_failed} > {max_errors}"
        
        # Check if any files were successfully typed
        if transform_result.files_typed == 0:
            return True, "No files successfully typed"
        
        return False, ""
