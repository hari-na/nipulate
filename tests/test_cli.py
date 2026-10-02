from pathlib import Path

from nipulate.cli import DEFAULT_PORT, default_log_path, parse_args
from nipulate.pairing import default_config_path


def test_defaults():
    args = parse_args([])
    assert args.port == DEFAULT_PORT
    assert args.log is None and args.config is None and not args.fake


def test_log_file_option():
    assert parse_args(["--log", "x.log"]).log == Path("x.log")


def test_log_lives_next_to_the_pairing_file():
    assert default_log_path() == default_config_path().with_name("nipulate.log")
