"""Code Editor installs the tested release from a verified copy, with two fallbacks.

scripts/install_code_editor.sh runs here against a vendor served from file://, a workshop
assets bucket behind a stand-in `aws`, and a stand-in installer that records where it was
told to download from. Plan A is the vendor's copy, plan B the assets copy, and plan C the
vendor's latest release when neither verified copy exists.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "install_code_editor.sh"
RELEASE_FILE = REPO / "scripts" / "code-editor-release.env"
VERSION = "v1.101.2"
DIST = f"code-editor-server-{VERSION}-7-linux-arm64.tar.gz"
ARCHIVE = b"the tested Code Editor archive\n"

INSTALLER = """#!/bin/bash
set -euo pipefail
CODEEDITOR_CLOUDFRONT_BASE_URL="https://code-editor.amazonaws.com/content/code-editor-server/dist"
# The vendor tests these with [[ -v ]]; ${VAR+x} is the same test on any bash.
if [ -n "${CODE_EDITOR_VERSION+x}" ] && [ -n "${CODE_EDITOR_DISTRIBUTION_VERSION+x}" ]; then
    ver="$CODE_EDITOR_VERSION"
    curl -fsSL "$CODEEDITOR_CLOUDFRONT_BASE_URL/$ver/$CODE_EDITOR_DISTRIBUTION_VERSION" \\
        -o "$CODE_EDITOR_HOME/fetched.tar.gz"
    echo "pinned $CODEEDITOR_CLOUDFRONT_BASE_URL" >> "$CODE_EDITOR_HOME/installer.log"
else
    ver="v9.9.9"
    echo "latest" >> "$CODE_EDITOR_HOME/installer.log"
fi
installed="${INSTALLED_VERSION:-${ver#v}}"
mkdir -p "$CODE_EDITOR_HOME/.local/lib/code-editor-$ver-linux-arm64/dist"
printf '{"version": "%s"}\\n' "$installed" \\
    > "$CODE_EDITOR_HOME/.local/lib/code-editor-$ver-linux-arm64/dist/product.json"
"""

FAKE_AWS = """#!/bin/bash
# aws s3 cp --only-show-errors s3://bucket/key destination
source_path="$FAKE_BUCKET_ROOT/${4#s3://}"
[ -f "$source_path" ] && cp "$source_path" "$5"
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Box:
    """A scratch vendor, assets bucket, home folder and release file for one run."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.vendor = root / "vendor"
        self.bucket = root / "bucket"
        self.home = root / "home"
        self.bin = root / "bin"
        for folder in (self.vendor, self.bucket, self.home, self.bin):
            folder.mkdir()
        (self.bin / "aws").write_text(FAKE_AWS)
        (self.bin / "aws").chmod(0o755)
        self.put_vendor_installer(INSTALLER)
        self.put_vendor_archive(ARCHIVE)
        self.release(installer_sha=_sha(INSTALLER.encode()))

    def release(self, installer_sha: str) -> None:
        (self.root / "release.env").write_text(
            "CODE_EDITOR_RELEASE=1.101.2\nCODE_EDITOR_BUILD=7\n"
            f"CODE_EDITOR_ARCHIVE_SHA256={_sha(ARCHIVE)}\n"
            f"CODE_EDITOR_INSTALLER_SHA256={installer_sha}\n")

    def put_vendor_archive(self, data: bytes) -> None:
        (self.vendor / VERSION).mkdir(exist_ok=True)
        (self.vendor / VERSION / DIST).write_bytes(data)

    def put_vendor_installer(self, text: str) -> None:
        (self.vendor / "aws-workshop-studio").mkdir(exist_ok=True)
        (self.vendor / "aws-workshop-studio" / "install.sh").write_text(text)

    def put_asset(self, name: str, data: bytes) -> None:
        target = self.bucket / "assets-bucket" / "event/code-editor" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def run(self, *, assets: bool = True, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "CodeEditorUser": "participant",
            "CODE_EDITOR_HOME": str(self.home),
            "CODE_EDITOR_RELEASE_FILE": str(self.root / "release.env"),
            "CODE_EDITOR_VENDOR_URL": f"file://{self.vendor}",
            "FAKE_BUCKET_ROOT": str(self.bucket),
            "ASSETS_BUCKET_NAME": "assets-bucket" if assets else "",
            "ASSETS_BUCKET_PREFIX": "event/",
            **extra,
        }
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True,
                              text=True, timeout=60)

    def installer_log(self) -> str:
        return (self.home / "installer.log").read_text()


@pytest.fixture
def box(tmp_path: Path) -> Box:
    return Box(tmp_path)


def test_plan_a_installs_the_vendor_copy_after_verifying_it(box: Box) -> None:
    done = box.run()

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "pinned download"
    assert (box.home / "fetched.tar.gz").read_bytes() == ARCHIVE
    assert re.fullmatch(r"pinned file://\S+/mirror\n", box.installer_log())


def test_plan_b_uses_the_assets_copy_when_the_vendor_has_none(box: Box) -> None:
    (box.vendor / VERSION / DIST).unlink()
    box.put_asset(DIST, ARCHIVE)

    done = box.run()

    assert done.stdout.strip() == "assets copy", done.stderr
    assert (box.home / "fetched.tar.gz").read_bytes() == ARCHIVE


def test_plan_b_replaces_a_vendor_copy_that_fails_its_checksum(box: Box) -> None:
    box.put_vendor_archive(b"tampered\n")
    box.put_asset(DIST, ARCHIVE)

    done = box.run()

    assert done.stdout.strip() == "assets copy", done.stderr
    assert (box.home / "fetched.tar.gz").read_bytes() == ARCHIVE


def test_plan_c_installs_the_vendor_latest_and_says_so(box: Box) -> None:
    (box.vendor / VERSION / DIST).unlink()

    done = box.run(assets=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "latest 9.9.9"
    assert "no test event ran" in done.stderr
    assert box.installer_log() == "latest\n"


def test_a_corrupt_assets_copy_is_never_installed(box: Box) -> None:
    (box.vendor / VERSION / DIST).unlink()
    box.put_asset(DIST, b"also tampered\n")

    done = box.run()

    assert done.stdout.strip() == "latest 9.9.9"
    assert not (box.home / "fetched.tar.gz").exists()


def test_a_changed_installer_warns_and_still_installs_the_pinned_release(box: Box) -> None:
    box.release(installer_sha="0" * 64)

    done = box.run()

    assert done.stdout.strip() == "pinned download"
    assert "installer changed" in done.stderr


def test_the_installer_comes_from_the_assets_when_the_vendor_lacks_it(box: Box) -> None:
    (box.vendor / "aws-workshop-studio" / "install.sh").unlink()
    box.put_asset("install.sh", INSTALLER.encode())

    done = box.run()

    assert done.stdout.strip() == "pinned download", done.stderr


def test_no_installer_anywhere_stops_the_bootstrap(box: Box) -> None:
    (box.vendor / "aws-workshop-studio" / "install.sh").unlink()

    done = box.run(assets=False)

    assert done.returncode == 1
    assert "no installer" in done.stderr


def test_a_pinned_install_that_reports_another_version_stops_the_bootstrap(box: Box) -> None:
    done = box.run(INSTALLED_VERSION="1.0.0")

    assert done.returncode == 1
    assert "expected 1.101.2" in done.stderr


def test_the_release_file_pins_one_release_with_both_checksums() -> None:
    values = dict(line.split("=", 1) for line in RELEASE_FILE.read_text().splitlines()
                  if line and not line.startswith("#"))
    assert re.fullmatch(r"\d+\.\d+\.\d+", values["CODE_EDITOR_RELEASE"])
    assert re.fullmatch(r"\d+\.\d+", values["CODE_EDITOR_BUILD"])
    for key in ("CODE_EDITOR_ARCHIVE_SHA256", "CODE_EDITOR_INSTALLER_SHA256"):
        assert re.fullmatch(r"[0-9a-f]{64}", values[key]), key


def test_bootstrap_installs_through_the_script_and_never_pipes_the_vendor_installer() -> None:
    bootstrap = (REPO / "scripts" / "bootstrap-environment.sh").read_text()
    assert "scripts/install_code_editor.sh" in bootstrap
    assert "install.sh | bash" not in bootstrap


def test_the_box_can_read_the_assets_copy_it_falls_back_to() -> None:
    templates = REPO / "deploy" / "own-account" / "templates"
    editor = (templates / "pellier-code-editor.yml").read_text()
    root = (templates / "pellier-governed.yml").read_text()
    assert 'export ASSETS_BUCKET_NAME="${AssetsBucketName}"' in editor
    assert "${Bucket}/${Prefix}code-editor/*" in editor
    assert "AssetsBucketName: !Ref AssetsBucketName" in root
