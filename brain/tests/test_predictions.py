"""Tests for prediction fields on Rule nodes."""

from __future__ import annotations

from engineering_brain.core.brain import Brain
from engineering_brain.core.types import Rule
from engineering_brain.retrieval.formatter import format_for_llm


class TestPredictionFields:
    def test_rule_model_has_prediction_fields(self):
        rule = Rule(
            id="CR-TEST-001",
            text="Test rule",
            why="Testing",
            how_to_do_right="Do it right",
            prediction_if="CORS allowed_origins contains '*'",
            prediction_then="XSS vulnerability via cross-origin requests",
        )
        assert rule.prediction_if == "CORS allowed_origins contains '*'"
        assert rule.prediction_then == "XSS vulnerability via cross-origin requests"
        assert rule.prediction_tested_count == 0
        assert rule.prediction_success_count == 0

    def test_rule_model_defaults_empty(self):
        rule = Rule(
            id="CR-TEST-002",
            text="No prediction rule",
            why="Testing",
            how_to_do_right="Do it",
        )
        assert rule.prediction_if == ""
        assert rule.prediction_then == ""
        assert rule.prediction_tested_count == 0

    def test_rule_model_serialization(self):
        rule = Rule(
            id="CR-TEST-003",
            text="Serialization test",
            why="Testing",
            how_to_do_right="Serialize",
            prediction_if="condition",
            prediction_then="outcome",
            prediction_tested_count=5,
            prediction_success_count=4,
        )
        d = rule.model_dump(mode="json")
        assert d["prediction_if"] == "condition"
        assert d["prediction_then"] == "outcome"
        assert d["prediction_tested_count"] == 5
        assert d["prediction_success_count"] == 4


class TestPredictionFormatting:
    def test_format_with_prediction_untested(self):
        results = {
            "L3": [
                {
                    "text": "Don't use CORS *",
                    "why": "Security risk",
                    "how_to_do_right": "Use explicit origins",
                    "severity": "high",
                    "validation_status": "cross_checked",
                    "reinforcement_count": 3,
                    "prediction_if": "cors_allowed_origins == '*'",
                    "prediction_then": "XSS via cross-origin",
                    "prediction_tested_count": 0,
                    "prediction_success_count": 0,
                }
            ],
        }
        text = format_for_llm(results)
        assert "PREDICT:" in text
        assert "IF cors_allowed_origins == '*'" in text
        assert "THEN XSS via cross-origin" in text
        assert "(untested)" in text

    def test_format_with_prediction_tested(self):
        results = {
            "L3": [
                {
                    "text": "Always validate paths",
                    "why": "Path traversal",
                    "how_to_do_right": "Use is_relative_to()",
                    "severity": "critical",
                    "validation_status": "unvalidated",
                    "reinforcement_count": 0,
                    "prediction_if": "Path() / user_input without validation",
                    "prediction_then": "path traversal attack possible",
                    "prediction_tested_count": 10,
                    "prediction_success_count": 8,
                }
            ],
        }
        text = format_for_llm(results)
        assert "PREDICT:" in text
        assert "tested 8/10 = 80%" in text

    def test_format_without_prediction(self):
        results = {
            "L3": [
                {
                    "text": "Simple rule",
                    "why": "Because",
                    "how_to_do_right": "Do this",
                    "severity": "medium",
                    "validation_status": "unvalidated",
                    "reinforcement_count": 0,
                }
            ],
        }
        text = format_for_llm(results)
        assert "PREDICT:" not in text

    def test_format_partial_prediction_not_shown(self):
        """If only prediction_if is set but not prediction_then, don't show."""
        results = {
            "L3": [
                {
                    "text": "Partial prediction",
                    "why": "Why",
                    "how_to_do_right": "How",
                    "severity": "medium",
                    "validation_status": "unvalidated",
                    "prediction_if": "some condition",
                    "prediction_then": "",
                }
            ],
        }
        text = format_for_llm(results)
        assert "PREDICT:" not in text


class TestPredictionOutcomeRecording:
    def test_record_prediction_outcome_success(self):
        brain = Brain()
        rule_id = brain.add_rule(
            text="Test prediction",
            why="Testing",
            how="Do it",
            prediction_if="condition",
            prediction_then="outcome",
        )
        assert brain.record_prediction_outcome(rule_id, success=True)
        node = brain._graph.get_node(rule_id)
        assert node["prediction_tested_count"] == 1
        assert node["prediction_success_count"] == 1

    def test_record_prediction_outcome_failure(self):
        brain = Brain()
        rule_id = brain.add_rule(
            text="Test prediction fail",
            why="Testing",
            how="Do it",
            prediction_if="condition",
            prediction_then="outcome",
        )
        assert brain.record_prediction_outcome(rule_id, success=False)
        node = brain._graph.get_node(rule_id)
        assert node["prediction_tested_count"] == 1
        assert node["prediction_success_count"] == 0

    def test_record_prediction_multiple(self):
        brain = Brain()
        rule_id = brain.add_rule(
            text="Multiple predictions",
            why="Testing",
            how="Do it",
            prediction_if="x",
            prediction_then="y",
        )
        brain.record_prediction_outcome(rule_id, success=True)
        brain.record_prediction_outcome(rule_id, success=True)
        brain.record_prediction_outcome(rule_id, success=False)
        node = brain._graph.get_node(rule_id)
        assert node["prediction_tested_count"] == 3
        assert node["prediction_success_count"] == 2

    def test_record_prediction_nonexistent_rule(self):
        brain = Brain()
        assert not brain.record_prediction_outcome("CR-nonexistent", success=True)


