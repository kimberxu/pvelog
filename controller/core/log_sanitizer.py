import re

class LogSanitizer:
    def __init__(self):
        self.dangerous_patterns = [
            re.compile(r"ignore previous instructions", re.IGNORECASE),
            re.compile(r"system prompt", re.IGNORECASE),
            re.compile(r"you are now", re.IGNORECASE),
            re.compile(r"```"),
            re.compile(r"\$\(.*\)"), 
            re.compile(r"`.*`"), 
        ]

    def sanitize(self, message: str) -> str:
        sanitized = message
        for pattern in self.dangerous_patterns:
            sanitized = pattern.sub("[SANITIZED]", sanitized)
        
        # Limit length to prevent context window exhaustion attacks
        if len(sanitized) > 2000:
            sanitized = sanitized[:2000] + "...[TRUNCATED]"
            
        return sanitized

log_sanitizer = LogSanitizer()
