# Project Task Runner

# List available recipes
default:
    @just --list

# Format code and configuration files
format:
    uv run ruff format .

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
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy .
    uv run pytest --cov=pulumi_reolink --cov-fail-under=90
