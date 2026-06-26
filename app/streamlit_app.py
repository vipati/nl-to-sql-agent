import pandas as pd
import streamlit as st

from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.repair import execute_with_repair
from nl_to_sql_agent.schema import ecommerce_schema

st.set_page_config(page_title="NL-to-SQL Agent", layout="wide")

st.title("NL-to-SQL Agent")

question = st.text_input("Question", value="show total revenue by customer")

if st.button("Generate and Run", type="primary"):
    try:
        sql = generate_sql(question, ecommerce_schema())
        attempt = execute_with_repair(sql)
    except Exception as exc:
        st.error(str(exc))
    else:
        st.subheader("Generated SQL")
        st.code(sql, language="sql")

        if attempt.changed:
            st.subheader("Repaired SQL")
            st.code(attempt.repaired_sql, language="sql")

        col_valid, col_executed = st.columns(2)
        col_valid.metric("Valid SQL", "Yes" if attempt.valid else "No")
        col_executed.metric("Executed", "Yes" if attempt.executed else "No")

        if attempt.error:
            st.error(attempt.error)

        if attempt.execution:
            st.subheader("Results")
            st.dataframe(pd.DataFrame(attempt.execution.rows), use_container_width=True)

