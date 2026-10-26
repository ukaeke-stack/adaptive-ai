"""Static allowlist policy for deterministic, bounded tool handlers."""
from app.tools.builtin.text_tools import EXTENDED_ACTIONS
ALLOWED_TOOL_NAMES = frozenset({"calculator"}) | frozenset(EXTENDED_ACTIONS)
def is_tool_allowed(name: str) -> bool:
    return name in ALLOWED_TOOL_NAMES
