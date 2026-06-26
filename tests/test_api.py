from fastapi.testclient import TestClient

from nl_to_sql_agent.api import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_query() -> None:
    response = TestClient(app).post("/query", json={"question": "show total revenue by customer"})

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert "total_revenue" in body["sql"]
    assert body["execution"]["execution"]["row_count"] == 3
    assert body["execution"]["execution"]["rows"][0]["name"] == "Jordan Patel"
    assert body["execution"]["execution"]["rows"][0]["total_revenue"] == 330.25
