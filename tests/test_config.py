import os
import subprocess
import sys


def _run_with_env(extra_env: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("DB_PATH", None)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd="/workspaces",
        env=env,
        capture_output=True,
        text=True,
    )


def test_invalid_log_level_fails_fast_with_clear_error():
    result = _run_with_env({"LOG_LEVEL": "NOT_A_LEVEL"})
    assert result.returncode == 1
    assert "Invalid configuration" in result.stderr
    assert "LOG_LEVEL" in result.stderr


def test_port_out_of_range_fails_fast_with_clear_error():
    result = _run_with_env({"PORT": "999999"})
    assert result.returncode == 1
    assert "Invalid configuration" in result.stderr


def test_base_url_missing_scheme_fails_fast_with_clear_error():
    result = _run_with_env({"BASE_URL": "not-a-url"})
    assert result.returncode == 1
    assert "Invalid configuration" in result.stderr
    assert "BASE_URL" in result.stderr


def test_valid_config_starts_cleanly():
    result = _run_with_env({"LOG_LEVEL": "DEBUG"})
    assert result.returncode == 0
    assert result.stderr == ""
