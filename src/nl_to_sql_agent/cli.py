import typer

from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.schema import ecommerce_schema
from nl_to_sql_agent.validator import validate_sql

app = typer.Typer(help="Generate validated SQL from natural-language questions.")


@app.command()
def generate(question: str) -> None:
    """Generate SQL for a natural-language question."""
    sql = generate_sql(question, ecommerce_schema())
    validation = validate_sql(sql)

    typer.echo(sql)
    if not validation.valid:
        raise typer.BadParameter(f"Generated SQL is invalid: {validation.error}")


if __name__ == "__main__":
    app()

