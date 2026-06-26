# Project Plan

## Goal

Build a recruiter-friendly NL-to-SQL system that shows practical AI engineering:

- clean application boundaries
- schema-aware generation
- SQL validation and execution
- measurable accuracy
- API and demo UI

## Milestones

1. Deterministic SQL baseline with schema models and SQLGlot validation.
2. DuckDB sample database with seed data and query execution endpoint.
3. Evaluation set with exact-match, syntax-validity, and execution-accuracy metrics.
4. LLM provider interface with prompt templates and schema context injection.
5. SQL repair loop for invalid syntax, missing tables, and execution errors.
6. Streamlit demo with question input, SQL display, validation status, and result table.
7. Dockerfile, GitHub Actions CI, architecture diagram, and polished README.

## Current Status

Completed:

- Milestone 1 baseline generator.
- Milestone 2 DuckDB seed data and SQL execution.
- Milestone 3 evaluation set and execution-accuracy metrics.
- Milestone 4 provider interface for LLM-backed generation.
- Milestone 5 SQL repair loop.
- Milestone 6 Streamlit demo.
- Milestone 7 Dockerfile, CI, architecture docs, and README polish.
- FastAPI `/health` and `/query` endpoints.
- CLI command for generating SQL.
- Unit tests for generator and API behavior.
- Ruff lint configuration.

Next:

- Add screenshots, publish privately to GitHub, then prepare a public release.

## Resume Bullets

- Built a schema-aware NL-to-SQL agent with SQL validation, execution checks, and API access.
- Improved query reliability with validation and repair loops before database execution.
- Created an evaluation harness measuring exact-match and execution accuracy across business questions.
