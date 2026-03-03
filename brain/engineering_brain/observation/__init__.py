"""Observation module — append-only tracking of brain interactions.

Records which rules were served, which findings were learned, and
reinforcement outcomes. This data feeds calibration and self-assessment.
"""

from engineering_brain.observation.calibrator import CalibrationBucket, ConfidenceCalibrator
from engineering_brain.observation.log import Observation, ObservationLog

__all__ = [
    "CalibrationBucket",
    "ConfidenceCalibrator",
    "Observation",
    "ObservationLog",
]
