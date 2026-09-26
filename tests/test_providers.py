import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from nl_to_sql_agent.agent import Agent
from nl_to_sql_agent.config import Settings
from nl_to_sql_agent.providers import (
    OpenAICompatibleProvider,
    ProviderError,
    RulesProvider,
    UnanswerableError,
    build_request,
    extract_sql,
    provider_from_settings,
)


class FakeChatServer:
    """A real HTTP server speaking the OpenAI chat-completions format, with queued replies."""

    def __init__(self, replies: list[str], status: int = 200) -> None:
        self.replies = replies
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                server.requests.append(json.loads(self.rfile.read(length)))
                server.headers.append(dict(self.headers))
                body = json.dumps(
                    {
                        "choices": [{"message": {"content": server.replies.pop(0)}}],
                        "usage": {"prompt_tokens": 321, "completion_tokens": 12},
                    }
                ).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()


@pytest.fixture
def chat_server():
    servers: list[FakeChatServer] = []

    def start(replies: list[str], status: int = 200) -> FakeChatServer:
        servers.append(FakeChatServer(replies, status))
        return servers[-1]

    yield start
    for server in servers:
        server.close()


def test_openai_provider_sends_schema_and_parses_fenced_sql(chat_server, schema) -> None:
    server = chat_server(["```sql\nSELECT COUNT(*) FROM customers;\n```"])
    provider = OpenAICompatibleProvider(server.url, model="llama3.1:8b", api_key="test-key")

    generation = provider.generate(build_request("How many customers?", schema))

    assert generation.sql == "SELECT COUNT(*) FROM customers"
    assert (generation.prompt_tokens, generation.completion_tokens) == (321, 12)
    request = server.requests[0]
    assert request["model"] == "llama3.1:8b"
    assert request["temperature"] == 0
    assert "CREATE TABLE customers" in request["messages"][0]["content"]
    assert request["messages"][1] == {"role": "user", "content": "How many customers?"}
    assert server.headers[0]["Authorization"] == "Bearer test-key"


def test_openai_provider_repair_turn_includes_previous_sql_and_error(chat_server, schema) -> None:
    server = chat_server(["SELECT 1"])
    provider = OpenAICompatibleProvider(server.url, model="m")

    provider.generate(
        build_request("q", schema, previous_sql="SELECT bad FROM orders", error="no column bad")
    )

    messages = server.requests[0]["messages"]
    assert messages[2] == {"role": "assistant", "content": "SELECT bad FROM orders"}
    assert "no column bad" in messages[3]["content"]
    assert "Authorization" not in server.headers[0]


def test_agent_self_corrects_through_a_real_http_round_trip(chat_server, database) -> None:
    server = chat_server(
        [
            "SELECT country, COUNT(*) FROM customers GROUP BY region",
            "SELECT country, COUNT(*) AS n FROM customers GROUP BY country",
        ]
    )
    agent = Agent(OpenAICompatibleProvider(server.url, model="m"), database)

    result = agent.ask("customers per country")

    assert result.status == "ok"
    assert [a.stage for a in result.attempts] == ["generate", "llm_repair"]
    assert result.result.row_count == 5
    assert result.prompt_tokens == 642


def test_http_errors_become_provider_errors(chat_server, schema) -> None:
    server = chat_server(["unused"], status=500)
    provider = OpenAICompatibleProvider(server.url, model="m")

    with pytest.raises(ProviderError):
        provider.generate(build_request("q", schema))


def test_unreachable_backend_is_a_provider_error(schema) -> None:
    provider = OpenAICompatibleProvider("http://127.0.0.1:9/v1", model="m", timeout_seconds=1)

    with pytest.raises(ProviderError):
        provider.generate(build_request("q", schema))


@pytest.mark.parametrize(
    "reply, expected",
    [
        ("SELECT 1", "SELECT 1"),
        ("  SELECT 1;  ", "SELECT 1"),
        ("```\nSELECT 1\n```", "SELECT 1"),
        ("Here you go:\n```sql\nSELECT 1;\n```\nThis counts rows.", "SELECT 1"),
        # Prose without fences is kept, so the guard rejects it and the model gets feedback.
        ("SELECT 1; -- then\nDROP TABLE x", "SELECT 1; -- then\nDROP TABLE x"),
    ],
)
def test_extract_sql(reply: str, expected: str) -> None:
    assert extract_sql(reply) == expected


def test_rules_provider_declines_unknown_questions_and_repairs(schema) -> None:
    provider = RulesProvider()

    assert (
        "COUNT(*)" in provider.generate(build_request("How many customers are there?", schema)).sql
    )
    with pytest.raises(UnanswerableError):
        provider.generate(build_request("what is the weather", schema))
    with pytest.raises(UnanswerableError):
        provider.generate(build_request("q", schema, previous_sql="SELECT 1", error="e"))


def test_provider_from_settings() -> None:
    assert provider_from_settings(Settings(provider="rules")).name == "rules"
    openai = provider_from_settings(Settings(provider="openai", base_url="http://x/v1/"))
    assert openai.url == "http://x/v1/chat/completions"
    with pytest.raises(ValueError, match="Unknown NL2SQL_PROVIDER"):
        provider_from_settings(Settings(provider="nope"))
