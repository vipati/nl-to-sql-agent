from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.providers import DeterministicProvider, build_prompt, format_schema_context
from nl_to_sql_agent.schema import ecommerce_schema


def test_format_schema_context_includes_tables_and_columns() -> None:
    context = format_schema_context(ecommerce_schema())

    assert "customers(customer_id INTEGER" in context
    assert "orders(order_id INTEGER" in context


def test_provider_backed_generation() -> None:
    sql = generate_sql(
        "count orders by status",
        ecommerce_schema(),
        provider=DeterministicProvider(),
    )

    assert "COUNT(*)" in sql
    assert "GROUP BY status" in sql


def test_build_prompt() -> None:
    prompt = build_prompt("list customers", ecommerce_schema())

    assert prompt.question == "list customers"
    assert "customers" in prompt.schema_context
