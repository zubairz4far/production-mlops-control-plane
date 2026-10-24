"""Verify a frozen MLOps lifecycle, permitting Python patch updates only."""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path


def compatible_python_patch(expected: str, observed: str) -> bool:
    """Accept only patch-level interpreter differences within the same major/minor."""
    def parts(version: str) -> tuple[int, ...] | None:
        segments = version.split(".")
        if len(segments) != 3 or not all(item.isdigit() for item in segments):
            return None
        return tuple(int(item) for item in segments)

    lhs, rhs = parts(expected), parts(observed)
    return lhs is not None and rhs is not None and lhs[:2] == rhs[:2]


def verify(frozen: dict, observed: dict) -> tuple[bool, str]:
    """Require all benchmark outcomes and dependency versions to match exactly."""
    expected = json.loads(json.dumps(frozen))
    actual = json.loads(json.dumps(observed))
    try:
        lhs = expected["runtime"]["python"]
        rhs = actual["runtime"]["python"]
    except (KeyError, TypeError):
        return False, "Missing runtime.python in frozen or observed evidence"
    if not isinstance(lhs, str) or not isinstance(rhs, str):
        return False, "Invalid runtime.python type"
    if not compatible_python_patch(lhs, rhs):
        return False, f"Unreviewed Python interpreter change: {lhs!r} -> {rhs!r}"

    # Patch upgrades can change runner version without changing the measured
    # lifecycle. No other field (including other runtime versions) is ignored.
    actual["runtime"]["python"] = lhs
    if expected == actual:
        return True, "Frozen lifecycle and security invariants match exactly"

    before = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    after = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    diff = "\n".join(difflib.unified_diff(before, after, fromfile="frozen", tofile="observed"))
    return False, diff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("observed", type=Path)
    args = parser.parse_args()
    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    observed = json.loads(args.observed.read_text(encoding="utf-8"))
    passed, explanation = verify(frozen, observed)
    print(explanation)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
