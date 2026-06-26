from nl_to_sql_agent.database import execute_sql


def test_execute_sql_returns_rows() -> None:
    result = execute_sql(
        "SELECT status, COUNT(*) AS order_count "
        "FROM orders "
        "GROUP BY status "
        "ORDER BY order_count DESC"
    )

    assert result.columns == ["status", "order_count"]
    assert result.row_count == 3
    assert result.rows[0] == {"status": "completed", "order_count": 3}

