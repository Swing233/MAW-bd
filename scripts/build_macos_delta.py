"""Build a delta from two already signed release apps (never re-sign the result)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maw.app_delta import build_delta  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build_delta(args.base, args.target, args.output)
    print(f"{result['fromVersion']} → {result['toVersion']}: {args.output.stat().st_size} bytes")
