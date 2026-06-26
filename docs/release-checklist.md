# Release Checklist

Before making this repository public:

- Confirm `uv run pytest` passes.
- Confirm `uv run ruff check .` passes.
- Confirm `uv run nl-to-sql eval` reports 100% on the current eval set.
- Add screenshots of the Streamlit demo.
- Add GitHub repository topics: `nl-to-sql`, `llm`, `duckdb`, `fastapi`, `streamlit`, `ai-engineering`.
- Confirm no private data or API keys are committed.
- Create the GitHub repo as private first.

```powershell
gh repo create nl-to-sql-agent --private --source . --remote origin
```

