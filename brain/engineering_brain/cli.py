"""CLI for the Engineering Knowledge Brain.

Usage:
    PYTHONPATH=src python -m engineering_brain stats
    PYTHONPATH=src python -m engineering_brain query "Flask CORS WebSocket"
    PYTHONPATH=src python -m engineering_brain validate --all
    PYTHONPATH=src python -m engineering_brain validate --id CR-SEC-CORS-001
    PYTHONPATH=src python -m engineering_brain validate --all --dry-run
    PYTHONPATH=src python -m engineering_brain validate --all --force-refresh
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="engineering_brain",
        description="Engineering Knowledge Brain — query, validate, and manage knowledge",
    )
    sub = parser.add_subparsers(dest="command")

    # stats
    sub.add_parser("stats", help="Show brain statistics")

    # query
    q_parser = sub.add_parser("query", help="Query knowledge for a task")
    q_parser.add_argument("task", help="Task description")
    q_parser.add_argument("--techs", nargs="*", default=[], help="Technologies")
    q_parser.add_argument("--domains", nargs="*", default=[], help="Domains")
    q_parser.add_argument("--budget", type=int, default=0, help="Budget chars")
    q_parser.add_argument("--human", action="store_true", help="Human-readable format")

    # validate
    v_parser = sub.add_parser("validate", help="Validate knowledge against sources")
    v_group = v_parser.add_mutually_exclusive_group(required=True)
    v_group.add_argument(
        "--all", action="store_true", dest="validate_all", help="Validate all nodes"
    )
    v_group.add_argument("--id", dest="node_id", help="Validate a single node by ID")
    v_group.add_argument("--layer", help="Validate a layer (L0, L1, L2, L3)")
    v_parser.add_argument("--dry-run", action="store_true", help="Plan only, no API calls")
    v_parser.add_argument("--force-refresh", action="store_true", help="Ignore cache")
    v_parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "stats":
        _cmd_stats()
    elif args.command == "query":
        _cmd_query(args)
    elif args.command == "validate":
        _cmd_validate(args)


def _cmd_stats() -> None:
    """Show brain statistics with validation coverage."""
    from engineering_brain.core.brain import Brain

    brain = Brain()
    brain.seed()
    stats = brain.stats()

    print("=" * 60)
    print("  Engineering Knowledge Brain — Statistics")
    print("=" * 60)
    print()

    layers = stats.get("layers", {})
    total = stats.get("total", 0)
    for name, count in layers.items():
        print(f"  {name:15s}  {count:5d}")
    print(f"  {'TOTAL':15s}  {total:5d}")
    print()

    # Validation coverage
    all_nodes_map = brain._graph.get_all_nodes()
    nodes = list(all_nodes_map.values()) if isinstance(all_nodes_map, dict) else all_nodes_map
    status_counts: dict[str, int] = {}
    for node in nodes:
        status = node.get("validation_status", "unvalidated")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("  Validation Coverage:")
    for status, count in sorted(status_counts.items()):
        pct = 100 * count / max(total, 1)
        print(f"    {status:20s}  {count:5d}  ({pct:.1f}%)")
    print()

    config = stats.get("config", {})
    print(f"  Adapter: {config.get('adapter', 'memory')}")
    print(f"  Budget:  {config.get('budget_chars', 0)} chars")
    print()


def _cmd_query(args: argparse.Namespace) -> None:
    """Query the brain."""
    from engineering_brain.core.brain import Brain

    brain = Brain()
    brain.seed()

    budget = args.budget if args.budget > 0 else None
    result = brain.query(
        task_description=args.task,
        technologies=args.techs,
        domains=args.domains,
        budget_chars=budget,
    )

    if args.human:
        from engineering_brain.retrieval.formatter import format_for_human

        text = format_for_human(result.results_by_layer)
    else:
        text = result.formatted_text

    print(text)
    print(f"\n--- {result.total_nodes} nodes, {len(result.formatted_text)} chars ---")


def _cmd_validate(args: argparse.Namespace) -> None:
    """Validate knowledge against external sources."""
    from engineering_brain.core.brain import Brain

    brain = Brain()
    brain.seed()

    start = time.monotonic()

    def progress(completed: int, total: int) -> None:
        pct = 100 * completed / max(total, 1)
        print(f"\r  Validating... {completed}/{total} ({pct:.0f}%)", end="", flush=True)

    if args.node_id:
        # Single node validation
        result = asyncio.run(brain.validate(node_id=args.node_id, force_refresh=args.force_refresh))
        elapsed = time.monotonic() - start
        if args.json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\n  Node: {args.node_id}")
            print(f"  Status: {result.get('validation_status', 'unknown')}")
            print(f"  Sources: {len(result.get('sources', []))}")
            for src in result.get("sources", []):
                if isinstance(src, dict):
                    print(
                        f"    - [{src.get('source_type', '')}] {src.get('title', '')} — {src.get('url', '')}"
                    )
            print(f"  Time: {elapsed:.1f}s")
    else:
        # Batch validation
        layer_filter = args.layer or ""
        report = asyncio.run(
            brain.validate(
                force_refresh=args.force_refresh,
                dry_run=args.dry_run,
                layer_filter=layer_filter,
                progress_callback=None if args.json_output else progress,
            )
        )

        elapsed = time.monotonic() - start

        if args.json_output:
            print(
                json.dumps(
                    {
                        "total_nodes": report.total_nodes,
                        "validated": report.validated,
                        "cache_hits": report.cache_hits,
                        "api_calls": report.api_calls,
                        "errors": report.errors,
                        "by_status": report.by_status,
                        "by_checker": report.by_checker,
                        "elapsed_seconds": report.elapsed_seconds,
                    },
                    indent=2,
                    default=str,
                )
            )
        else:
            print()
            print()
            print(report.summary())
            print(f"\n  Elapsed: {elapsed:.1f}s")
            print()
