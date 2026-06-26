# NL-to-SQL Agent

An AI engineering portfolio project for translating natural-language business questions into validated SQL.

## Portfolio Signal

This project demonstrates:

- schema-aware query generation
- SQL validation before execution
- provider interface for LLM-backed generation
- an API surface suitable for product integration
- testable AI application architecture
- a path from deterministic baseline to LLM-backed agent

## Architecture

```text
Question -> Schema Context -> SQL Generator -> SQL Validator -> Query Result
```

## Current Milestone

The initial implementation is a deterministic baseline. It handles a small set of common analytical questions against a sample ecommerce schema and validates generated SQL with SQLGlot.

Next milestones:

- add DuckDB execution against sample data
- add schema retrieval from live databases
- add LLM generation behind a provider interface
- add repair loops for invalid SQL
- add evaluation set with execution accuracy

## Quickstart

```powershell
uv sync
uv run pytest
uv run nl-to-sql "show total revenue by customer" --execute
uv run nl-to-sql eval
uv run uvicorn nl_to_sql_agent.api:app --reload
```

## Example

```text
Question: show total revenue by customer
SQL:
SELECT customers.name, SUM(orders.total_amount) AS total_revenue
FROM orders
JOIN customers ON orders.customer_id = customers.customer_id
GROUP BY customers.name
ORDER BY total_revenue DESC
```

The `/query` API also executes valid SQL against the seeded DuckDB sample database and returns columns, rows, and row count.

## Evaluation

Run the evaluation suite:

```powershell
uv run nl-to-sql eval
```

Current metrics measure generation success, SQL validity, execution success, and result accuracy against `data/eval/questions.jsonl`.

## Generation Providers

The default generator is deterministic for reproducible tests. The provider interface in `src/nl_to_sql_agent/providers.py` lets the project add hosted LLMs later without changing validation, execution, or evaluation contracts.
