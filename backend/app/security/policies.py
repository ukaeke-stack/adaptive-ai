"""Static policy helpers; no dynamic permissions in Milestone 1."""
ALLOWED_TOOL_NAMES = frozenset({"calculator"})


def is_tool_allowed(name: str) -> bool:
    return name in ALLOWED_TOOL_NAMES
