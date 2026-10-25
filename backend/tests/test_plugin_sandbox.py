import pytest
from app.tools.plugin_sandbox import validate_plugin


def test_accepts_small_pure_plugin():
    result = validate_plugin("simple_math", "def run(arguments):\n    return arguments['value'] + 1\n")
    assert result["status"] == "pending_review"
    assert len(result["source_sha256"]) == 64


@pytest.mark.parametrize("source", [
    "import os\ndef run(arguments):\n    return 1\n",
    "print('execute at import time')\ndef run(arguments):\n    return 1\n",
    "def run(arguments):\n    return open('/etc/passwd').read()\n",
    "def run(arguments):\n    return eval(arguments['code'])\n",
    "def other(arguments):\n    return 1\n",
])
def test_rejects_unsafe_or_malformed_plugins(source):
    with pytest.raises(ValueError):
        validate_plugin("unsafe_plugin", source)


def test_rejects_bad_names_and_oversized_source():
    with pytest.raises(ValueError):
        validate_plugin("../unsafe", "def run(arguments):\n    return 1\n")
    with pytest.raises(ValueError):
        validate_plugin("large_plugin", " " * 12001)
