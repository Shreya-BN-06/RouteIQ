"""Regenerate data/processed/*.csv from data/raw/R101.txt (deterministic, no sampling)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loader import parse_solomon, subset_customers  # noqa: E402


def main() -> None:
    full, capacity = parse_solomon(ROOT / "data/raw/R101.txt")
    out = ROOT / "data/processed"
    out.mkdir(parents=True, exist_ok=True)
    for n, name in [(25, "r101_25.csv"), (100, "r101_100.csv")]:
        subset_customers(full, n).to_csv(out / name, index=False, float_format="%g")
        print(f"wrote {out / name} (depot + {n} customers, capacity {capacity})")


if __name__ == "__main__":
    main()
