"""Safe plugin proposal validation. Generated code is never executed here."""
import ast
import hashlib
import re

MAX_SOURCE_CHARS = 12000
_ALLOWED_NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Expr, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.If, ast.For, ast.List, ast.Tuple, ast.Dict, ast.Subscript, ast.Slice, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.IfExp, ast.Pass, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)
_BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "getattr", "setattr", "delattr", "input", "breakpoint"}
_ALLOWED_BUILTINS = {"abs", "min", "max", "sum", "round", "len", "range", "sorted"}

def validate_plugin(name: str, source: str) -> dict:
    name = name.strip()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,47}", name):
        raise ValueError("Plugin name must be 3–48 lowercase letters, digits, hyphens, or underscores.")
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_SOURCE_CHARS:
        raise ValueError("Plugin source must be non-empty and at most 12,000 characters.")
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise ValueError("Plugin source has invalid Python syntax.") from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("A plugin must contain exactly one function definition and no top-level execution.")
    fn = tree.body[0]
    if fn.name != "run" or len(fn.args.args) != 1 or fn.args.args[0].arg != "arguments":
        raise ValueError("Plugin must define run(arguments).")
    if fn.decorator_list or fn.args.vararg or fn.args.kwarg or fn.args.defaults or fn.args.kw_defaults:
        raise ValueError("Decorators, variadic arguments, and defaults are not allowed.")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("Plugin uses a disallowed Python construct: " + type(node).__name__)
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in _BLOCKED_NAMES):
            raise ValueError("Plugin uses a blocked capability.")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_BUILTINS):
            raise ValueError("Only approved pure built-in function calls are allowed.")
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and len(node.value) > 2000:
            raise ValueError("String constants are limited to 2,000 characters.")
    return {"name": name, "status": "pending_review", "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "source": source}
