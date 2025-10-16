"""
Pattern Aggregator - Phase 3
Aggregates patterns from all repositories into a unified dataset
Place this in: JS_CODE_PATTERN_ANALYSIS/scripts/pattern_aggregator.py
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd


class PatternAggregator:
    """Aggregates code patterns across multiple repositories."""

    def __init__(
        self,
        patterns_dir: Path = Path("./data/patterns_by_repo"),
        results_dir: Path = Path("./results"),
    ):
        """
        Initialize Pattern Aggregator.

        Args:
            patterns_dir: Directory containing per-repo pattern files
            results_dir: Directory for output files
        """
        self.patterns_dir = Path(patterns_dir)
        self.results_dir = Path(results_dir)

        # Create results directory if needed
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def load_all_repo_patterns(self) -> List[tuple[int, str, pd.DataFrame]]:
        """
        Load all repository pattern files.

        Returns:
            List of tuples: (repo_id, repo_name, df_patterns)
        """
        if not self.patterns_dir.exists():
            raise FileNotFoundError(f"Patterns directory not found: {self.patterns_dir}")

        pattern_files = sorted(self.patterns_dir.glob("repo_*.pkl"))

        if len(pattern_files) == 0:
            raise FileNotFoundError(
                f"No pattern files found in {self.patterns_dir}\n"
                "Run pattern mining on repositories first."
            )

        print(f"📂 Loading {len(pattern_files)} repository pattern files...")

        repo_data = []
        for filepath in pattern_files:
            try:
                # Extract repo_id and name from filename
                # Format: repo_001_facebook_react.pkl
                filename = filepath.stem  # Remove .pkl
                parts = filename.split("_", 2)  # Split into ['repo', '001', 'facebook_react']

                if len(parts) >= 3:
                    repo_id = int(parts[1])
                    repo_name = parts[2].replace("_", "/")
                else:
                    # Fallback
                    repo_id = len(repo_data) + 1
                    repo_name = filename

                # Load DataFrame
                df = pd.read_pickle(filepath)

                # Add repo metadata
                df["repo_id"] = repo_id
                df["repo_name"] = repo_name

                repo_data.append((repo_id, repo_name, df))

            except Exception as e:
                print(f"   ⚠️  Failed to load {filepath.name}: {e}")
                continue

        print(f"✅ Loaded {len(repo_data)} repository pattern files")
        return repo_data

    def aggregate_all_patterns(
        self, min_repo_count: int = 2, min_total_frequency: int = 5
    ) -> pd.DataFrame:
        """
        Aggregate patterns across all repositories.

        Args:
            min_repo_count: Pattern must appear in at least N repos
            min_total_frequency: Pattern must have total frequency >= N

        Returns:
            DataFrame with aggregated statistics
        """
        print("\n" + "=" * 70)
        print("📊 AGGREGATING PATTERNS ACROSS REPOSITORIES")
        print("=" * 70)

        # Load all repo patterns
        repo_data = self.load_all_repo_patterns()
        total_repos = len(repo_data)

        print(f"\n⚙️  Combining patterns from {total_repos} repositories...")

        # Concatenate all DataFrames
        all_dfs = [df for _, _, df in repo_data]
        df_combined = pd.concat(all_dfs, ignore_index=True)

        print(f"   Total pattern occurrences: {len(df_combined):,}")

        # Aggregate by pattern_hash
        print("\n🔄 Aggregating by pattern_hash...")

        df_agg = (
            df_combined.groupby("pattern_hash")
            .agg(
                {
                    # Keep first occurrence of metadata
                    "abstract_signature": "first",
                    "semantic_signature": "first",
                    "node_type": "first",
                    "category": "first",
                    # Aggregate statistics
                    "frequency": "sum",  # Total across all repos
                    "repo_id": "nunique",  # Count unique repos
                    "repo_name": lambda x: list(x.unique()),  # List of repo names
                    "examples_json": lambda x: self._combine_examples(
                        x, max_examples=5
                    ),
                }
            )
            .reset_index()
        )

        # Rename columns for clarity
        df_agg.rename(
            columns={
                "frequency": "total_frequency",
                "repo_id": "repo_count",
                "repo_name": "repos_list",
            },
            inplace=True,
        )

        # Calculate prevalence percentage
        df_agg["prevalence_pct"] = (df_agg["repo_count"] / total_repos * 100).round(2)

        print(f"   Unique patterns: {len(df_agg):,}")

        # Filter by thresholds
        print(f"\n🔍 Filtering patterns...")
        print(f"   Min repo count: {min_repo_count}")
        print(f"   Min total frequency: {min_total_frequency}")

        df_filtered = df_agg[
            (df_agg["repo_count"] >= min_repo_count)
            & (df_agg["total_frequency"] >= min_total_frequency)
        ].copy()

        print(f"   Patterns after filtering: {len(df_filtered):,}")

        # Sort by total frequency (descending)
        df_filtered = df_filtered.sort_values(
            "total_frequency", ascending=False
        ).reset_index(drop=True)

        # Add rank
        df_filtered.insert(0, "rank", range(1, len(df_filtered) + 1))

        # Print summary statistics
        self._print_aggregation_summary(df_filtered, total_repos)

        return df_filtered

    def _combine_examples(self, examples_series: pd.Series, max_examples: int = 5) -> str:
        """
        Combine examples from multiple repos, taking a sample.

        Args:
            examples_series: Series of JSON strings (examples from different repos)
            max_examples: Maximum number of examples to keep

        Returns:
            JSON string with combined examples
        """
        all_examples = []

        for examples_json in examples_series:
            if pd.isna(examples_json) or not examples_json:
                continue

            try:
                examples = json.loads(examples_json)
                if isinstance(examples, list):
                    all_examples.extend(examples[:2])  # Take 2 from each repo
            except:
                continue

        # Limit total examples
        combined = all_examples[:max_examples]

        return json.dumps(combined)

    def _print_aggregation_summary(self, df_agg: pd.DataFrame, total_repos: int):
        """Print summary statistics after aggregation."""
        print(f"\n" + "=" * 70)
        print("📈 AGGREGATION SUMMARY")
        print("=" * 70)

        print(f"\n📊 Overall Statistics:")
        print(f"   Total unique patterns: {len(df_agg):,}")
        print(f"   Total occurrences: {df_agg['total_frequency'].sum():,}")
        print(f"   Repositories analyzed: {total_repos}")

        print(f"\n📊 Prevalence Distribution:")
        prevalence_bins = [0, 10, 25, 50, 75, 90, 100]
        prevalence_labels = ["<10%", "10-25%", "25-50%", "50-75%", "75-90%", ">90%"]

        df_agg["prevalence_bin"] = pd.cut(
            df_agg["prevalence_pct"],
            bins=prevalence_bins,
            labels=prevalence_labels,
            include_lowest=True,
        )

        prevalence_dist = df_agg["prevalence_bin"].value_counts().sort_index()

        for label, count in prevalence_dist.items():
            pct = count / len(df_agg) * 100
            print(f"   {label:10s}: {count:5d} patterns ({pct:5.1f}%)")

        print(f"\n📊 Category Distribution:")
        category_stats = (
            df_agg.groupby("category")
            .agg({"pattern_hash": "count", "total_frequency": "sum"})
            .rename(columns={"pattern_hash": "pattern_count"})
            .sort_values("total_frequency", ascending=False)
        )

        for category, row in category_stats.head(10).iterrows():
            print(
                f"   {category:30s} {row['pattern_count']:5d} patterns, {row['total_frequency']:8,} occurrences"
            )

        print(f"\n📊 Top 10 Patterns:")
        for idx, row in df_agg.head(10).iterrows():
            print(
                f"   {row['rank']:3d}. [{row['total_frequency']:6,}x | {row['prevalence_pct']:5.1f}%] {row['abstract_signature'][:60]}"
            )
            print(f"        Category: {row['category']}")

    def export_top_k(
        self, df_agg: pd.DataFrame, k: int = 200, output_dir: Optional[Path] = None
    ) -> Dict[str, Path]:
        """
        Export top-k patterns to multiple formats.

        Args:
            df_agg: Aggregated patterns DataFrame
            k: Number of top patterns to export
            output_dir: Override default results directory

        Returns:
            Dictionary mapping format to output path
        """
        if output_dir is None:
            output_dir = self.results_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n" + "=" * 70)
        print(f"💾 EXPORTING TOP {k} PATTERNS")
        print("=" * 70)

        # Get top-k
        df_top_k = df_agg.head(k).copy()

        output_paths = {}

        # 1. Export JSON
        json_path = output_dir / f"patterns_top_{k}.json"
        self._export_json(df_top_k, json_path, k)
        output_paths["json"] = json_path

        # 2. Export Markdown
        md_path = output_dir / f"patterns_top_{k}.md"
        self._export_markdown(df_top_k, md_path, k)
        output_paths["markdown"] = md_path

        # 3. Export full dataset as Parquet
        parquet_path = output_dir / "patterns_full.parquet"
        self._export_parquet(df_agg, parquet_path)
        output_paths["parquet"] = parquet_path

        # 4. Export category summary
        csv_path = output_dir / "category_summary.csv"
        self._export_category_summary(df_agg, csv_path)
        output_paths["category_summary"] = csv_path

        print(f"\n✅ All exports completed!")

        return output_paths

    def _export_json(self, df: pd.DataFrame, output_path: Path, k: int):
        """Export patterns to JSON with metadata."""
        print(f"\n📄 Exporting JSON: {output_path.name}")

        # Prepare data
        patterns_list = []
        for idx, row in df.iterrows():
            pattern_dict = {
                "rank": int(row["rank"]),
                "pattern_hash": row["pattern_hash"],
                "abstract_signature": row["abstract_signature"],
                "semantic_signature": row["semantic_signature"],
                "node_type": row["node_type"],
                "category": row["category"],
                "total_frequency": int(row["total_frequency"]),
                "repo_count": int(row["repo_count"]),
                "prevalence_pct": float(row["prevalence_pct"]),
            }

            # Parse examples JSON
            try:
                examples = json.loads(row["examples_json"])
                pattern_dict["examples"] = examples
            except:
                pattern_dict["examples"] = []

            patterns_list.append(pattern_dict)

        # Create output with metadata
        output = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "top_k": k,
                "total_patterns": len(df),
                "total_occurrences": int(df["total_frequency"].sum()),
            },
            "patterns": patterns_list,
        }

        # Write JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"   ✅ Exported {len(patterns_list)} patterns")
        print(f"   📊 Size: {output_path.stat().st_size / 1024:.1f} KB")

    def _export_markdown(self, df: pd.DataFrame, output_path: Path, k: int):
        """Export patterns to Markdown report."""
        print(f"\n📝 Exporting Markdown: {output_path.name}")

        with open(output_path, "w", encoding="utf-8") as f:
            # Header
            f.write(f"# JavaScript/TypeScript Code Patterns - Top {k}\n\n")
            f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
            f.write("---\n\n")

            # Summary
            f.write("## 📊 Summary\n\n")
            f.write(f"- **Total Patterns**: {len(df):,}\n")
            f.write(f"- **Total Occurrences**: {df['total_frequency'].sum():,}\n")
            f.write(f"- **Repositories Analyzed**: {df['repo_count'].max()}\n\n")
            f.write("---\n\n")

            # Group by category
            categories = df.groupby("category")

            f.write("## 📑 Table of Contents\n\n")
            for category in sorted(categories.groups.keys()):
                cat_patterns = categories.get_group(category)
                anchor = category.lower().replace("_", "-")
                f.write(f"- [{category}](#{anchor}) ({len(cat_patterns)} patterns)\n")

            f.write("\n---\n\n")

            # Patterns by category
            for category in sorted(categories.groups.keys()):
                cat_patterns = categories.get_group(category)

                f.write(f"## {category}\n\n")
                f.write(
                    f"*{len(cat_patterns)} patterns, {cat_patterns['total_frequency'].sum():,} total occurrences*\n\n"
                )

                for idx, row in cat_patterns.iterrows():
                    f.write(f"### {row['rank']}. {row['abstract_signature']}\n\n")

                    # Statistics
                    f.write(f"**Statistics:**\n")
                    f.write(
                        f"- Frequency: {row['total_frequency']:,} occurrences\n"
                    )
                    f.write(
                        f"- Prevalence: {row['prevalence_pct']:.1f}% ({row['repo_count']} repos)\n"
                    )
                    f.write(f"- Node Type: `{row['node_type']}`\n")

                    if (
                        row["semantic_signature"]
                        and row["semantic_signature"] != row["abstract_signature"]
                    ):
                        f.write(f"- Semantic: `{row['semantic_signature']}`\n")

                    f.write("\n")

                    # Examples
                    try:
                        examples = json.loads(row["examples_json"])
                        if examples:
                            f.write("**Examples:**\n\n")
                            for ex in examples[:2]:  # Show 2 examples
                                if isinstance(ex, dict) and "concrete_code" in ex:
                                    f.write(f"```javascript\n{ex['concrete_code']}\n```\n")
                                    if "file_path" in ex:
                                        f.write(f"*{ex['file_path']}*\n\n")
                    except:
                        pass

                    f.write("\n")

                f.write("---\n\n")

        print(f"   ✅ Exported {len(df)} patterns")
        print(f"   📊 Size: {output_path.stat().st_size / 1024:.1f} KB")

    def _export_parquet(self, df: pd.DataFrame, output_path: Path):
        """Export full dataset to Parquet for analysis."""
        print(f"\n💾 Exporting Parquet: {output_path.name}")

        # Prepare DataFrame (convert lists to JSON strings)
        df_export = df.copy()

        # Convert repos_list to JSON string
        df_export["repos_list"] = df_export["repos_list"].apply(json.dumps)

        # Write Parquet
        df_export.to_parquet(output_path, index=False, compression="snappy")

        print(f"   ✅ Exported {len(df)} patterns")
        print(f"   📊 Size: {output_path.stat().st_size / 1024:.1f} KB")

    def _export_category_summary(self, df: pd.DataFrame, output_path: Path):
        """Export category-level summary statistics."""
        print(f"\n📊 Exporting Category Summary: {output_path.name}")

        category_stats = (
            df.groupby("category")
            .agg(
                {
                    "pattern_hash": "count",
                    "total_frequency": "sum",
                    "repo_count": "mean",
                }
            )
            .rename(
                columns={
                    "pattern_hash": "pattern_count",
                    "repo_count": "avg_repo_count",
                }
            )
            .round(2)
            .sort_values("total_frequency", ascending=False)
        )

        category_stats.to_csv(output_path)

        print(f"   ✅ Exported {len(category_stats)} categories")

    def get_category_summary(self, df_agg: pd.DataFrame) -> pd.DataFrame:
        """
        Get summary statistics by category.

        Args:
            df_agg: Aggregated patterns DataFrame

        Returns:
            DataFrame with category-level statistics
        """
        return (
            df_agg.groupby("category")
            .agg(
                {
                    "pattern_hash": "count",
                    "total_frequency": "sum",
                    "repo_count": ["mean", "max"],
                    "prevalence_pct": "mean",
                }
            )
            .round(2)
            .sort_values(("total_frequency", "sum"), ascending=False)
        )


# Convenience function for command-line usage
def main():
    """Main entry point for standalone usage."""
    import sys

    print("\n" + "=" * 70)
    print("  📊 Pattern Aggregator")
    print("=" * 70)

    # Parse arguments
    min_repo_count = 2
    min_total_frequency = 5
    top_k = 200

    if "--min-repos" in sys.argv:
        idx = sys.argv.index("--min-repos")
        min_repo_count = int(sys.argv[idx + 1])

    if "--min-freq" in sys.argv:
        idx = sys.argv.index("--min-freq")
        min_total_frequency = int(sys.argv[idx + 1])

    if "--top-k" in sys.argv:
        idx = sys.argv.index("--top-k")
        top_k = int(sys.argv[idx + 1])

    # Run aggregation
    aggregator = PatternAggregator()

    df_agg = aggregator.aggregate_all_patterns(
        min_repo_count=min_repo_count, min_total_frequency=min_total_frequency
    )

    # Export results
    aggregator.export_top_k(df_agg, k=top_k)

    print("\n✨ Aggregation complete!")
    print(f"\nResults saved to: {aggregator.results_dir}")
    print("\nNext steps:")
    print("  1. Review results/patterns_top_200.json")
    print("  2. Check results/patterns_top_200.md for detailed report")
    print("  3. Use results/patterns_full.parquet for custom analysis")


if __name__ == "__main__":
    main()
