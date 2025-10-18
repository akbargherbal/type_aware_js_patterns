# Data Flow & Schema Documentation

## Overview

This document defines the data structures and flow between components in the type-aware pattern mining pipeline.

---

## 📊 Data Flow Diagram

```
DF_REPO_LINKS.pkl (input)
    ↓
[StateManager.initialize_from_pickle()]
    ↓
repo_queue.pkl
    ↓
[Orchestrator Loop]
    ↓
    ├─> [RepoCloner.clone()]
    │       ↓
    │   temp/repo_001/  (cloned repository)
    │
    ├─> [TypeTransformer.transform_repository()]
    │       ↓
    │   temp/repo_001/_typed/  (transformed files)
    │       ↓
    │   TransformResult {
    │       files_attempted: int
    │       files_typed: int
    │       files_failed: int
    │       avg_coverage_pct: float
    │       errors: List[str]
    │   }
    │
    ├─> [PatternExtractor.extract_from_repository()]
    │       ↓
    │   DataFrame + StatsDict
    │
    ├─> [StateManager.save_repo_patterns()]
    │       ↓
    │   data/typed_patterns_by_repo/repo_001_facebook_react.pkl
    │
    └─> [StateManager.mark_completed()]
            ↓
        repo_queue.pkl (updated)

[PatternAggregator.aggregate_all_patterns()]
    ↓
results/
    ├── patterns_top_200.json
    ├── patterns_top_200.md
    ├── patterns_full.parquet
    └── category_summary.csv
```

---

## 📋 Schema Definitions

### 1. Input: DF_REPO_LINKS.pkl

**Purpose:** List of GitHub repositories to process

**Schema:**
```python
pd.DataFrame({
    "REPO": str  # Full git URL, e.g., "https://github.com/facebook/react.git"
})
```

**Example:**
```python
   REPO
0  https://github.com/facebook/react.git
1  https://github.com/vuejs/vue.git
2  https://github.com/angular/angular.git
```

---

### 2. Queue State: repo_queue.pkl

**Purpose:** Tracks processing status for each repository

**Schema:**
```python
pd.DataFrame({
    # Repository identification
    "repo_id": int,                    # Unique ID (1, 2, 3, ...)
    "url": str,                        # Git URL
    "name": str,                       # Friendly name (e.g., "facebook/react")
    
    # Processing state
    "status": str,                     # One of: "pending", "processing", "completed", "failed"
    "attempt_count": int,              # Number of processing attempts
    "last_attempt": pd.Timestamp,      # When last processing attempt started
    
    # File processing stats (from old project)
    "files_processed": int,            # Number of files successfully processed
    "files_skipped": int,              # Number of files skipped
    "parse_errors": int,               # Number of parsing errors
    "skip_reasons_json": str,          # JSON dict of skip reasons
    
    # Type transformation stats (NEW - Session 3)
    "type_coverage_pct": float,        # Avg % of variables successfully typed
    "typed_files_count": int,          # Number of files with type transformation
    "transform_errors": int,           # Number of transformation errors
    
    # Pattern extraction results
    "patterns_extracted": int,         # Number of unique patterns found
    "total_frequency": int,            # Sum of all pattern frequencies
    "analysis_duration_sec": float,    # Total processing time
    
    # Error tracking
    "error_message": str,              # Error message if status="failed"
    "checkpoint_batch": int,           # Checkpoint batch number
})
```

**Status Transitions:**
```
"pending" → "processing" → "completed"
                ↓
           "failed" → "pending" (retry)
                ↓
           "failed" (max retries exceeded)
```

---

### 3. Transform Result: TypeTransformer Output

**Purpose:** Statistics from type transformation step

**Python Class:**
```python
@dataclass
class FileTransformResult:
    """Result of transforming a single file"""
    file_path: Path
    success: bool
    coverage_pct: float  # 0-100
    variables_total: int
    variables_typed: int
    error_message: Optional[str]

@dataclass
class RepoTransformResult:
    """Result of transforming entire repository"""
    repo_path: Path
    typed_output_dir: Path
    files_attempted: int
    files_typed: int
    files_failed: int
    avg_coverage_pct: float  # Average across all files
    errors: List[str]  # List of error messages
    duration_sec: float
```

**JSON Output from TypeScript POC:**
```json
{
  "file_path": "src/components/Button.js",
  "success": true,
  "coverage_pct": 71.4,
  "variables_total": 7,
  "variables_typed": 5,
  "type_breakdown": {
    "HTMLElement": 2,
    "HTMLButtonElement": 1,
    "String": 1,
    "Function": 1
  }
}
```

---

### 4. Pattern DataFrame: Output from PatternExtractor

**Purpose:** Patterns extracted from a single repository

**CRITICAL:** Must match schema from old `pattern_miner_wrapper.py` for compatibility with `pattern_aggregator.py`

**Schema:**
```python
pd.DataFrame({
    # Pattern identification
    "pattern_hash": str,               # Unique identifier (MD5 hash of signature)
    
    # Pattern signatures (ADAPTED FOR TYPE-AWARE)
    "typed_signature": str,            # NEW: Full typed pattern (e.g., "HTMLInputElement.addEventListener()")
    "base_type": str,                  # NEW: Base type (e.g., "HTMLInputElement")
    "method": str,                     # NEW: Method name (e.g., "addEventListener")
    
    # Old schema columns (keep for compatibility)
    "abstract_signature": str,         # Same as typed_signature for now
    "semantic_signature": str,         # Same as typed_signature for now
    "node_type": str,                  # "MethodCall" (regex doesn't give AST node types)
    
    # Categorization
    "category": str,                   # One of: DOM_EVENTS, DOM_QUERIES, ARRAY_METHODS, etc.
    
    # Statistics
    "frequency": int,                  # Number of occurrences in this repo
    
    # Examples
    "examples_json": str,              # JSON-serialized list of example dicts
})
```

