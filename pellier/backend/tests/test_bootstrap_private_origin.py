"""Execute the deployed nginx emitter without touching host configuration."""

from pathlib import Path
import os
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[3] / "scripts/bootstrap-environment.sh"


def _render(tmp_path: Path, private: bool, token: str = "test-origin-token") -> str:
    source = SOURCE.read_text()
    block = source.split('log "Configuring Nginx..."', 1)[1].split("\nnginx -t", 1)[0]
    root = tmp_path / "nginx"
    block = block.replace("/etc/nginx", str(root))
    # Preserve sed's actual expression evaluation on macOS and Linux.
    compatibility = (
        'sed() { if [ "$1" = "-i" ]; then shift; command sed -i "" "$@"; '
        'else command sed "$@"; fi; }\n' if sys.platform == "darwin" else ""
    )
    subprocess.run(
        ["bash", "-eu", "-c", compatibility + block],
        env={**os.environ, "PELLIER_PRIVATE_ORIGIN": str(private).lower(), "ORIGIN_VERIFY_TOKEN": token},
        check=True,
        capture_output=True,
        text=True,
    )
    return (root / "conf.d/code-editor.conf").read_text()


def test_private_origin_preserves_guard_and_exposes_only_health_on_separate_port(tmp_path):
    config = _render(tmp_path, True)
    assert 'if ($http_x_pellier_origin_verify != "test-origin-token") { return 403; }' in config
    assert "map $http_x_pellier_viewer_proto $pellier_forwarded_proto" in config
    assert "$http_x_forwarded_proto" not in config
    user, health = config.split("\nserver {", 2)[1:]
    assert "listen 80 default_server;" in user and "listen 8081;" not in user
    assert "proxy_http_version 1.1;" in user
    assert "listen 8081;" in health
    assert "location = /health {" in health
    assert "proxy_pass http://127.0.0.1:8000/api/health;" in health
    assert "location / { return 404; }" in health
    assert "8080" not in health
    main = (tmp_path / "nginx/nginx.conf").read_text()
    assert str(tmp_path / "nginx/conf.d/code-editor.conf") in main
    assert "*.conf" not in main
    assert "server {" not in main


def test_existing_origin_default_keeps_forwarding_contract_without_health_listener(tmp_path):
    config = _render(tmp_path, False)
    assert "map $http_x_forwarded_proto $pellier_forwarded_proto" in config
    assert "$http_x_pellier_viewer_proto" not in config
    assert "listen 8081" not in config
    assert 'return 403;' in config


@pytest.mark.parametrize("private,token,expected", [("true", "", 1), ("unexpected", "token", 1), ("true", "token", 0), ("false", "", 0)])
def test_private_origin_configuration_fails_before_host_mutation(private, token, expected):
    prefix = SOURCE.read_text().split("\nprobe_editor_http()", 1)[0]
    result = subprocess.run(
        ["bash", "-c", prefix],
        env={**os.environ, "CODE_EDITOR_PASSWORD": "test-only", "PELLIER_PRIVATE_ORIGIN": private, "ORIGIN_VERIFY_TOKEN": token},
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected
