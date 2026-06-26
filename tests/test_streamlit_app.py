from pathlib import Path


def test_streamlit_app_exists() -> None:
    app_path = Path("app/streamlit_app.py")

    assert app_path.exists()
    assert "Generate and Run" in app_path.read_text(encoding="utf-8")
