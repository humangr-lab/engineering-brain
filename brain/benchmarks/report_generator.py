"""Generates publication-quality PDF reports from benchmark results.

Pipeline: BenchmarkResults -> Charts (matplotlib) -> Jinja2 HTML -> WeasyPrint PDF
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .results import AblationResult, BenchmarkResults, CostProfile, RobustnessScenarioResult

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ASSETS_DIR = Path(__file__).parent / "assets"


class ReportGenerator:
    """Produces branded PDF benchmark reports."""

    def __init__(
        self,
        results: BenchmarkResults,
        output_dir: str | None = None,
    ) -> None:
        self._results = results
        self._output_dir = Path(output_dir or str(Path(__file__).parent / "reports"))
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    def generate(
        self,
        filename: str | None = None,
        dark: bool = False,
    ) -> Path:
        """Generate full benchmark report PDF."""
        if filename is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_report_{ts}.pdf"

        charts = self._generate_charts(dark)
        context = self._build_context(charts)
        html = self._render_html(context)

        # Try PDF generation via WeasyPrint; fall back to HTML
        pdf_path = self._output_dir / filename
        self._output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from weasyprint import HTML

            HTML(string=html, base_url=str(_ASSETS_DIR)).write_pdf(str(pdf_path))
            logger.info("PDF report generated: %s", pdf_path)
        except ImportError:
            # Fall back to HTML output
            html_path = pdf_path.with_suffix(".html")
            html_path.write_text(html, encoding="utf-8")
            logger.warning("WeasyPrint not installed — HTML report saved: %s", html_path)
            return html_path

        return pdf_path

    def _generate_charts(self, dark: bool) -> dict[str, str]:
        """Generate all charts and return as {name: base64_png}."""
        charts: dict[str, str] = {}

        try:
            from .charts.comparison import bar_comparison, category_heatmap, radar_comparison

            charts["comparison_bar"] = bar_comparison(self._results, dark)
            charts["comparison_radar"] = radar_comparison(self._results, dark)
            charts["category_heatmap"] = category_heatmap(self._results, dark)
        except Exception as exc:
            logger.warning("Comparison charts failed: %s", exc)

        if self._results.ablation:
            try:
                from .charts.ablation import heatmap_flags, waterfall_impact

                charts["ablation_waterfall"] = waterfall_impact(self._results.ablation, dark)
                charts["ablation_heatmap"] = heatmap_flags(self._results.ablation, dark)
            except Exception as exc:
                logger.warning("Ablation charts failed: %s", exc)

        if self._results.robustness:
            try:
                from .charts.robustness import degradation_chart

                charts["robustness_degradation"] = degradation_chart(self._results.robustness, dark)
            except Exception as exc:
                logger.warning("Robustness charts failed: %s", exc)

        if self._results.cost:
            try:
                from .charts.cost import latency_comparison, quality_vs_cost

                charts["latency_comparison"] = latency_comparison(self._results.cost, dark)
                charts["quality_vs_cost"] = quality_vs_cost(self._results, self._results.cost, dark)
            except Exception as exc:
                logger.warning("Cost charts failed: %s", exc)

        return charts

    def _build_context(self, charts: dict[str, str]) -> dict:
        """Build the Jinja2 template context."""
        systems = self._results.systems
        primary = next(iter(systems.values())) if systems else None

        # Logo as base64 data URI
        logo_path = _ASSETS_DIR / "hugr-logo-dark.svg"
        logo_base64 = ""
        if logo_path.exists():
            svg_data = logo_path.read_text(encoding="utf-8")
            b64 = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
            logo_base64 = f"data:image/svg+xml;base64,{b64}"

        # CSS
        css_path = _ASSETS_DIR / "report.css"
        css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

        # Determine winner
        winner = ""
        winner_metrics = 0
        if len(systems) > 1:
            metric_keys = ["avg_ndcg_at_10", "avg_mrr", "avg_recall_at_10", "avg_map", "avg_f1_at_10"]
            wins: dict[str, int] = {}
            for key in metric_keys:
                best_name = max(systems.keys(), key=lambda n: getattr(systems[n].aggregate, key, 0))
                wins[best_name] = wins.get(best_name, 0) + 1
            winner = max(wins.keys(), key=lambda n: wins[n])
            winner_metrics = wins[winner]

        # Executive summary cards
        executive_cards = []
        if primary:
            agg = primary.aggregate
            executive_cards = [
                {"label": "NDCG@10", "value": f"{agg.avg_ndcg_at_10:.4f}", "delta": None, "delta_class": ""},
                {"label": "MRR", "value": f"{agg.avg_mrr:.4f}", "delta": None, "delta_class": ""},
                {"label": "Recall@10", "value": f"{agg.avg_recall_at_10:.4f}", "delta": None, "delta_class": ""},
                {"label": "MAP", "value": f"{agg.avg_map:.4f}", "delta": None, "delta_class": ""},
            ]

        # Key findings
        key_findings = self._generate_findings()

        # Systems info for methodology
        systems_info = [
            {"name": sr.system_name, "description": sr.system_description}
            for sr in systems.values()
        ]

        # Categories
        all_cats: set[str] = set()
        for sr in systems.values():
            all_cats.update(sr.per_category.keys())
        categories = sorted(all_cats)

        # Per-query results for appendix
        per_query_results = primary.queries if primary else []

        context = {
            # Global
            "css": css,
            "logo_base64": logo_base64,
            "date": time.strftime("%Y-%m-%d %H:%M UTC"),
            "dataset_version": self._results.dataset_version,
            "total_queries": sum(sr.aggregate.count for sr in systems.values()) // max(len(systems), 1),
            "total_systems": len(systems),
            "charts": charts,
            # Cover
            # Executive
            "executive_cards": executive_cards,
            "key_findings": key_findings,
            "winner": winner,
            "winner_metrics": winner_metrics,
            "total_metrics": 5,
            # Methodology
            "systems_info": systems_info,
            "categories": categories,
            # Comparison
            "systems": systems,
            "seed_count": "3,700+",
            "layer_count": 6,
            # Ablation
            "ablation_results": self._results.ablation,
            "ablation_top10": sorted(self._results.ablation or [], key=lambda r: abs(r.delta_ndcg), reverse=True)[:10],
            # Robustness
            "robustness_results": self._results.robustness,
            # Cost
            "cost_profiles": self._results.cost,
            # Appendix
            "primary_system": primary.system_name if primary else "",
            "per_query_results": per_query_results,
        }

        return context

    def _render_html(self, context: dict) -> str:
        """Render the report template with context."""
        template = self._env.get_template("report_base.html.j2")
        return template.render(**context)

    def _generate_findings(self) -> list[str]:
        """Generate key findings from results."""
        findings: list[str] = []
        systems = self._results.systems

        if not systems:
            return ["No systems evaluated."]

        # Compare systems
        names = list(systems.keys())
        if len(names) >= 2:
            best = max(names, key=lambda n: systems[n].aggregate.avg_ndcg_at_10)
            worst = min(names, key=lambda n: systems[n].aggregate.avg_ndcg_at_10)
            delta = systems[best].aggregate.avg_ndcg_at_10 - systems[worst].aggregate.avg_ndcg_at_10
            findings.append(
                f"<strong>{best}</strong> outperforms <strong>{worst}</strong> by "
                f"{delta:.4f} NDCG@10 ({delta * 100:.1f}% improvement)."
            )

        # Best category
        primary = systems[names[0]]
        if primary.per_category:
            best_cat = max(primary.per_category.keys(), key=lambda c: primary.per_category[c].avg_ndcg_at_10)
            findings.append(
                f"Strongest category: <strong>{best_cat.replace('_', ' ').title()}</strong> "
                f"(NDCG@10 = {primary.per_category[best_cat].avg_ndcg_at_10:.4f})."
            )

        # Latency
        if primary.aggregate.avg_latency_ms > 0:
            findings.append(
                f"Average query latency: <strong>{primary.aggregate.avg_latency_ms:.1f}ms</strong> "
                f"(p95: {primary.aggregate.p95_latency_ms:.1f}ms)."
            )

        # Ablation summary
        if self._results.ablation:
            impactful = [r for r in self._results.ablation if abs(r.delta_ndcg) > 0.001]
            if impactful:
                top = max(impactful, key=lambda r: abs(r.delta_ndcg))
                findings.append(
                    f"Most impactful feature: <strong>{top.flag_name}</strong> "
                    f"(NDCG delta: {top.delta_ndcg:+.4f} when disabled)."
                )

        # Robustness summary
        if self._results.robustness:
            avg_resilience = sum(r.resilience_score for r in self._results.robustness) / len(self._results.robustness)
            findings.append(f"Average resilience score: <strong>{avg_resilience:.3f}</strong> across adversarial scenarios.")

        return findings
