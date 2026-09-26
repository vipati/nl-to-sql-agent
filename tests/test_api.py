import pytest
from fastapi.testclient import TestClient

from nl_to_sql_agent.agent import Agent
from nl_to_sql_agent.api import create_app
from nl_to_sql_agent.providers import ProviderError, RulesProvider


@pytest.fixture
def client(database) -> TestClient:
    return TestClient(create_app(Agent(RulesProvider(), database)))


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["provider"] == "rules"


def test_query(client: TestClient) -> None:
    response = client.post("/query", json={"question": "Who are the top 5 customers by spend?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["result"]["columns"] == ["name", "total_spent"]
    assert body["result"]["rows"][0] == ["Sam Okafor", 1435.67]
    assert body["attempts"][0]["stage"] == "generate"


def test_unanswerable_question_is_reported_in_status(client: TestClient) -> None:
    response = client.post("/query", json={"question": "what is the weather"})

    assert response.status_code == 200
    assert response.json()["status"] == "unanswerable"


def test_sql_endpoint_blocks_unsafe_sql(client: TestClient) -> None:
    response = client.post("/sql", json={"sql": "SELECT 1; DROP TABLE customers"})

    assert response.status_code == 400
    assert response.json()["detail"]["status"] == "blocked"


def test_sql_endpoint_runs_safe_sql(client: TestClient) -> None:
    response = client.post("/sql", json={"sql": "SELECT COUNT(*) AS n FROM orders"})

    assert response.status_code == 200
    assert response.json()["result"]["rows"] == [[60]]


def test_schema(client: TestClient) -> None:
    body = client.get("/schema").json()

    assert {table["name"] for table in body["schema"]["tables"]} >= {"orders", "customers"}
    assert "CREATE TABLE orders" in body["prompt_context"]


def test_metrics(client: TestClient) -> None:
    client.post("/query", json={"question": "How many customers are there?"})
    client.post("/sql", json={"sql": "DROP TABLE orders"})

    metrics = client.get("/metrics").json()

    assert metrics["requests"] == 2
    assert metrics["by_status"] == {"ok": 1, "blocked": 1}
    assert metrics["latency_ms_p95"] is not None


def test_provider_failure_is_502(database) -> None:
    class DownProvider:
        name = "down"

        def generate(self, request):
            raise ProviderError("backend unavailable")

    client = TestClient(create_app(Agent(DownProvider(), database)))

    response = client.post("/query", json={"question": "anything at all"})

    assert response.status_code == 502
