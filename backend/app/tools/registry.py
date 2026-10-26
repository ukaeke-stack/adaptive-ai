from app.security.policies import is_tool_allowed
from app.tools.builtin.calculator import run_calculator
from app.tools.builtin.text_tools import EXTENDED_ACTIONS, execute_extended

_TOOL_HANDLERS = {"calculator": run_calculator}
_TOOL_DESCRIPTIONS = {"calculator": "Perform basic arithmetic on two numbers."}


def _extended_handler(action_name: str):
    """Create a fixed-name adapter to the bounded deterministic text-tool executor."""
    def run(arguments: dict):
        # The registry key is authoritative; callers cannot override the action.
        result = execute_extended({**arguments, "action": action_name})
        if result is None:
            raise ValueError("Unknown extended action.")
        if result.get("status") == "failed":
            raise ValueError(result.get("message", "Tool execution failed."))
        return result
    return run


for _name in sorted(EXTENDED_ACTIONS):
    _TOOL_HANDLERS[_name] = _extended_handler(_name)
    _TOOL_DESCRIPTIONS[_name] = _name.replace("_", " ").capitalize() + " using bounded local processing."


def list_tools():
    return [
        {"name": name, "description": _TOOL_DESCRIPTIONS[name], "status": "implemented"}
        for name in _TOOL_HANDLERS if is_tool_allowed(name)
    ]


def get_tool(name: str):
    if not is_tool_allowed(name):
        return None
    return _TOOL_HANDLERS.get(name)
