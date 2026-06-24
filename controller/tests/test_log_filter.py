import pytest
from core.log_filter import log_filter

class MockLogEntry:
    def __init__(self, message, priority=6):
        self.message = message
        self.priority = priority

def test_log_filter_empty():
    assert log_filter.is_all_routine([]) == False

def test_log_filter_all_routine():
    entries = [
        MockLogEntry("run-parts /etc/cron.hourly", priority=6),
        MockLogEntry("Executing sata_monitor.sh...", priority=6),
        MockLogEntry("pve-cluster[1234]: 数据验证成功", priority=6)
    ]
    assert log_filter.is_all_routine(entries) == True

def test_log_filter_with_unknown_benign():
    entries = [
        MockLogEntry("run-parts /etc/cron.hourly", priority=6),
        MockLogEntry("User root logged in", priority=6) # Unknown benign
    ]
    assert log_filter.is_all_routine(entries) == False

def test_log_filter_exemption_mechanism():
    entries = [
        MockLogEntry("run-parts /etc/cron.hourly", priority=6),
        MockLogEntry("pve-cluster[1234]: 数据验证成功", priority=3) # High priority error!
    ]
    assert log_filter.is_all_routine(entries) == False

def test_log_filter_no_priority_attribute():
    class MissingPriorityEntry:
        def __init__(self, message):
            self.message = message
    
    entries = [
        MissingPriorityEntry("run-parts /etc/cron.hourly"),
    ]
    assert log_filter.is_all_routine(entries) == True
