"""
Setup Script - Create or Locate DF_REPO_LINKS.pkl
This script is designed to be run from anywhere in the project.
"""
import pandas as pd
from pathlib import Path
import sys
import shutil

# Define the project root relative to this script's location
# This script is in ./scripts/setup/, so the root is three levels up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'


def find_existing_file():
    """Search for DF_REPO_LINKS.pkl in common locations"""
    # Prioritize the canonical location
    search_paths = [
        DATA_DIR / 'DF_REPO_LINKS.pkl',
        PROJECT_ROOT / 'DF_REPO_LINKS.pkl',
    ]
    
    print("🔍 Searching for existing DF_REPO_LINKS.pkl...")
    for path in search_paths:
        if path.exists():
            print(f"✅ Found: {path.absolute()}")
            return path
    
    print("❌ File not found in common locations")
    return None


def inspect_file(filepath: Path):
    """Show contents of existing file"""
    try:
        df = pd.read_pickle(filepath)
        print(f"\n📊 File contains {len(df)} repositories")
        print(f"\nColumns: {list(df.columns)}")
        print(f"\nFirst 5 rows:")
        print(df.head())
        
        if 'REPO' in df.columns:
            print(f"\n✅ File has expected 'REPO' column")
            return df
        else:
            print(f"\n⚠️  File doesn't have 'REPO' column. Found: {list(df.columns)}")
            return df
            
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return None


def copy_to_data_dir(source_path: Path):
    """Copy file to the correct data/ directory"""
    DATA_DIR.mkdir(exist_ok=True)
    target_path = DATA_DIR / 'DF_REPO_LINKS.pkl'
    
    if target_path.exists() and source_path.resolve() != target_path.resolve():
        print(f"\n⚠️  Target already exists: {target_path}")
        response = input("Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled")
            return False
    
    shutil.copy(source_path, target_path)
    print(f"\n✅ Copied to: {target_path}")
    return True


def create_sample_file():
    """Create a sample DF_REPO_LINKS.pkl with popular JS repos"""
    print("\n📝 Creating sample DF_REPO_LINKS.pkl with 10 popular repos...")
    
    sample_repos = [
        'https://github.com/facebook/react.git',
        'https://github.com/vuejs/vue.git',
        'https://github.com/angular/angular.git',
        'https://github.com/nodejs/node.git',
        'https://github.com/microsoft/TypeScript.git',
        'https://github.com/axios/axios.git',
        'https://github.com/lodash/lodash.git',
        'https://github.com/expressjs/express.git',
        'https://github.com/webpack/webpack.git',
        'https://github.com/prettier/prettier.git',
    ]
    
    df = pd.DataFrame({'REPO': sample_repos})
    
    DATA_DIR.mkdir(exist_ok=True)
    output_path = DATA_DIR / 'DF_REPO_LINKS.pkl'
    df.to_pickle(output_path)
    
    print(f"✅ Created sample file: {output_path}")
    print(f"   Contains {len(df)} repositories")
    print("\n⚠️  NOTE: This is a SAMPLE file for testing.")
    print("   Replace it with your actual repo list when ready!")
    
    return output_path


def create_from_csv():
    """Create from a CSV file"""
    print("\n📄 Create from CSV file")
    csv_path_str = input("Enter path to CSV file (with 'url' or 'repo' column): ")
    
    csv_path = Path(csv_path_str.strip())
    if not csv_path.exists():
        print(f"❌ File not found: {csv_path}")
        return None
    
    try:
        df = pd.read_csv(csv_path)
        print(f"\nColumns found: {list(df.columns)}")
        
        url_col = None
        for col in df.columns:
            if col.lower() in ['repo', 'url', 'repository', 'git', 'github']:
                url_col = col
                break
        
        if not url_col:
            print("Available columns:", list(df.columns))
            url_col = input("Enter column name containing repo URLs: ")
        
        if url_col not in df.columns:
            print(f"❌ Column '{url_col}' not found")
            return None
        
        df_repos = pd.DataFrame({'REPO': df[url_col]})
        
        DATA_DIR.mkdir(exist_ok=True)
        output_path = DATA_DIR / 'DF_REPO_LINKS.pkl'
        
        df_repos.to_pickle(output_path)
        print(f"\n✅ Created: {output_path}")
        print(f"   Contains {len(df_repos)} repositories")
        
        return output_path
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def create_from_list():
    """Manually paste a list of repo URLs"""
    print("\n📝 Create from manual list")
    print("Paste repository URLs (one per line)")
    print("Press Ctrl+D (Unix) or Ctrl+Z+Enter (Windows) when done:")
    print()
    
    repos = sys.stdin.read().strip().splitlines()
    repos = [line.strip() for line in repos if line.strip()]
    
    if not repos:
        print("❌ No repositories entered")
        return None
    
    df = pd.DataFrame({'REPO': repos})
    
    DATA_DIR.mkdir(exist_ok=True)
    output_path = DATA_DIR / 'DF_REPO_LINKS.pkl'
    
    df.to_pickle(output_path)
    print(f"\n✅ Created: {output_path}")
    print(f"   Contains {len(df)} repositories")
    
    return output_path


def main():
    """Main execution flow for the setup wizard."""
    print("=" * 70)
    print("  🔧 DF_REPO_LINKS.pkl Setup Wizard")
    print("=" * 70)
    
    existing = find_existing_file()
    
    if existing:
        df = inspect_file(existing)
        if df is not None:
            target = DATA_DIR / 'DF_REPO_LINKS.pkl'
            if existing.resolve() == target.resolve():
                print("\n✅ File is already in the correct location!")
                print("\nYou can now run: python scripts/validation/validate_foundation.py")
                return
            else:
                copy_to_data_dir(existing)
                print("\n✅ Setup complete!")
                print("\nYou can now run: python scripts/validation/validate_foundation.py")
                return
    
    print("\n" + "=" * 70)
    print("  Options:")
    print("=" * 70)
    print("1. Create sample file (10 popular repos for testing)")
    print("2. Create from CSV file")
    print("3. Create from manual list (paste URLs)")
    print("4. Exit (I'll create the file manually)")
    print()
    
    choice = input("Select option (1-4): ").strip()
    
    if choice == '1':
        path = create_sample_file()
        if path:
            print("\n✅ Setup complete!")
            print("\nNext steps:")
            print("  1. Run: python scripts/validation/validate_foundation.py")
            print("  2. Replace sample file with your full repo list when ready")
    
    elif choice == '2':
        path = create_from_csv()
        if path:
            print("\n✅ Setup complete!")
            print("\nYou can now run: python scripts/validation/validate_foundation.py")
    
    elif choice == '3':
        path = create_from_list()
        if path:
            print("\n✅ Setup complete!")
            print("\nYou can now run: python scripts/validation/validate_foundation.py")
    
    elif choice == '4':
        print("\n📝 Manual creation instructions:")
        print(f"\nCreate a file at: {DATA_DIR / 'DF_REPO_LINKS.pkl'}")
        print("\nUsing Python:")
        print("```python")
        print("import pandas as pd")
        print("from pathlib import Path")
        print()
        print("repos = [")
        print("    'https://github.com/facebook/react.git',")
        print("    'https://github.com/vuejs/vue.git',")
        print("    # ... add your repos ...")
        print("]")
        print()
        print("df = pd.DataFrame({'REPO': repos})")
        print("data_dir = Path('data')")
        print("data_dir.mkdir(exist_ok=True)")
        print("df.to_pickle(data_dir / 'DF_REPO_LINKS.pkl')")
        print("```")
    
    else:
        print("❌ Invalid choice")


if __name__ == "__main__":
    main()