import os
from pathlib import Path

from nipulate.cli import DEFAULT_PORT, default_log_path, parse_args


def test_defaults():
    args = parse_args([])
    assert args.port == DEFAULT_PORT
    assert args.log is None and not args.fake


def test_log_file_option():
    assert parse_args(["--log", "x.log"]).log == Path("x.log")


def test_log_lives_in_appdata(monkeypatch):
    monkeypatch.setenv("APPDATA", os.path.join("C:", "Users", "x", "AppData", "Roaming"))
    assert default_log_path() == Path("C:", "Users", "x", "AppData", "Roaming", "nipulate", "nipulate.log")
