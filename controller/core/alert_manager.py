import datetime
from typing import Dict

class AlertManager:
    def __init__(self, cooldown_minutes: int = 60):
        self.cooldown_minutes = cooldown_minutes
        self.last_alert_time: Dict[str, datetime.datetime] = {}

    def should_alert(self, node_id: str, severity: str) -> bool:
        if severity not in ["ERROR", "CRITICAL"]:
            return False
            
        now = datetime.datetime.utcnow()
        if node_id in self.last_alert_time:
            time_since_last = now - self.last_alert_time[node_id]
            if time_since_last.total_seconds() < self.cooldown_minutes * 60:
                return False
                
        self.last_alert_time[node_id] = now
        return True

    def send_alert(self, node_id: str, report: str, severity: str):
        # Placeholder for actual email sending logic
        print(f"[ALERT] {severity} alert for Node {node_id}: \n{report}")
        # In a real scenario, this calls email_service.send_email(...)

alert_manager = AlertManager()
