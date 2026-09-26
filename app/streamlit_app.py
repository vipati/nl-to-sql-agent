import pandas as pd
import sqlglot
import streamlit as st
from sqlglot.errors import SqlglotError

from nl_to_sql_agent.agent import Agent, AgentResult
from nl_to_sql_agent.config import Settings
from nl_to_sql_agent.evaluation import load_cases
from nl_to_sql_agent.schema import format_schema_context

st.set_page_config(page_title="NL-to-SQL Agent", layout="wide")


@st.cache_resource
def get_agent() -> Agent:
    return Agent.from_settings()


@st.cache_data
def example_questions() -> list[str]:
    return [case.question for case in load_cases()]


def pretty(sql: str) -> str:
    try:
        statements = sqlglot.transpile(sql, read="duckdb", write="duckdb", pretty=True)
        return ";\n".join(statements)  # show every statement, including rejected extras
    except SqlglotError:
        return sql


def show_result(result: AgentResult) -> None:
    rows = result.result.row_count if result.result else 0
    status, attempts, latency, row_count = st.columns(4)
    status.metric("Status", result.status)
    attempts.metric("Attempts", len(result.attempts))
    latency.metric("Latency", f"{result.latency_ms:,.1f} ms")
    row_count.metric("Rows", rows)

    shown_sql = result.sql or (result.attempts[-1].sql if result.attempts else None)
    if shown_sql:
        st.code(pretty(shown_sql), language="sql")
    if result.error:
        st.error(result.error)

    if len(result.attempts) > 1:
        with st.expander(f"Attempts ({len(result.attempts)})", expanded=result.status != "ok"):
            for index, attempt in enumerate(result.attempts, start=1):
                label = "ok" if attempt.ok else f"{attempt.error_kind} error"
                st.markdown(f"**{index}. {attempt.stage}**: {label}")
                st.code(pretty(attempt.sql), language="sql")
                if attempt.error:
                    st.caption(attempt.error)

    if result.result and result.result.columns:
        frame = pd.DataFrame(result.result.rows, columns=result.result.columns)
        st.dataframe(frame, use_container_width=True, hide_index=True)
        if result.result.truncated:
            st.caption(f"Showing the first {result.result.row_count} rows.")


agent = get_agent()
settings = Settings.from_env()

st.title("NL-to-SQL Agent")
st.caption(
    "Ask questions in plain English. Generated SQL is checked by an AST guard, "
    "self-corrected on errors, and run on a read-only connection with a timeout and row cap."
)

with st.sidebar:
    st.subheader("Configuration")
    provider = agent.provider.name
    st.write(f"Provider: `{provider}`" + (f" / `{settings.model}`" if provider != "rules" else ""))
    st.write(f"Database: `{agent.database.path.name}`")
    st.write(f"Row cap: {agent.database.max_rows}, timeout: {agent.database.timeout_seconds:g}s")
    with st.expander("Schema the model sees"):
        st.code(format_schema_context(agent.database.schema), language="sql")

ask_tab, sql_tab = st.tabs(["Ask a question", "Run SQL (try to break it)"])

with ask_tab:
    examples = example_questions()
    choice = st.selectbox(
        "Example questions",
        examples,
        index=examples.index("Who are the top 5 customers by total spend?"),
    )
    question = st.text_input("Question", value=choice)
    if question.strip():
        show_result(agent.ask(question))

with sql_tab:
    sql = st.text_area(
        "SQL",
        value="SELECT name FROM customers; DROP TABLE customers",
        height=100,
    )
    if sql.strip():
        show_result(agent.run_sql(sql))