class TestPredictionScorerSignal:
    """Prediction accuracy modifies confidence score in the scorer."""

    def test_high_accuracy_boosts_score(self):
        from engineering_brain.retrieval.scorer import score_knowledge

        base_node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 5,
            "confidence": 0.6,
        }
        # Node with high prediction accuracy
        pred_node = {
            **base_node,
            "prediction_tested_count": 10,
            "prediction_success_count": 9,  # 90% accuracy
        }
        score_base = score_knowledge(base_node, ["flask"], ["security"])
        score_pred = score_knowledge(pred_node, ["flask"], ["security"])
        assert score_pred > score_base

    def test_low_accuracy_penalizes_score(self):
        from engineering_brain.retrieval.scorer import score_knowledge

        base_node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 5,
            "confidence": 0.6,
        }
        pred_node = {
            **base_node,
            "prediction_tested_count": 10,
            "prediction_success_count": 2,  # 20% accuracy
        }
        score_base = score_knowledge(base_node, ["flask"], ["security"])
        score_pred = score_knowledge(pred_node, ["flask"], ["security"])
        assert score_pred < score_base

    def test_untested_predictions_no_effect(self):
        from engineering_brain.retrieval.scorer import score_knowledge

        base_node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 5,
            "confidence": 0.6,
        }
        pred_node = {
            **base_node,
            "prediction_tested_count": 0,
            "prediction_success_count": 0,
        }
        score_base = score_knowledge(base_node, ["flask"], ["security"])
        score_pred = score_knowledge(pred_node, ["flask"], ["security"])
        assert score_base == score_pred

    def test_few_tests_no_effect(self):
        """Below 3 tests, no accuracy signal applied."""
        from engineering_brain.retrieval.scorer import score_knowledge

        base_node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 5,
            "confidence": 0.6,
        }
        pred_node = {
            **base_node,
            "prediction_tested_count": 2,
            "prediction_success_count": 2,
        }
        score_base = score_knowledge(base_node, ["flask"], ["security"])
        score_pred = score_knowledge(pred_node, ["flask"], ["security"])
        assert score_base == score_pred


class TestPredictionBudgetEstimation:
    """Prediction text is accounted for in budget estimation."""

    def test_prediction_adds_chars(self):
        from engineering_brain.retrieval.budget import _estimate_chars

        base = {"text": "A rule", "why": "Because", "how_to_do_right": "Do this"}
        pred = {
            **base,
            "prediction_if": "some condition is met",
            "prediction_then": "something bad happens",
        }
        chars_base = _estimate_chars(base)
        chars_pred = _estimate_chars(pred)
        assert chars_pred > chars_base

    def test_no_prediction_no_extra_chars(self):
        from engineering_brain.retrieval.budget import _estimate_chars

        node = {"text": "A rule", "why": "Because"}
        chars = _estimate_chars(node)
        assert chars > 0


class TestPredictionHumanFormat:
    """Prediction fields in format_for_human."""

    def test_human_format_shows_prediction(self):
        from engineering_brain.retrieval.formatter import format_for_human

        results = {
            "L3": [
                {
                    "id": "CR-001",
                    "text": "Test rule",
                    "why": "Why",
                    "how_to_do_right": "How",
                    "severity": "high",
                    "reinforcement_count": 5,
                    "validation_status": "cross_checked",
                    "prediction_if": "condition X",
                    "prediction_then": "outcome Y",
                    "prediction_tested_count": 5,
                    "prediction_success_count": 4,
                }
            ],
        }
        text = format_for_human(results)
        assert "**Prediction**: IF condition X THEN outcome Y" in text
        assert "**Prediction Accuracy**: 4/5 (80%)" in text

    def test_human_format_untested_prediction(self):
        from engineering_brain.retrieval.formatter import format_for_human

        results = {
            "L3": [
                {
                    "id": "CR-002",
                    "text": "Test rule",
                    "why": "Why",
                    "how_to_do_right": "How",
                    "severity": "medium",
                    "reinforcement_count": 0,
                    "validation_status": "unvalidated",
                    "prediction_if": "condition",
                    "prediction_then": "outcome",
                    "prediction_tested_count": 0,
                    "prediction_success_count": 0,
                }
            ],
        }
        text = format_for_human(results)
        assert "**Prediction Accuracy**: untested" in text
