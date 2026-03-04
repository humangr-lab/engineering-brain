# Evidence Roadmap: Items Requiring Production Usage

These items were identified by expert review as necessary for "true SOTA" status.
They require real-world production data that cannot be fabricated or simulated.

---

## 7. Real Seniority Metrics

**Status**: BLOCKED — Requires production deployments with team metrics access

**What it proves**: That the Engineering Brain measurably improves engineering outcomes, not just retrieval quality.

**Metrics to measure**:
- Bug rate (before vs after Brain adoption)
- Security findings per sprint
- Rework percentage (changes after review)
- Time from PR open to merge
- Production incident rate and MTTR

**Criteria to unblock**:
- [ ] 3+ engineering teams using Engineering Brain in daily workflow for 30+ days
- [ ] Access to team metrics systems (bug tracker, CI/CD, PR platform)
- [ ] Baseline metrics collected for 30+ days before Brain adoption
- [ ] Privacy/consent approval for developer productivity measurement

**Measurement plan**: A/B study with matched team pairs (similar experience, similar codebases). Track metrics for 60 days with Brain vs 60 days without. Report with 95% confidence intervals.

---

## 8. Case Studies (Before/After)

**Status**: BLOCKED — Requires real project completions

**What it proves**: Concrete, auditable evidence that the Brain transforms engineering quality in real projects.

**Deliverable**: 2-3 case studies with:
- Project description and team composition
- Measurable before/after metrics (code quality scores, review time, incident count)
- Qualitative team feedback
- Timeline (weeks/months of usage)

**Criteria to unblock**:
- [ ] 1+ team completes a full project (inception to production) with Brain integration
- [ ] Code quality metrics available from static analysis tools (SonarQube, CodeClimate, etc.)
- [ ] Team agrees to publish anonymized results

**Measurement plan**: Collect metrics at project start, midpoint, and completion. Compare against team's historical baseline on similar projects.

---

## 9. Curadoria com Governanca Forte (Curation with Strong Governance)

**Status**: PARTIALLY BLOCKED — Infrastructure can be built now, proof requires scale

**What it proves**: The knowledge base maintains quality as it grows with multiple contributors.

**Components**:
- Owner per knowledge domain
- Expert review workflow for new/modified rules
- Rule versioning with deprecation protocol
- Audit trail for all knowledge changes

**Criteria to unblock**:
- [ ] 3+ domain experts contributing knowledge across different areas
- [ ] 50+ knowledge modifications tracked through the governance workflow
- [ ] 0 governance-bypass incidents over 30-day period
- [ ] Knowledge quality audit shows no degradation after 100+ contributions

**What we CAN build now**:
- [ ] Domain owner registry (YAML-based, per knowledge domain)
- [ ] Review gate for seed file modifications (GitHub CODEOWNERS + CI check)
- [ ] Deprecation protocol (soft-deprecate -> quarantine -> remove lifecycle)
- [ ] Audit log integration with observation system

---

## 10. Freshness e Validade Continua (Freshness & Continuous Validity)

**Status**: PARTIALLY BLOCKED — Mechanisms can be built, proof requires time

**What it proves**: The Brain detects and handles obsolete knowledge automatically.

**Components**:
- Staleness detection (rules referencing deprecated APIs/versions)
- Automatic revalidation against external sources
- Quarantine for knowledge with expired validity
- Freshness score per rule (time since last validation)

**Criteria to unblock**:
- [ ] Staleness detection correctly identifies 90%+ of known-obsolete rules in a test set
- [ ] Revalidation pipeline runs automatically on schedule (weekly)
- [ ] 6+ months of continuous operation demonstrating freshness maintenance
- [ ] Zero production incidents caused by stale knowledge

**What we CAN build now**:
- [ ] Predictive decay model (already in `predictive_decay.py`, needs validation data)
- [ ] External source validators (already in `validation/checkers/`, needs scheduler)
- [ ] Freshness dashboard (age distribution, last-validated timestamps)
- [ ] Quarantine workflow integration with the epistemic ladder

---

## Timeline

| Item | Can build infrastructure now? | Needs production data? | Estimated time to evidence |
|------|-------------------------------|------------------------|---------------------------|
| 7. Seniority metrics | No | Yes — teams using Brain | 3-6 months after adoption |
| 8. Case studies | No | Yes — project completions | 2-4 months after adoption |
| 9. Governance | Yes (partial) | Yes — multiple contributors | 1-3 months after contributors |
| 10. Freshness | Yes (partial) | Yes — time passage | 6+ months of operation |

---

*Document maintained by HuGR Engineering. Last updated: 2026-03-04.*
