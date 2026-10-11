"""Configuration from the environment."""

from __future__ import annotations

import pytest

from norway_archives_mcp.config import DA_MIN_INTERVAL, ConfigError, load_config

VARS = (
    "NORWAY_ARCHIVES_CACHE_DIR",
    "NORWAY_ARCHIVES_TIMEOUT",
    "NORWAY_ARCHIVES_DA_INTERVAL",
    "NORWAY_ARCHIVES_DA_DAILY_BUDGET",
    "NORWAY_ARCHIVES_CONTACT",
    "NORWAY_ARCHIVES_DOWNLOAD_DIR",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_defaults_need_nothing():
    cfg = load_config()
    assert cfg.da_interval == DA_MIN_INTERVAL == 5.0
    assert cfg.da_daily_budget == 600
    assert cfg.download_dir is None and cfg.contact == ""


def test_digitalarkivet_cannot_be_asked_faster_than_five_seconds(monkeypatch):
    monkeypatch.setenv("NORWAY_ARCHIVES_DA_INTERVAL", "2")
    with pytest.raises(ConfigError):
        load_config()
    monkeypatch.setenv("NORWAY_ARCHIVES_DA_INTERVAL", "8")
    assert load_config().da_interval == 8.0


def test_the_budget_is_a_whole_positive_number(monkeypatch):
    monkeypatch.setenv("NORWAY_ARCHIVES_DA_DAILY_BUDGET", "2.5")
    with pytest.raises(ConfigError):
        load_config()
    monkeypatch.setenv("NORWAY_ARCHIVES_DA_DAILY_BUDGET", "0")
    with pytest.raises(ConfigError):
        load_config()
    monkeypatch.setenv("NORWAY_ARCHIVES_DA_DAILY_BUDGET", "50")
    assert load_config().da_daily_budget == 50


@pytest.mark.parametrize("bad", ["a\nb", "x (y)", "\x07"])
def test_a_contact_that_could_break_the_header_is_refused(monkeypatch, bad):
    monkeypatch.setenv("NORWAY_ARCHIVES_CONTACT", bad)
    with pytest.raises(ConfigError):
        load_config()


def test_the_download_folder_must_exist_and_be_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("NORWAY_ARCHIVES_DOWNLOAD_DIR", "relative/path")
    with pytest.raises(ConfigError):
        load_config()
    monkeypatch.setenv("NORWAY_ARCHIVES_DOWNLOAD_DIR", str(tmp_path / "missing"))
    with pytest.raises(ConfigError):
        load_config()
    monkeypatch.setenv("NORWAY_ARCHIVES_DOWNLOAD_DIR", str(tmp_path))
    assert load_config().download_dir == tmp_path


def test_a_dotenv_in_the_working_directory_is_read(tmp_path):
    (tmp_path / ".env").write_text("NORWAY_ARCHIVES_TIMEOUT=12\n")
    assert load_config().timeout == 12.0
