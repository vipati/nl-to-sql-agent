# Offline demo: no API key or model needed. Set $env:NL2SQL_PROVIDER = "openai" to use an LLM.
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "1. Ask a question: SQL is generated, guarded, and run read-only"
uv run nl-to-sql ask "Who are the top 5 customers by total spend?"
Write-Host ""

Write-Host "2. Stacked query: blocked by the guard before it reaches the database"
uv run nl-to-sql sql "SELECT name FROM customers; DROP TABLE customers"
Write-Host ""

Write-Host "3. File read through a table function: blocked"
uv run nl-to-sql sql "SELECT * FROM read_csv('/etc/passwd')"
Write-Host ""

Write-Host "4. Wrong column name: rejected with a schema hint the repair loop can use"
uv run nl-to-sql sql "SELECT order_status, COUNT(*) FROM orders GROUP BY order_status"
Write-Host ""

Write-Host "5. Evaluation: execution accuracy and the safety suite"
uv run nl-to-sql eval
