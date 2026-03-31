from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict
from models.alert_record import AlertRecord

class AlertStore:
    def __init__(self, max_age_seconds=3600, max_alerts=10000):
        self._alerts: List[AlertRecord] = []
        self._by_symbol: Dict[str, List[AlertRecord]] = defaultdict(list)
        self._max_age = max_age_seconds
        self._max_alerts = max_alerts

    def add(self, alert):
        self._alerts.append(alert)
        self._by_symbol[alert.symbol].append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

    def get_recent(self, limit=100):
        return self._alerts[-limit:]

    def cleanup_old(self):
        cutoff = datetime.utcnow() - timedelta(seconds=self._max_age)
        old = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.timestamp >= cutoff]
        return old - len(self._alerts)

    @property
    def size(self):
        return len(self._alerts)
