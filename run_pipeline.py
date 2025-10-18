"""
Main entry point for running the Type-Aware Pattern Mining pipeline.
"""
import sys
from pathlib import Path

# Ensure the source code is in the Python path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / 'src'))

from type_pattern_analyzer.orchestrator import Orchestrator

def main():
    """
    Initializes and runs the main orchestrator.
    """
    print("=" * 70)
    print("🚀 Starting Type-Aware Pattern Mining Pipeline")
    print("=" * 70)

    try:
        # The Orchestrator will automatically find and use 'config.yaml'
        orchestrator = Orchestrator()
        orchestrator.run()

        print("\n" + "=" * 70)
        print("✅ Pipeline execution finished successfully.")
        print("=" * 70)

    except FileNotFoundError as e:
        print(f"\n❌ ERROR: A required file or directory was not found.")
        print(f"   Details: {e}")
        print("   Please ensure 'config.yaml' is configured correctly and all paths exist.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()