from math import isfinite

_OPERATIONS = {
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "multiply": lambda a, b: a * b,
    "divide": lambda a, b: a / b,
}


def run_calculator(arguments):
    if set(arguments) != {"operation", "a", "b"}:
        raise ValueError("Expected exactly operation, a, and b")
    operation = arguments["operation"]
    if operation not in _OPERATIONS:
        raise ValueError("Unsupported calculator operation")
    a, b = arguments["a"], arguments["b"]
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ValueError("Operands must be numbers")
    if not isfinite(a) or not isfinite(b):
        raise ValueError("Operands must be finite numbers")
    if operation == "divide" and b == 0:
        raise ValueError("Division by zero is not allowed")
    result = _OPERATIONS[operation](a, b)
    if not isfinite(result):
        raise ValueError("Result is not finite")
    return float(result)