**Example Row:**
```python
{
    "pattern_hash": "a3f5e8c9...",
    "typed_signature": "HTMLInputElement.addEventListener()",
    "base_type": "HTMLInputElement",
    "method": "addEventListener",
    "abstract_signature": "HTMLInputElement.addEventListener()",  # Compat
    "semantic_signature": "HTMLInputElement.addEventListener()",  # Compat
    "node_type": "MethodCall",
    "category": "DOM_EVENTS",
    "frequency": 42,
    "examples_json": '[{"file_path": "src/app.js", "line_number": 15, "concrete_code": "input.addEventListener(\\"click\\", ...)"}]'
}
```

---

### 5. Examples JSON Format

**Purpose:** Store concrete code examples for each pattern

**Format:** JSON array of example dictionaries

**Schema:**
```python
List[Dict[str, Any]] where each dict has:
{
    "file_path": str,        # Relative path from repo root
    "line_number": int,      # Line number in file
    "concrete_code": str,    # Actual code snippet (max 200 chars)
}
```

**Example:**
```json
[
  {
    "file_path": "src/components/Form.js",
    "line_number": 23,
    "concrete_code": "const HTMLInputElement = document.getElementById(\"email\");"
  },
  {
    "file_path": "src/utils/validation.js", 
    "line_number": 47,
    "concrete_code": "HTMLInputElement.addEventListener(\"blur\", validateEmail);"
  }
]
```

---

### 6. Statistics Dictionary: From PatternExtractor

**Purpose:** Summary statistics for a repository

**Schema:**
```python
{
    # File processing
    "files_processed": int,          # Files successfully analyzed
    "files_skipped": int,            # Files skipped (minified, too large, etc.)
    "parse_errors": int,             # Files that failed to parse
    "skip_reasons": Dict[str, int],  # Reasons for skipping {"minified": 5, "too_large": 2}
    
    # Pattern extraction
    "patterns_extracted": int,       # Number of unique patterns
    "total_frequency": int,          # Sum of all frequencies
    
    # Performance
    "duration": float,               # Processing time in seconds
}
```

---

### 7. Aggregated Patterns: Output from PatternAggregator

**Purpose:** Patterns aggregated across all repositories

**Schema:**
```python
pd.DataFrame({
    # Rank
    "rank": int,                     # 1, 2, 3, ... (sorted by total_frequency)
    
    # Pattern identification
    "pattern_hash": str,
    "typed_signature": str,          # NEW
    "base_type": str,                # NEW
    "method": str,                   # NEW
    
    # Old schema (compatibility)
    "abstract_signature": str,
    "semantic_signature": str,
    "node_type": str,
    "category": str,
    
    # Aggregated statistics
    "total_frequency": int,          # Sum across all repos
    "repo_count": int,               # Number of repos containing pattern
    "prevalence_pct": float,         # (repo_count / total_repos) * 100
    
    # Metadata
    "repos_list": str,               # JSON list of repo names
    "examples_json": str,            # Combined examples (max 5)
})
```

---

## 🔄 Component Interfaces

### TypeTransformer → PatternExtractor

**Output:** Directory of transformed files + `RepoTransformResult`

**PatternExtractor expects:**
```python
typed_repo_dir = Path("temp/repo_001/_typed/")
# Should contain .js/.ts files with type-normalized identifiers
# e.g., const HTMLElement = document.getElementById(...)
```

### PatternExtractor → StateManager

**Output:** `(df_patterns, stats_dict)`

**StateManager expects:**
- `df_patterns`: DataFrame with schema defined above
- `stats_dict`: Dictionary with keys defined above

### StateManager → PatternAggregator

**Output:** Multiple `.pkl` files in `data/typed_patterns_by_repo/`

**PatternAggregator expects:**
- Filename format: `repo_{id:03d}_{name}.pkl`
- Each file contains a DataFrame with pattern schema
- Each DataFrame has `repo_id` and `repo_name` columns

---

## 🎯 Critical Compatibility Notes

### For Session 2 (TypeTransformer):
- Must create output directory: `{repo_path}/_typed/`
- Must return `RepoTransformResult` with coverage stats
- Must handle timeouts and errors gracefully

### For Session 3 (PatternExtractor):
- **MUST output DataFrame with exact schema from `pattern_miner_wrapper.py`**
- Even though we use regex (not tree-sitter), output must match
- `examples_json` must be valid JSON string
- `pattern_hash` must be unique per pattern

### For Session 4 (PatternAggregator):
- Only needs column name updates:
  - Add: `typed_signature`, `base_type`, `method`
  - Keep: `abstract_signature`, `semantic_signature` (for compatibility)
- All aggregation logic stays the same

---

## ✅ Validation Checklist

Before moving to next session, verify:

- [ ] `config.yaml` has all required settings
- [ ] `package.json` has TypeScript dependencies
- [ ] `requirements.txt` has pandas, PyYAML, etc.
- [ ] Schema documentation is clear
- [ ] Component interfaces are defined
- [ ] Compatibility requirements are understood

---

## 📝 Next Session Preview

**Session 2 will implement:**
```python
class TypeTransformer:
    def transform_file(self, input_js: Path, output_js: Path) -> FileTransformResult:
        """Subprocess wrapper for TypeScript POC"""
        pass
    
    def transform_repository(self, repo_path: Path, output_dir: Path) -> RepoTransformResult:
        """Batch transformation with parallelization"""
        pass
```

This will bridge Python orchestration with TypeScript transformation.
