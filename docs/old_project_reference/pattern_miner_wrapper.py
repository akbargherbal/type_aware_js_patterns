"""
Pattern Miner Wrapper - Phase 2
Bridges existing PatternMiner with pandas-based orchestration
Place this in: JS_CODE_PATTERN_ANALYSIS/pattern_miner_wrapper.py
"""

import json
from pathlib import Path
from typing import Tuple, Dict
import pandas as pd

# Import the existing PatternMiner
from .pattern_miner import PatternMiner


def mine_repository_to_dataframe(
    repo_path: Path, max_file_size_mb: float = 2.0, min_freq: int = 2
) -> Tuple[pd.DataFrame, Dict]:
    """
    Wrapper around PatternMiner that returns pandas-friendly output.

    This function:
    1. Runs the existing PatternMiner on a repository
    2. Converts List[CodePattern] → pandas DataFrame
    3. Serializes examples to JSON strings
    4. Returns both patterns and statistics

    Args:
        repo_path: Path to the cloned repository
        max_file_size_mb: Maximum file size to process (default: 2.0 MB)
        min_freq: Minimum frequency threshold (default: 2)

    Returns:
        Tuple of (df_patterns, stats_dict)

        df_patterns: DataFrame with columns:
            - pattern_hash: str (unique identifier)
            - abstract_signature: str (generic pattern)
            - semantic_signature: str (semantic pattern)
            - node_type: str (AST node type)
            - category: str (pattern category)
            - frequency: int (occurrences in this repo)
            - examples_json: str (JSON-serialized list of examples)

        stats_dict: Dictionary with:
            - files_processed: int
            - files_skipped: int
            - parse_errors: int
            - skip_reasons: dict (e.g., {"minified": 5, "too_large": 2})
            - patterns_extracted: int (unique patterns)
            - total_frequency: int (sum of all frequencies)
    """

    # Validate input
    repo_path = Path(repo_path)
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    # Initialize the existing PatternMiner with repo_path as first argument
    miner = PatternMiner(repo_path, max_file_size_mb=max_file_size_mb)

    # Run the miner (returns List[CodePattern])
    # Note: mine_repository() takes no arguments, it uses self.repo_path
    patterns_list = miner.mine_repository()

    # Filter by minimum frequency if needed
    if min_freq > 1:
        patterns_list = [p for p in patterns_list if p.frequency >= min_freq]

    # Convert to DataFrame
    if not patterns_list:
        # No patterns found - return empty DataFrame with correct schema and dtypes
        df_patterns = pd.DataFrame(
            {
                "pattern_hash": pd.Series(dtype="str"),
                "abstract_signature": pd.Series(dtype="str"),
                "semantic_signature": pd.Series(dtype="str"),
                "node_type": pd.Series(dtype="str"),
                "category": pd.Series(dtype="str"),
                "frequency": pd.Series(dtype="int64"),
                "examples_json": pd.Series(dtype="str"),
            }
        )
    else:
        # Convert each CodePattern to a dictionary
        pattern_dicts = []
        for pattern in patterns_list:
            # Serialize examples to JSON
            # Each example should be a dict with keys like: file_path, line_number, concrete_code
            examples_serializable = []
            for example in pattern.examples:
                if isinstance(example, dict):
                    examples_serializable.append(example)
                elif hasattr(example, "__dict__"):
                    # If it's an object, convert to dict
                    examples_serializable.append(vars(example))
                else:
                    # Fallback: convert to string
                    examples_serializable.append({"code": str(example)})

            pattern_dict = {
                "pattern_hash": pattern.pattern_hash,
                "abstract_signature": pattern.abstract_signature,
                "semantic_signature": pattern.semantic_signature,
                "node_type": pattern.node_type,
                "category": pattern.category,
                "frequency": pattern.frequency,
                "examples_json": json.dumps(examples_serializable),
            }
            pattern_dicts.append(pattern_dict)

        df_patterns = pd.DataFrame(pattern_dicts)

    # Extract statistics from the miner
    stats = miner.stats

    # Build stats dictionary
    stats_dict = {
        "files_processed": stats.get("files_processed", 0),
        "files_skipped": stats.get("files_skipped", 0),
        "parse_errors": stats.get("parse_errors", 0),
        "skip_reasons": dict(stats.get("skip_reasons", {})),  # Convert Counter to dict
        "patterns_extracted": len(df_patterns),
        "total_frequency": (
            int(df_patterns["frequency"].sum()) if len(df_patterns) > 0 else 0
        ),
    }

    return df_patterns, stats_dict


