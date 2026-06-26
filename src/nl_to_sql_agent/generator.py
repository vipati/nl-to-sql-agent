from nl_to_sql_agent.providers import SQLGenerationProvider, build_prompt
from nl_to_sql_agent.schema import DatabaseSchema


def generate_sql(
    question: str,
    schema: DatabaseSchema,
    provider: SQLGenerationProvider | None = None,
) -> str:
    """Generate SQL using a deterministic baseline.

    This baseline is intentionally simple and testable. Later milestones can swap
    this function for an LLM-backed generator while keeping validation and API
    contracts stable.
    """
    if provider:
        return provider.generate(build_prompt(question, schema))

    normalized = question.lower().strip()
    table_names = {table.name for table in schema.tables}

    if "revenue" in normalized and "customer" in normalized:
        _require_tables(table_names, {"orders", "customers"})
        return (
            "SELECT customers.name, SUM(orders.total_amount) AS total_revenue "
            "FROM orders "
            "JOIN customers ON orders.customer_id = customers.customer_id "
            "GROUP BY customers.name "
            "ORDER BY total_revenue DESC"
        )

    if "orders" in normalized and ("status" in normalized or "count" in normalized):
        _require_tables(table_names, {"orders"})
        return (
            "SELECT status, COUNT(*) AS order_count "
            "FROM orders "
            "GROUP BY status "
            "ORDER BY order_count DESC"
        )

    if "customers" in normalized or "customer" in normalized:
        _require_tables(table_names, {"customers"})
        return "SELECT customer_id, name, email FROM customers ORDER BY name"

    raise ValueError(
        "No baseline SQL pattern matched this question. Add a generator strategy or LLM fallback."
    )


def _require_tables(available: set[str], required: set[str]) -> None:
    missing = sorted(required - available)
    if missing:
        raise ValueError(f"Schema is missing required tables: {', '.join(missing)}")
