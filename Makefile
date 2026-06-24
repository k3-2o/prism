# PRISM Development Makefile
# Loops: write → make fmt → make check → make test → commit → repeat

.PHONY: fmt lint types security check test test-cov clean build install-local audit

# ── Format ──────────────────────────────────────────────────────────────

fmt:
	uv run ruff format src/ tests/

# ── Lint ────────────────────────────────────────────────────────────────

lint:
	uv run ruff check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/

# ── Type check ──────────────────────────────────────────────────────────

types:
	uv run mypy src/ --ignore-missing-imports

# ── Security ────────────────────────────────────────────────────────────

security:
	uv run bandit -r src/ -x src/prism/rules/

# ── Full check (fmt → lint → types) ────────────────────────────────────
# security is separate — pre-existing bandit issues are all Low severity
# and expected for a CLI tool that runs subprocesses.

check: fmt lint types
	@echo "✅ All checks passed"

check-all: check security
	@echo "✅ All checks (including security) passed"

# ── Test ────────────────────────────────────────────────────────────────

test:
	uv run pytest -v || test $$? -eq 5

test-cov:
	uv run pytest --cov=src/prism --cov-report=term-missing -v

# ── Clean ───────────────────────────────────────────────────────────────

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/

# ── Build ───────────────────────────────────────────────────────────────

build:
	uv build

# ── Local install ───────────────────────────────────────────────────────

install-local: build
	uv tool install --reinstall .

# ── Self-audit ──────────────────────────────────────────────────────────

audit:
	uv run prism . --structure-only

audit-full:
	uv run prism .

# ── Run ─────────────────────────────────────────────────────────────────

run:
	uv run prism $(ARGS)

# ── Smoke ───────────────────────────────────────────────────────────────

smoke:
	uv run prism --version
	uv run prism --help
