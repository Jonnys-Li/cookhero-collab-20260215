"""Utility script to list HowToCook dish categories.

Usage:
    python scripts/list_categories.py

It will scan data/HowToCook/dishes and print all subdirectory names,
which correspond to category keys that HowToCookDataSource can use.
You can use the output to update HowToCookDataSource.CATEGORY_MAPPING
when new categories are added upstream.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DISHES_DIR = BASE_DIR / "data" / "HowToCook" / "dishes"


def main() -> None:
    if not DISHES_DIR.exists():
        print(f"Directory not found: {DISHES_DIR}")
        print("Please run 'python scripts/sync_data.py' first to clone/update HowToCook.")
        return

    categories = sorted(
        p.name for p in DISHES_DIR.iterdir() if p.is_dir()
    )

    print("# Discovered HowToCook dish categories:\n")
    for cat in categories:
        print(cat)

    print("\n# Suggested CATEGORY_MAPPING snippet (values can be adjusted):\n")
    print("CATEGORY_MAPPING = {")
    for cat in categories:
        # Default value is the key itself; adjust to appropriate Chinese name as needed.
        print(f"    '{cat}': '{cat}',")
    print("}")


if __name__ == "__main__":
    main()
