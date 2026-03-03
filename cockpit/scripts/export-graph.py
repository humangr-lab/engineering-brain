#!/usr/bin/env python3
"""Export Engineering Brain graph as static JSON for cockpit client."""

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export brain graph to JSON")
    parser.add_argument("--seeds", type=str, default=None,
                       help="Path to seeds directory")
    parser.add_argument("--brain-json", type=str, default=None,
                       help="Path to existing brain JSON file")
    parser.add_argument("--out", type=str, default="client/data/graph.json",
                       help="Output JSON file path")
    args = parser.parse_args()

    try:
        from engineering_brain import Brain
    except ImportError:
        sys.exit(
            "Error: engineering_brain package not found.\n"
            "Install it with: pip install engineering-brain\n"
            "Or set PYTHONPATH to the engineering_brain source directory."
        )

    if args.brain_json:
        print(f"Loading brain from JSON: {args.brain_json}")
        brain = Brain.load(args.brain_json)
    elif args.seeds:
        print(f"Loading brain from seeds: {args.seeds}")
        brain = Brain()
        brain.seed(args.seeds)
    else:
        print("Loading brain from built-in seeds")
        brain = Brain()
        brain.seed()

    # Export using brain bridge to get cockpit-format data
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from server.brain_bridge import BrainBridge

    if args.brain_json:
        bridge = BrainBridge(brain_json_path=args.brain_json)
    elif args.seeds:
        bridge = BrainBridge(seeds_dir=args.seeds)
    else:
        bridge = BrainBridge()

    snapshot = asyncio.run(bridge.snapshot())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Exported {len(snapshot.get('nodes', []))} nodes, "
          f"{len(snapshot.get('edges', []))} edges to {out_path}")


if __name__ == "__main__":
    main()
