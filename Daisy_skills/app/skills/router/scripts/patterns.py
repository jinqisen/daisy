from typing import List

# Default patterns for FAST path
# These cover simple greetings, acknowledgments, and short navigational queries
DEFAULT_FAST_PATTERNS: List[str] = [
    r"^(hi|hello|hey|你好|您好|早|早安|晚安)$",
    r"^(ok|okay|好的|收到|嗯|哦)$",
    r"^(谢谢|thanks|thank you)$",
    r"^(再见|bye|goodbye|拜拜)$",
    r"^(help|帮助)$"
]

class PatternManager:
    def __init__(self):
        self._patterns = list(DEFAULT_FAST_PATTERNS)
    
    def get_patterns(self) -> List[str]:
        return list(self._patterns)
    
    def update_patterns(self, new_patterns: List[str]) -> int:
        self._patterns = list(new_patterns)
        return len(self._patterns)

pattern_manager = PatternManager()
