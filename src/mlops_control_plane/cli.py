from __future__ import annotations

import argparse
import json

from .demo import write_demo


def main() -> None:
    parser = argparse.ArgumentParser(prog="mlops-control-plane")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="run the deterministic v0.1 lifecycle benchmark")
    demo.add_argument("--output", default="evals/results/v0.1_control_plane.json")
    args = parser.parse_args()
    if args.command == "demo":
        result = write_demo(args.output)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