def validate_patterns_dataframe(df: pd.DataFrame) -> bool:
    """
    Validate that a patterns DataFrame has the correct schema.

    Args:
        df: DataFrame to validate

    Returns:
        True if valid, raises ValueError if invalid
    """
    required_columns = [
        "pattern_hash",
        "abstract_signature",
        "semantic_signature",
        "node_type",
        "category",
        "frequency",
        "examples_json",
    ]

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Check data types (only if DataFrame has data)
    if len(df) > 0:
        if not pd.api.types.is_string_dtype(df["pattern_hash"]):
            raise ValueError("pattern_hash must be string type")

        if not pd.api.types.is_numeric_dtype(df["frequency"]):
            raise ValueError("frequency must be numeric type")

        # Check for duplicates
        if df["pattern_hash"].duplicated().any():
            raise ValueError("Duplicate pattern_hash values found")

    return True


# Convenience function for testing
def test_wrapper_on_repo(repo_path: str):
    """
    Test the wrapper on a single repository.
    Prints summary statistics and sample patterns.

    Args:
        repo_path: Path to repository to test
    """
    print(f"Testing pattern miner wrapper on: {repo_path}")
    print("=" * 70)

    try:
        df_patterns, stats = mine_repository_to_dataframe(repo_path)

        print("\n📊 Statistics:")
        print(f"   Files processed:    {stats['files_processed']}")
        print(f"   Files skipped:      {stats['files_skipped']}")
        print(f"   Parse errors:       {stats['parse_errors']}")
        print(f"   Patterns extracted: {stats['patterns_extracted']}")
        print(f"   Total frequency:    {stats['total_frequency']}")

        if stats["skip_reasons"]:
            print(f"\n   Skip reasons:")
            for reason, count in stats["skip_reasons"].items():
                print(f"      {reason}: {count}")

        print("\n📋 DataFrame Info:")
        print(f"   Shape: {df_patterns.shape}")
        print(f"   Columns: {list(df_patterns.columns)}")

        if len(df_patterns) > 0:
            print("\n🔍 Top 10 Patterns by Frequency:")
            top_10 = df_patterns.nlargest(10, "frequency")
            for idx, row in top_10.iterrows():
                print(f"\n   {row['frequency']:4d}x | {row['category']}")
                print(f"          {row['abstract_signature'][:80]}")

            print("\n📊 Category Distribution:")
            category_counts = (
                df_patterns.groupby("category")
                .agg({"frequency": "sum", "pattern_hash": "count"})
                .sort_values("frequency", ascending=False)
            )

            for category, row_data in category_counts.iterrows():
                print(
                    f"   {category:30s} {row_data['pattern_hash']:4d} patterns, {row_data['frequency']:6d} occurrences"
                )
        else:
            print("\n⚠️  No patterns extracted")

        print("\n✅ Validation:")
        validate_patterns_dataframe(df_patterns)
        print("   All checks passed!")

        return df_patterns, stats

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None, None


if __name__ == "__main__":
    """
    Quick test - run this script directly to test the wrapper.
    Usage: python pattern_miner_wrapper.py /path/to/repo
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pattern_miner_wrapper.py <repo_path>")
        print("\nExample:")
        print("  python pattern_miner_wrapper.py ./temp/react")
        sys.exit(1)

    repo_path = sys.argv[1]
    test_wrapper_on_repo(repo_path)
