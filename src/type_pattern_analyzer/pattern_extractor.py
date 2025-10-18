"""
Pattern Extractor - Session 3
Extracts type-aware patterns from transformed JavaScript files
Uses regex-based extraction (matches tree-sitter output schema)
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import Counter
import pandas as pd


class PatternExtractor:
    """Extracts code patterns from type-normalized JavaScript files"""
    
    def __init__(self, config: Dict):
        """
        Initialize Pattern Extractor with configuration.
        
        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        self.min_frequency = config.get("min_pattern_frequency", 2)
        self.max_file_size_mb = config.get("max_file_size_mb", 2.0)
        self.max_examples = config.get("max_examples_per_pattern", 5)
        
        # Load pattern categories from config
        self.pattern_categories = config.get("pattern_categories", {})
        
        # Track statistics
        self.stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "parse_errors": 0,
            "skip_reasons": Counter(),
        }
    
    def extract_from_repository(
        self, 
        typed_repo_dir: Path, 
        repo_path: Path
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Extract patterns from all typed files in repository.
        
        Args:
            typed_repo_dir: Directory with type-normalized files (e.g., repo/_typed/)
            repo_path: Original repository path (for relative file paths)
            
        Returns:
            Tuple of (df_patterns, stats_dict)
        """
        print(f"\n🔍 Extracting patterns from {typed_repo_dir}")
        
        # Find all JS/TS files
        js_files = self._find_typed_files(typed_repo_dir)
        
        if not js_files:
            print(f"⚠️  No typed files found in {typed_repo_dir}")
            return self._empty_dataframe(), self.stats
        
        print(f"📊 Found {len(js_files)} typed files")
        
        # Extract patterns from each file
        all_patterns = {}  # pattern_hash -> pattern_data
        
        for file_path in js_files:
            try:
                file_patterns = self._extract_from_file(file_path, typed_repo_dir)
                
                # Merge patterns (aggregate frequencies)
                for pattern_hash, pattern_data in file_patterns.items():
                    if pattern_hash in all_patterns:
                        # Pattern already exists - merge
                        all_patterns[pattern_hash]["frequency"] += pattern_data["frequency"]
                        all_patterns[pattern_hash]["examples"].extend(pattern_data["examples"])
                    else:
                        # New pattern
                        all_patterns[pattern_hash] = pattern_data
                
                self.stats["files_processed"] += 1
                
            except Exception as e:
                print(f"   ⚠️  Error processing {file_path.name}: {e}")
                self.stats["parse_errors"] += 1
        
        # Convert to DataFrame
        df_patterns = self._patterns_to_dataframe(all_patterns)
        
        # Filter by minimum frequency
        if len(df_patterns) > 0:
            df_patterns = df_patterns[df_patterns["frequency"] >= self.min_frequency].copy()
        
        # Update statistics
        self.stats["patterns_extracted"] = len(df_patterns)
        self.stats["total_frequency"] = int(df_patterns["frequency"].sum()) if len(df_patterns) > 0 else 0
        
        print(f"✅ Extracted {len(df_patterns)} unique patterns")
        print(f"   Total occurrences: {self.stats['total_frequency']}")
        
        return df_patterns, self.stats
    
    def _find_typed_files(self, typed_dir: Path) -> List[Path]:
        """Find all JavaScript/TypeScript files in typed directory"""
        extensions = self.config.get("pattern_file_extensions", [".js", ".jsx", ".ts", ".tsx"])
        
        files = []
        for ext in extensions:
            files.extend(typed_dir.rglob(f"*{ext}"))
        
        # Filter by size
        max_size = self.max_file_size_mb * 1024 * 1024
        filtered = []
        for f in files:
            size = f.stat().st_size
            if size <= max_size:
                filtered.append(f)
            else:
                self.stats["files_skipped"] += 1
                self.stats["skip_reasons"]["too_large"] += 1
        
        return filtered
    
    def _extract_from_file(self, file_path: Path, base_dir: Path) -> Dict[str, Dict]:
        """
        Extract patterns from a single file.
        
        Returns:
            Dictionary mapping pattern_hash to pattern data
        """
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            raise RuntimeError(f"Failed to read file: {e}")
        
        patterns = {}
        
        # Extract method call patterns: Type.method()
        method_patterns = self._extract_method_calls(content, file_path, base_dir)
        patterns.update(method_patterns)
        
        # Extract property access patterns: Type.property
        property_patterns = self._extract_property_access(content, file_path, base_dir)
        patterns.update(property_patterns)
        
        return patterns
    
    def _extract_method_calls(
        self, 
        content: str, 
        file_path: Path, 
        base_dir: Path
    ) -> Dict[str, Dict]:
        """
        Extract method call patterns: TypeName.methodName()
        
        Example matches:
        - HTMLElement.addEventListener()
        - Array.map()
        - String.split()
        """
        patterns = {}
        
        # Regex: TypeName.methodName( with optional arguments
        # Captures: type name, method name
        pattern_regex = r'(\w+)\.(\w+)\s*\('
        
        for match in re.finditer(pattern_regex, content):
            base_type = match.group(1)
            method = match.group(2)
            
            # Skip if base type is lowercase (likely not a type name)
            if not base_type[0].isupper():
                continue
            
            # Create signatures
            typed_signature = f"{base_type}.{method}()"
            
            # Generate pattern hash
            pattern_hash = self._hash_pattern(typed_signature)
            
            # Get line number for example
            line_num = content[:match.start()].count('\n') + 1
            
            # Get concrete code snippet (50 chars context)
            start = max(0, match.start() - 20)
            end = min(len(content), match.end() + 30)
            concrete_code = content[start:end].strip()
            if len(concrete_code) > 100:
                concrete_code = concrete_code[:100] + "..."
            
            # Categorize pattern
            category = self._categorize_pattern(base_type, method)
            
            # Create or update pattern
            if pattern_hash not in patterns:
                patterns[pattern_hash] = {
                    "pattern_hash": pattern_hash,
                    "typed_signature": typed_signature,
                    "base_type": base_type,
                    "method": method,
                    "abstract_signature": typed_signature,  # Compatibility
                    "semantic_signature": typed_signature,  # Compatibility
                    "node_type": "MethodCall",
                    "category": category,
                    "frequency": 0,
                    "examples": []
                }
            
            # Increment frequency
            patterns[pattern_hash]["frequency"] += 1
            
            # Add example (limit per pattern)
            if len(patterns[pattern_hash]["examples"]) < self.max_examples:
                relative_path = str(file_path.relative_to(base_dir))
                patterns[pattern_hash]["examples"].append({
                    "file_path": relative_path,
                    "line_number": line_num,
                    "concrete_code": concrete_code
                })
        
        return patterns
    
    def _extract_property_access(
        self, 
        content: str, 
        file_path: Path, 
        base_dir: Path
    ) -> Dict[str, Dict]:
        """
        Extract property access patterns: TypeName.propertyName
        
        Example matches:
        - HTMLElement.value
        - HTMLElement.textContent
        - Array.length
        """
        patterns = {}
        
        # Regex: TypeName.propertyName (not followed by '(')
        # This captures property access but not method calls
        pattern_regex = r'(\w+)\.(\w+)\s*(?!\()'
        
        for match in re.finditer(pattern_regex, content):
            base_type = match.group(1)
            property_name = match.group(2)
            
            # Skip if base type is lowercase
            if not base_type[0].isupper():
                continue
            
            # Skip common non-pattern cases
            if property_name in ['prototype', 'constructor', 'name', 'length'] and base_type not in ['Array', 'String']:
                continue
            
            # Create signatures
            typed_signature = f"{base_type}.{property_name}"
            
            # Generate pattern hash
            pattern_hash = self._hash_pattern(typed_signature)
            
            # Get line number
            line_num = content[:match.start()].count('\n') + 1
            
            # Get concrete code snippet
            start = max(0, match.start() - 20)
            end = min(len(content), match.end() + 30)
            concrete_code = content[start:end].strip()
            if len(concrete_code) > 100:
                concrete_code = concrete_code[:100] + "..."
            
            # Categorize pattern
            category = self._categorize_pattern(base_type, property_name)
            
            # Create or update pattern
            if pattern_hash not in patterns:
                patterns[pattern_hash] = {
                    "pattern_hash": pattern_hash,
                    "typed_signature": typed_signature,
                    "base_type": base_type,
                    "method": property_name,  # Using 'method' field for property name
                    "abstract_signature": typed_signature,
                    "semantic_signature": typed_signature,
                    "node_type": "PropertyAccess",
                    "category": category,
                    "frequency": 0,
                    "examples": []
                }
            
            # Increment frequency
            patterns[pattern_hash]["frequency"] += 1
            
            # Add example
            if len(patterns[pattern_hash]["examples"]) < self.max_examples:
                relative_path = str(file_path.relative_to(base_dir))
                patterns[pattern_hash]["examples"].append({
                    "file_path": relative_path,
                    "line_number": line_num,
                    "concrete_code": concrete_code
                })
        
        return patterns
    
    def _categorize_pattern(self, base_type: str, member: str) -> str:
        """
        Categorize a pattern based on base type and method/property name.
        
        Args:
            base_type: The type name (e.g., "HTMLElement", "Array")
            member: The method or property name
            
        Returns:
            Category string (e.g., "DOM_EVENTS", "ARRAY_METHODS")
        """
        # Check each category's patterns
        for category, patterns in self.pattern_categories.items():
            if member in patterns:
                return category
        
        # Fallback: categorize by type prefix
        if base_type.startswith("HTML"):
            return "DOM"
        elif base_type in ["Array", "ArrayLike"]:
            return "ARRAY"
        elif base_type in ["String", "StringArray"]:
            return "STRING"
        elif base_type in ["Object", "ObjectArray"]:
            return "OBJECT"
        elif base_type in ["Promise", "PromiseArray"]:
            return "PROMISE"
        elif base_type == "console":
            return "CONSOLE_METHODS"
        else:
            return "OTHER"
    
    def _hash_pattern(self, signature: str) -> str:
        """Generate unique hash for pattern signature"""
        return hashlib.md5(signature.encode('utf-8')).hexdigest()
    
    def _patterns_to_dataframe(self, patterns_dict: Dict[str, Dict]) -> pd.DataFrame:
        """
        Convert patterns dictionary to DataFrame with correct schema.
        
        Args:
            patterns_dict: Dictionary of pattern_hash -> pattern_data
            
        Returns:
            DataFrame matching pattern_miner_wrapper.py schema
        """
        if not patterns_dict:
            return self._empty_dataframe()
        
        # Convert to list of dicts
        pattern_list = []
        for pattern_hash, data in patterns_dict.items():
            # Serialize examples to JSON
            examples_json = json.dumps(data["examples"][:self.max_examples])
            
            pattern_list.append({
                "pattern_hash": data["pattern_hash"],
                "typed_signature": data["typed_signature"],
                "base_type": data["base_type"],
                "method": data["method"],
                "abstract_signature": data["abstract_signature"],
                "semantic_signature": data["semantic_signature"],
                "node_type": data["node_type"],
                "category": data["category"],
                "frequency": data["frequency"],
                "examples_json": examples_json
            })
        
        # Create DataFrame
        df = pd.DataFrame(pattern_list)
        
        # Sort by frequency (descending)
        df = df.sort_values("frequency", ascending=False).reset_index(drop=True)
        
        return df
    
    def _empty_dataframe(self) -> pd.DataFrame:
        """Return empty DataFrame with correct schema"""
        return pd.DataFrame({
            "pattern_hash": pd.Series(dtype="str"),
            "typed_signature": pd.Series(dtype="str"),
            "base_type": pd.Series(dtype="str"),
            "method": pd.Series(dtype="str"),
            "abstract_signature": pd.Series(dtype="str"),
            "semantic_signature": pd.Series(dtype="str"),
            "node_type": pd.Series(dtype="str"),
            "category": pd.Series(dtype="str"),
            "frequency": pd.Series(dtype="int64"),
            "examples_json": pd.Series(dtype="str"),
        })


def test_pattern_extractor():
    """Test the pattern extractor on sample transformed code"""
    import yaml
    from pathlib import Path
    
    print("\n" + "=" * 70)
    print("🧪 Testing Pattern Extractor")
    print("=" * 70)
    
    # Load config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    extractor = PatternExtractor(config)
    
    # Create a sample typed file
    sample_dir = Path("temp/test_typed")
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    sample_code = """
// Sample typed code
const HTMLElement = document.getElementById("test");
const HTMLButtonElement = document.createElement("button");
HTMLElement.addEventListener("click", () => {
    console.log("clicked");
});
HTMLButtonElement.textContent = "Click me";
HTMLElement.appendChild(HTMLButtonElement);

const numberArray = [1, 2, 3];
numberArray.forEach(item => console.log(item));
numberArray.map(x => x * 2);

const str = "hello";
str.split("");
str.toUpperCase();
"""
    
    sample_file = sample_dir / "test.js"
    sample_file.write_text(sample_code)
    
    print(f"\n📝 Created sample file: {sample_file}")
    
    # Extract patterns
    df_patterns, stats = extractor.extract_from_repository(sample_dir, sample_dir)
    
    print(f"\n📊 Extraction Results:")
    print(f"   Files processed: {stats['files_processed']}")
    print(f"   Patterns extracted: {stats['patterns_extracted']}")
    print(f"   Total frequency: {stats['total_frequency']}")
    
    if len(df_patterns) > 0:
        print(f"\n🔍 Top Patterns:")
        for idx, row in df_patterns.head(10).iterrows():
            print(f"   {row['frequency']:3d}x | {row['category']:20s} | {row['typed_signature']}")
        
        print(f"\n📋 Category Distribution:")
        cat_counts = df_patterns.groupby("category").agg({
            "frequency": "sum",
            "pattern_hash": "count"
        }).sort_values("frequency", ascending=False)
        
        for category, row_data in cat_counts.iterrows():
            print(f"   {category:20s} {row_data['pattern_hash']:3d} patterns, {row_data['frequency']:4d} occurrences")
    
    # Cleanup
    import shutil
    shutil.rmtree(sample_dir)
    print(f"\n✅ Test complete! (cleaned up {sample_dir})")


if __name__ == "__main__":
    test_pattern_extractor()