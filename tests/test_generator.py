import pytest

from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.schema import ecommerce_schema
from nl_to_sql_agent.validator import validate_sql


@pytest.mark.parametrize(
    "question, expected",
    [
        ("show total revenue by customer", "SUM(orders.total_amount)"),
        ("count orders by status", "COUNT(*)"),
        ("list customers", "FROM customers"),
    ],
)
def test_generate_sql_returns_valid_sql(question: str, expected: str) -> None:
    sql = generate_sql(question, ecommerce_schema())

    assert expected in sql
    assert validate_sql(sql).valid


def test_generate_sql_raises_for_unknown_question() -> None:
    with pytest.raises(ValueError, match="No baseline SQL pattern"):
        generate_sql("which products are trending", ecommerce_schema())

