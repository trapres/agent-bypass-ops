#!/usr/bin/env python3
"""Generate balanced safe/unsafe pairs, or check the committed bytes."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from abo.matched import build_cases, generated_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "matched-cases")
    parser.add_argument("--check", action="store_true", help="verify generated files without writing")
    parser.add_argument("--audit", action="store_true", help="list labels and safety rationale without writing")
    args = parser.parse_args()
    if args.audit:
        for case in build_cases():
            print(f"{case.id}: {case.safety_basis}")
        return 0
    files = generated_files()
    if args.check:
        actual = {p.relative_to(args.out).as_posix(): p.read_text()
                  for p in args.out.rglob("*") if p.is_file() and p != args.out / "README.md"}
        changed = sorted(path for path in actual.keys() | files.keys()
                         if actual.get(path) != files.get(path))
        if changed:
            print("Generated corpus differs: " + ", ".join(changed), file=sys.stderr)
            return 1
        print(f"Verified {len(files)} files across 16 cases (8 matched pairs).")
        return 0
    for path, content in files.items():
        destination = args.out / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
    print(f"Wrote 16 cases (8 safe, 8 unsafe) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
