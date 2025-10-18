"""
Test Type Transformer on Sample Repository
Validates that the transformer works before scaling to 150 repos
"""

import sys
from pathlib import Path
import yaml
import shutil

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.type_pattern_analyzer.type_transformer import TypeTransformer


def create_sample_js_file():
    """Create a sample JS file for testing"""
    sample_code = """// Sample JavaScript file for testing type transformation
const input = document.getElementById("search");
const button = document.createElement("button");
const items = [1, 2, 3, 4, 5];

function initialize() {
    input.value = "";
    button.textContent = "Click me";
    
    const list = document.createElement("ul");
    items.forEach(item => {
        const li = document.createElement("li");
        li.textContent = String(item);
        list.appendChild(li);
    });
    
    document.body.appendChild(list);
}

initialize();
"""

    sample_file = PROJECT_ROOT / "sample_app.js"
    sample_file.write_text(sample_code)
    print(f"✅ Created sample file: {sample_file}")
    return sample_file


def test_single_file():
    """Test transformation on a single file"""
    print("\n" + "=" * 70)
    print("🧪 TEST 1: Single File Transformation")
    print("=" * 70)

    # Load config
    with open(PROJECT_ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    transformer = TypeTransformer(config)

    # Create sample file
    sample_file = create_sample_js_file()
    output_file = PROJECT_ROOT / "temp" / "sample_app_typed.js"
    output_file.parent.mkdir(exist_ok=True)

    print(f"\n🔍 Transforming {sample_file.name}...")
    result = transformer.transform_file(sample_file, output_file)

    print(f"\n📊 Results:")
    print(f"   Success: {'✅' if result.success else '❌'} {result.success}")
    print(f"   Coverage: {result.coverage_pct}%")
    print(f"   Variables: {result.variables_typed}/{result.variables_total} typed")
    print(f"   Duration: {result.duration_sec:.2f}s")

    if result.error_message:
        print(f"   ❌ Error: {result.error_message}")
        return False

    # Check output file
    if output_file.exists():
        output_size = output_file.stat().st_size
        print(f"   Output file: {output_size} bytes")

        # Show first few lines of transformed code
        print(f"\n📄 Transformed code preview:")
        lines = output_file.read_text().splitlines()[:15]
        for line in lines:
            print(f"   {line}")
        if len(lines) >= 15:
            print("   ...")
    else:
        print(f"   ❌ Output file not created!")
        return False

    return result.success and result.coverage_pct > 0


def test_repository():
    """Test transformation on a mini repository structure"""
    print("\n" + "=" * 70)
    print("🧪 TEST 2: Repository Transformation")
    print("=" * 70)

    # Create a mini test repository
    test_repo = PROJECT_ROOT / "temp" / "test_repo"
    test_repo.mkdir(parents=True, exist_ok=True)

    # Create some test files
    files_to_create = {
        "app.js": """
const title = document.getElementById("title");
const data = [1, 2, 3];
title.textContent = "Hello";
""",
        "utils.js": """
function createElement(tag) {
    return document.createElement(tag);
}

const div = createElement("div");
""",
        "components/button.js": """
const btn = document.createElement("button");
btn.addEventListener("click", () => {
    console.log("Clicked!");
});
""",
    }

    print(f"\n📁 Creating test repository at {test_repo}")
    for filepath, content in files_to_create.items():
        file_path = test_repo / filepath
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        print(f"   ✅ {filepath}")

    # Load config and transform
    with open(PROJECT_ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    transformer = TypeTransformer(config)

    print(f"\n⚙️  Transforming repository...")
    result = transformer.transform_repository(test_repo)

    print(f"\n📊 Results:")
    print(f"   Files attempted: {result.files_attempted}")
    print(f"   Files typed: {result.files_typed}")
    print(f"   Files failed: {result.files_failed}")
    print(f"   Avg coverage: {result.avg_coverage_pct}%")
    print(f"   Duration: {result.duration_sec:.2f}s")

    if result.errors:
        print(f"\n⚠️  Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            print(f"   - {error}")

    # Check if should skip
    should_skip, reason = transformer.should_skip_repo(result)
    if should_skip:
        print(f"\n⚠️  Would skip this repo: {reason}")
    else:
        print(f"\n✅ Repo meets quality threshold!")

    # Show transformed files
    typed_dir = Path(result.typed_output_dir)
    if typed_dir.exists():
        typed_files = list(typed_dir.rglob("*.js"))
        print(f"\n📄 Transformed files created: {len(typed_files)}")
        for f in typed_files[:5]:
            print(f"   - {f.relative_to(typed_dir)}")

    return result.files_typed > 0 and result.avg_coverage_pct > 0


def cleanup():
    """Clean up test files"""
    print("\n" + "=" * 70)
    print("🧹 Cleaning up test files...")
    print("=" * 70)

    test_repo = PROJECT_ROOT / "temp" / "test_repo"
    if test_repo.exists():
        shutil.rmtree(test_repo)
        print(f"   ✅ Removed {test_repo}")

    sample_file = PROJECT_ROOT / "sample_app.js"
    if sample_file.exists():
        sample_file.unlink()
        print(f"   ✅ Removed {sample_file}")

    typed_output = PROJECT_ROOT / "temp" / "sample_app_typed.js"
    if typed_output.exists():
        typed_output.unlink()
        print(f"   ✅ Removed {typed_output}")


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("🔬 TYPE TRANSFORMER VALIDATION")
    print("=" * 70)
    print(f"\nProject Root: {PROJECT_ROOT}")

    try:
        # Run tests
        test1_pass = test_single_file()
        test2_pass = test_repository()

        # Summary
        print("\n" + "=" * 70)
        print("📋 TEST SUMMARY")
        print("=" * 70)

        print(f"{'✅' if test1_pass else '❌'} Test 1: Single File Transformation")
        print(f"{'✅' if test2_pass else '❌'} Test 2: Repository Transformation")

        if test1_pass and test2_pass:
            print("\n" + "=" * 70)
            print("✅ ALL TESTS PASSED!")
            print("=" * 70)
            print("\n🚀 Type Transformer is ready!")
            print("\nNext steps:")
            print("  1. Review transformed files in temp/")
            print("  2. Test on a real repository (optional)")
            print("  3. Proceed to Session 3: Pattern Extraction")
            return 0
        else:
            print("\n" + "=" * 70)
            print("❌ SOME TESTS FAILED")
            print("=" * 70)
            return 1

    finally:
        # Always cleanup
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
