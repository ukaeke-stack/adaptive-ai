from app.security.policies import is_tool_allowed
from app.tools.builtin.calculator import run_calculator

_TOOL_HANDLERS = {"calculator": run_calculator}
_TOOL_DESCRIPTIONS = {"calculator": "Perform basic arithmetic on two numbers."}


def list_tools():
    return [{"name": name, "description": _TOOL_DESCRIPTIONS[name]} for name in _TOOL_HANDLERS if is_tool_allowed(name)]


def get_tool(name: str):
    if not is_tool_allowed(name):
        return None
    return _TOOL_HANDLERS.get(name)
