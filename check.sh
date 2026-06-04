set -e

PYTHON_EXECUTABLE=${PYTHON:-python3}

# Run static type checker and verify formatting guidelines
$PYTHON_EXECUTABLE -m ruff check
$PYTHON_EXECUTABLE -m ruff format --check
$PYTHON_EXECUTABLE -m mypy markdown_doc

# Run unit tests
$PYTHON_EXECUTABLE check.py
$PYTHON_EXECUTABLE check_routing.py
