"""CLI startup rules."""

from __future__ import annotations

import pytest
from windagent_cli.main import main


def test_info_exits_zero_with_valid_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("WINDAGENT_ENVIRONMENT", "test")
    monkeypatch.delenv("WINDAGENT_DATABASE_URL", raising=False)
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "windagent" in out
    assert "database_driver=postgresql+asyncpg" in out


def test_info_reports_startup_error_for_sqlite_in_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("WINDAGENT_ENVIRONMENT", "production")
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///x.db")
    assert main(["info"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("STARTUP_ERROR")


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["does-not-exist"])
