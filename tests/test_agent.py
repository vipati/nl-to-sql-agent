from nl_to_sql_agent.agent import Agent
from nl_to_sql_agent.config import Settings
from nl_to_sql_agent.database import Database, sample_database_path
from nl_to_sql_agent.providers import ProviderError, RulesProvider

from .conftest import SLOW_SQL, ScriptedProvider

GOOD_SQL = "SELECT status, COUNT(*) AS n FROM orders GROUP BY status"


def make_agent(database: Database, *responses: str, max_repairs: int = 2) -> Agent:
    return Agent(ScriptedProvider(list(responses)), database, max_repair_attempts=max_repairs)


def test_first_attempt_success(database) -> None:
    agent = make_agent(database, GOOD_SQL)

    result = agent.ask("orders by status")

    assert result.status == "ok"
    assert [a.stage for a in result.attempts] == ["generate"]
    assert result.result.row_count == 4
    assert result.sql.endswith("LIMIT 1001")
    assert (result.provider_calls, result.prompt_tokens, result.completion_tokens) == (1, 100, 20)


def test_schema_errors_are_autofixed_without_a_model_call(database) -> None:
    agent = make_agent(database, "SELECT order_status, COUNT(*) FROM orders GROUP BY order_status")

    result = agent.ask("orders by status")

    assert result.status == "ok"
    assert [a.stage for a in result.attempts] == ["generate", "autofix"]
    assert result.provider_calls == 1


def test_execution_errors_are_sent_back_to_the_model(database) -> None:
    provider = ScriptedProvider(["SELECT name FROM customers WHERE signup_date > 'soon'", GOOD_SQL])
    agent = Agent(provider, database)

    result = agent.ask("orders by status")

    assert result.status == "ok"
    assert [a.stage for a in result.attempts] == ["generate", "llm_repair"]
    assert result.attempts[0].error_kind == "execution"
    repair_request = provider.requests[1]
    assert repair_request.previous_sql.startswith("SELECT name FROM customers")
    assert "soon" in repair_request.error


def test_unsafe_sql_fails_closed_without_retry(database) -> None:
    provider = ScriptedProvider(["DELETE FROM orders", GOOD_SQL])
    agent = Agent(provider, database)

    result = agent.ask("remove the orders")

    assert result.status == "blocked"
    assert len(result.attempts) == 1
    assert len(provider.requests) == 1


def test_repairs_are_bounded(database) -> None:
    agent = make_agent(database, "SELEC 1", "SELEC 2", "SELEC 3", "SELEC 4", max_repairs=2)

    result = agent.ask("anything")

    assert result.status == "invalid"
    assert len(result.attempts) == 3
    assert result.error


def test_timeouts_are_not_retried() -> None:
    database = Database(sample_database_path(), timeout_seconds=0.2)
    agent = make_agent(database, SLOW_SQL, GOOD_SQL)

    result = agent.ask("slow question")

    assert result.status == "timeout"
    assert len(result.attempts) == 1


def test_unanswerable_question(database) -> None:
    agent = Agent(RulesProvider(), database)

    result = agent.ask("what is the meaning of life")

    assert result.status == "unanswerable"
    assert result.attempts == []
    assert "No rule matches" in result.error


def test_provider_errors_are_reported(database) -> None:
    class BrokenProvider:
        name = "broken"

        def generate(self, request):
            raise ProviderError("connection refused")

    result = Agent(BrokenProvider(), database).ask("anything")

    assert result.status == "provider_error"
    assert result.error == "connection refused"


def test_run_sql_guards_user_sql(database) -> None:
    agent = Agent(RulesProvider(), database)

    assert agent.run_sql("SELECT COUNT(*) FROM customers").result.rows == [[12]]
    blocked = agent.run_sql("SELECT 1; DROP TABLE customers")
    assert blocked.status == "blocked"
    assert blocked.result is None


def test_from_settings_uses_configured_database(tmp_path) -> None:
    settings = Settings(database=str(sample_database_path()), max_rows=7, query_timeout_seconds=1)

    agent = Agent.from_settings(settings)

    assert agent.provider.name == "rules"
    assert agent.database.max_rows == 7
    assert agent.ask("list customers").result.truncated is True
