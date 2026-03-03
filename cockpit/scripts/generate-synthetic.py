#!/usr/bin/env python3
"""Generate synthetic graph_data.json files for benchmarks and testing.

Uses Erdos-Renyi model with configurable node count. Produces graphs that
validate against schemas/graph_data.json.

Usage:
    python scripts/generate-synthetic.py --nodes 1000
    python scripts/generate-synthetic.py --nodes 100 --output examples/synthetic/small.json
    python scripts/generate-synthetic.py --nodes 5000 --seed 42
"""

from __future__ import annotations

import json

import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# -- Node types and groups ---------------------------------------------------

NODE_TYPES = [
    "service",
    "module",
    "class",
    "function",
    "database",
    "queue",
    "api",
    "config",
    "file",
    "package",
]

NODE_GROUPS = [
    "backend",
    "frontend",
    "infra",
    "data",
    "auth",
    "api",
    "core",
    "utils",
    "testing",
    "config",
]

EDGE_TYPES = [
    "CALLS",
    "DEPENDS_ON",
    "IMPORTS",
    "CONTAINS",
    "HTTP",
    "GRPC",
    "PUBLISHES",
    "SUBSCRIBES",
]

# -- Name generators ---------------------------------------------------------

_ADJECTIVES = [
    "fast", "smart", "core", "main", "base", "data", "auth", "user",
    "event", "async", "batch", "cache", "graph", "meta", "test", "mock",
    "real", "live", "prod", "beta", "edge", "deep", "flat", "rich",
]

_NOUNS = [
    "service", "handler", "manager", "engine", "store", "queue", "worker",
    "router", "mapper", "parser", "builder", "loader", "sender", "reader",
    "writer", "filter", "client", "server", "bridge", "proxy", "gateway",
    "monitor", "tracker", "logger", "config", "schema", "model", "view",
]


def _generate_node_id(index: int, rng: random.Random) -> str:
    """Generate a unique, schema-valid node ID."""
    adj = rng.choice(_ADJECTIVES)
    noun = rng.choice(_NOUNS)
    return f"{adj}_{noun}_{index:04d}"


def _generate_label(node_id: str) -> str:
    """Derive a human-readable label from a node ID."""
    parts = node_id.rsplit("_", 1)[0]  # drop the numeric suffix
    return parts.replace("_", " ").title()


# -- Graph generation --------------------------------------------------------


def generate_graph(
    num_nodes: int,
    edge_probability: float | None = None,
    seed: int | None = None,
) -> dict:
    """Generate a synthetic graph using Erdos-Renyi model.

    Args:
        num_nodes: Number of nodes to generate.
        edge_probability: Probability of edge between any two nodes.
            Defaults to 6/N (average ~3 edges per node).
        seed: Random seed for reproducibility.

    Returns:
        A dict conforming to the graph_data.json schema.
    """
    rng = random.Random(seed)

    if edge_probability is None:
        # Target ~3 edges per node on average
        edge_probability = min(6.0 / max(num_nodes, 1), 1.0)

    # Generate nodes
    nodes = []
    node_ids = []
    for i in range(num_nodes):
        node_id = _generate_node_id(i, rng)
        node_ids.append(node_id)

        node_type = rng.choice(NODE_TYPES)
        group = rng.choice(NODE_GROUPS)
        loc = rng.randint(10, 2000)
        complexity = round(rng.uniform(1.0, 50.0), 1)

        node = {
            "id": node_id,
            "label": _generate_label(node_id),
            "type": node_type,
            "group": group,
            "properties": {
                "loc": loc,
                "complexity": complexity,
                "description": f"Synthetic {node_type} node #{i}",
            },
        }
        nodes.append(node)

    # Generate edges using Erdos-Renyi model
    edges = []
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i == j:
                continue
            if rng.random() < edge_probability:
                edge_type = rng.choice(EDGE_TYPES)
                weight = round(rng.uniform(0.1, 1.0), 2)
                edge = {
                    "from": node_ids[i],
                    "to": node_ids[j],
                    "type": edge_type,
                    "properties": {
                        "weight": weight,
                    },
                }
                edges.append(edge)

    # Assemble graph
    graph = {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "name": f"Synthetic Graph ({num_nodes} nodes)",
            "version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "ontology-map-toolkit/generate-synthetic",
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }

    return graph


# -- CLI ---------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate synthetic graph_data.json for benchmarks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/generate-synthetic.py --nodes 100\n"
            "  python scripts/generate-synthetic.py --nodes 1000 --output examples/synthetic/large.json\n"
            "  python scripts/generate-synthetic.py --nodes 5000 --seed 42\n"
        ),
    )
    parser.add_argument(
        "--nodes", "-n",
        type=int,
        default=100,
        help="Number of nodes to generate (default: 100)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path (default: examples/synthetic/graph_{N}nodes.json)",
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--edge-probability", "-p",
        type=float,
        default=None,
        help="Edge probability (default: 6/N for ~3 edges per node)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate output against schemas/graph_data.json",
    )

    args = parser.parse_args()

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path("examples/synthetic")
        output_path = output_dir / f"graph_{args.nodes}nodes.json"

    # Generate
    print(f"Generating graph with {args.nodes} nodes (seed={args.seed})...")
    graph = generate_graph(
        num_nodes=args.nodes,
        edge_probability=args.edge_probability,
        seed=args.seed,
    )

    # Validate if requested
    if args.validate:
        schema_path = Path("schemas/graph_data.json")
        if schema_path.exists():
            try:
                from jsonschema import Draft202012Validator

                with open(schema_path) as f:
                    schema = json.load(f)
                validator = Draft202012Validator(schema)
                errors = list(validator.iter_errors(graph))
                if errors:
                    print(f"VALIDATION FAILED: {len(errors)} error(s)")
                    for e in errors[:5]:
                        print(f"  {e.json_path}: {e.message}")
                    sys.exit(1)
                print("Validation: OK")
            except ImportError:
                print("Warning: jsonschema not installed, skipping validation")
        else:
            print(f"Warning: schema not found at {schema_path}")

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(graph, f, indent=2)

    # Report
    size_kb = output_path.stat().st_size / 1024
    avg_edges = len(graph["edges"]) / max(len(graph["nodes"]), 1)
    print(f"Generated: {output_path}")
    print(f"  Nodes: {len(graph['nodes'])}")
    print(f"  Edges: {len(graph['edges'])} (avg {avg_edges:.1f} per node)")
    print(f"  Size:  {size_kb:.1f} KB")
    # Approximate density for large graphs
    n = len(graph["nodes"])
    max_edges = n * (n - 1)
    density = len(graph["edges"]) / max_edges if max_edges > 0 else 0
    print(f"  Density: {density:.4f}")


if __name__ == "__main__":
    main()
