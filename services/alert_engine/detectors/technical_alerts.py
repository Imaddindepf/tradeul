"""
Technical Alert Detector - Legacy stub.
MACD logic migrated to macd_alerts.py (multi-timeframe).
Stochastic logic migrated to stochastic_alerts.py (multi-timeframe).
"""

from typing import Optional, List
from detectors.base import BaseAlertDetector
from models.alert_state import AlertState
from models.alert_record import AlertRecord


class TechnicalAlertDetector(BaseAlertDetector):

    def detect(self, current: AlertState, previous: Optional[AlertState]) -> List[AlertRecord]:
        return []
