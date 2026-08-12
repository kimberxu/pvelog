import datetime

class AlertManager:
    def __init__(self, cooldown_minutes: int = 60):
        self.cooldown_minutes = cooldown_minutes

    def send_alert(self, node_id: str, report: str, severity: str):
        from services.email_service import send_email
        subject = f"[PVE-AIOps] {severity} Alert for Node {node_id}"
        body = f"An anomaly was detected on Node {node_id}:\n\nSeverity: {severity}\n\nReport:\n{report}"
        print(f"[ALERT] Triggering email for {severity} alert on Node {node_id}")
        send_email(subject=subject, body=body)

alert_manager = AlertManager()
