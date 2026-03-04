"""CLI for the HuGR Engineering Brain Benchmark Framework.

Usage:
    python -m benchmarks run                        # Full benchmark
    python -m benchmarks run --systems brain,rag    # Specific systems
    python -m benchmarks ablation                   # Full ablation study
    python -m benchmarks ablation --group gaps      # Ablation for one group
    python -m benchmarks robustness                 # Robustness evaluation
    python -m benchmarks cost                       # Cost/benefit analysis
    python -m benchmarks report                     # Generate PDF from last results
    python -m benchmarks compare run1.json run2.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger("benchmarks")

REPORTS_DIR = Path(__file__).parent / "reports"

SYSTEM_REGISTRY = {
    "brain": "baselines.brain_system.BrainSystem",
    "naive_rag": "baselines.naive_rag.NaiveRAGSystem",
    "raw_llm": "baselines.raw_llm.RawLLMSystem",
    "graph_rag": "baselines.graph_rag.GraphRAGSystem",
}


def _resolve_systems(names: str) -> list:
    """Dynamically import and instantiate baseline systems."""
    import importlib

    if names == "all":
        keys = list(SYSTEM_REGISTRY.keys())
    else:
        keys = [k.strip() for k in names.split(",")]

    systems = []
    for key in keys:
        module_path = SYSTEM_REGISTRY.get(key)
        if not module_path:
            logger.warning("Unknown system: %s (skipping)", key)
            continue
        mod_name, cls_name = module_path.rsplit(".", 1)
        try:
            mod = importlib.import_module(f".{mod_name}", package="benchmarks")
            cls = getattr(mod, cls_name)
            instance = cls()
            systems.append(instance)
        except Exception as exc:
            logger.warning("Failed to load %s: %s (skipping)", key, exc)
    return systems


def cmd_run(args: argparse.Namespace) -> None:
    """Run benchmark suite."""
    from .runner import BenchmarkRunner

    systems = _resolve_systems(args.systems)
    if not systems:
        logger.error("No systems loaded. Check --systems flag.")
        sys.exit(1)

    runner = BenchmarkRunner(
        systems=systems,
        dataset_path=args.dataset,
        output_dir=args.output or str(REPORTS_DIR),
    )
    results = runner.run(
        categories=args.category,
        difficulties=args.difficulty,
        k=args.k,
    )

    if not args.no_report:
        try:
            from .report_generator import ReportGenerator

            gen = ReportGenerator(results, output_dir=args.output or str(REPORTS_DIR))
            pdf_path = gen.generate()
            logger.info("PDF report: %s", pdf_path)
        except ImportError as exc:
            logger.warning("Report generation skipped (missing deps): %s", exc)

    # Print summary
    print("\n=== Benchmark Results ===")
    for name, sr in results.systems.items():
        agg = sr.aggregate
        print(f"\n  {name}:")
        print(f"    NDCG@10  = {agg.avg_ndcg_at_10:.4f}")
        print(f"    MRR      = {agg.avg_mrr:.4f}")
        print(f"    Recall@10= {agg.avg_recall_at_10:.4f}")
        print(f"    MAP      = {agg.avg_map:.4f}")
        print(f"    F1@10    = {agg.avg_f1_at_10:.4f}")
        print(f"    Latency  = {agg.avg_latency_ms:.1f}ms (p95: {agg.p95_latency_ms:.1f}ms)")


def cmd_ablation(args: argparse.Namespace) -> None:
    """Run ablation study."""
    from .ablation.ablation_runner import AblationRunner

    runner = AblationRunner(dataset_path=args.dataset)
    if args.flags:
        results = runner.run_specific_flags(args.flags)
    elif args.group:
        results = runner.run_group_ablation(args.group)
    else:
        results = runner.run_full_ablation()

    print("\n=== Ablation Study ===")
    print(f"{'Flag':<40} {'Group':<12} {'NDCG Delta':>11} {'MRR Delta':>10}")
    print("-" * 75)
    for r in sorted(results, key=lambda x: abs(x.delta_ndcg), reverse=True):
        sign = "+" if r.delta_ndcg >= 0 else ""
        print(f"  {r.flag_name:<38} {r.group:<12} {sign}{r.delta_ndcg:>10.4f} {sign}{r.delta_mrr:>9.4f}")


def cmd_robustness(args: argparse.Namespace) -> None:
    """Run robustness evaluation."""
    from .robustness.robustness_runner import RobustnessRunner

    runner = RobustnessRunner()
    scenarios = args.scenario or ["conflicting", "obsolete", "biased"]
    results = runner.run(scenarios=scenarios)

    print("\n=== Robustness Evaluation ===")
    for r in results:
        print(f"\n  {r.scenario}:")
        print(f"    Injected:      {r.injected_count}")
        print(f"    Contamination: {r.contamination_rate:.2%}")
        print(f"    Detection:     {r.detection_rate:.2%}")
        print(f"    NDCG Degrad:   {r.degradation_pct:+.2%}")
        print(f"    Resilience:    {r.resilience_score:.4f}")


def cmd_cost(args: argparse.Namespace) -> None:
    """Run cost/benefit analysis."""
    from .cost.cost_analyzer import CostAnalyzer

    analyzer = CostAnalyzer()
    results = analyzer.run()

    print("\n=== Cost/Benefit Analysis ===")
    print(f"{'System':<25} {'Latency p50':>12} {'p95':>8} {'Tokens/q':>10} {'Memory':>10}")
    print("-" * 67)
    for r in results:
        print(
            f"  {r.system_name:<23} {r.median_latency_ms:>10.1f}ms "
            f"{r.p95_latency_ms:>6.1f}ms {r.avg_tokens_per_query:>9.0f} "
            f"{r.peak_memory_mb:>8.1f}MB"
        )


def cmd_report(args: argparse.Namespace) -> None:
    """Generate PDF report from existing results."""
    from .report_generator import ReportGenerator
    from .results import BenchmarkResults

    input_path = args.input or str(REPORTS_DIR / "latest.json")
    results = BenchmarkResults.from_json(input_path)
    gen = ReportGenerator(
        results,
        output_dir=args.output or str(REPORTS_DIR),
    )
    pdf_path = gen.generate(dark=args.dark)
    print(f"Report generated: {pdf_path}")


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare two benchmark runs."""
    from .results import BenchmarkResults

    r1 = BenchmarkResults.from_json(args.run1)
    r2 = BenchmarkResults.from_json(args.run2)

    print("\n=== Benchmark Comparison ===")
    print(f"  Run 1: {args.run1}")
    print(f"  Run 2: {args.run2}")

    common = set(r1.systems.keys()) & set(r2.systems.keys())
    regressions = False
    for name in sorted(common):
        a1 = r1.systems[name].aggregate
        a2 = r2.systems[name].aggregate
        d_ndcg = a2.avg_ndcg_at_10 - a1.avg_ndcg_at_10
        d_mrr = a2.avg_mrr - a1.avg_mrr
        d_lat = a2.avg_latency_ms - a1.avg_latency_ms
        print(f"\n  {name}:")
        print(f"    NDCG@10:  {a1.avg_ndcg_at_10:.4f} -> {a2.avg_ndcg_at_10:.4f}  ({d_ndcg:+.4f})")
        print(f"    MRR:      {a1.avg_mrr:.4f} -> {a2.avg_mrr:.4f}  ({d_mrr:+.4f})")
        print(f"    Latency:  {a1.avg_latency_ms:.1f} -> {a2.avg_latency_ms:.1f}ms  ({d_lat:+.1f}ms)")
        if d_ndcg < -0.01:
            print(f"    ** REGRESSION: NDCG dropped {abs(d_ndcg):.4f} **")
            regressions = True
        if d_mrr < -0.02:
            print(f"    ** REGRESSION: MRR dropped {abs(d_mrr):.4f} **")
            regressions = True

    if regressions:
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        prog="benchmarks",
        description="HuGR Engineering Brain — Benchmark & Evaluation Framework",
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Run benchmark suite")
    p_run.add_argument("--systems", default="all", help="Comma-separated: brain,naive_rag,raw_llm,graph_rag")
    p_run.add_argument("--category", nargs="*", default=None)
    p_run.add_argument("--difficulty", nargs="*", default=None)
    p_run.add_argument("--dataset", default=None, help="Dataset YAML path")
    p_run.add_argument("--k", type=int, default=10)
    p_run.add_argument("--output", default=None, help="Output directory")
    p_run.add_argument("--no-report", action="store_true", help="Skip PDF generation")
    p_run.set_defaults(func=cmd_run)

    # ablation
    p_abl = sub.add_parser("ablation", help="Run ablation study")
    p_abl.add_argument("--group", default=None, help="scoring|retrieval|epistemic|llm|gaps|maintenance")
    p_abl.add_argument("--flags", nargs="*", default=None, help="Specific flag names")
    p_abl.add_argument("--dataset", default=None)
    p_abl.set_defaults(func=cmd_ablation)

    # robustness
    p_rob = sub.add_parser("robustness", help="Run robustness evaluation")
    p_rob.add_argument("--scenario", nargs="*", default=None)
    p_rob.set_defaults(func=cmd_robustness)

    # cost
    p_cost = sub.add_parser("cost", help="Run cost/benefit analysis")
    p_cost.set_defaults(func=cmd_cost)

    # report
    p_rep = sub.add_parser("report", help="Generate PDF report")
    p_rep.add_argument("--input", default=None, help="Results JSON path")
    p_rep.add_argument("--output", default=None, help="Output directory")
    p_rep.add_argument("--dark", action="store_true", help="Dark theme charts")
    p_rep.set_defaults(func=cmd_report)

    # compare
    p_cmp = sub.add_parser("compare", help="Compare two benchmark runs")
    p_cmp.add_argument("run1", help="First results JSON")
    p_cmp.add_argument("run2", help="Second results JSON")
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
