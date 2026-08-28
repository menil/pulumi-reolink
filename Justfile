# Project Task Runner

# List available recipes
default:
    @just --list

# Format code and configuration files (pass --check to check without writing)
format *ARGS:
    uv run ruff format {{ ARGS }} .

# Run code and markdown linting checks
lint:
    uv run ruff check .

# Run static type checking
typecheck:
    uv run mypy .

# Run the unit test suite with coverage enforcement
test:
    uv run pytest --cov=pulumi_reolink --cov-fail-under=90

# Run all local checks (format, lint, type check, tests)
validate:
    just format --check
    just lint
    just typecheck
    just test
