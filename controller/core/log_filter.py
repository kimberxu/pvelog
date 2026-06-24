import re
from typing import List, Any

class LogFilter:
    def __init__(self):
        # syslog priorities: 0=emerg, 1=alert, 2=crit, 3=err, 4=warning
        self.alert_priorities = {0, 1, 2, 3, 4}
        
        # Regular expressions for known benign logs
        self.benign_patterns = [
            re.compile(r"/etc/cron\.hourly", re.IGNORECASE),
            re.compile(r"sata_monitor\.sh", re.IGNORECASE),
            re.compile(r"pve-cluster.*数据验证成功", re.IGNORECASE),
            re.compile(r"pve-cluster.*successful data validation", re.IGNORECASE)
        ]

    def is_all_routine(self, entries: List[Any]) -> bool:
        """
        Check if a batch of logs consists entirely of known routine operations.
        Returns True if ALL logs are routine and low priority, False otherwise.
        """
        if not entries:
            return False
            
        for entry in entries:
            # 1. Exemption mechanism: if it's a Warning or Error, do NOT filter
            priority = getattr(entry, "priority", 6)  # Default to info if missing
            if priority in self.alert_priorities:
                return False
                
            # 2. Check if message matches any benign pattern
            message = getattr(entry, "message", "")
            is_benign = False
            for pattern in self.benign_patterns:
                if pattern.search(message):
                    is_benign = True
                    break
                    
            if not is_benign:
                # If we find even one log that is NOT explicitly benign, we must analyze the batch
                return False
                
        return True

log_filter = LogFilter()
