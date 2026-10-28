"""Code Editor's first load of the multi-root workspace must not stall on its start-up race."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


race = _load("patch_code_editor_workspace_race")
readiness = _load("event_readiness")

# The two sites as Code Editor 1.101.2 ships them in out/vs/code/browser/workbench/workbench.js.
HANDLER = ("this.z=this.B(new KYs(e,r,a,l)),this.B(this.z.onDidUpdateConfiguration(h=>{this.yb(h)"
           ".then(()=>{this.c.initialized=this.z.initialized,this.gb(h)})})),this.B(this.r.onDid")
INITIALIZE = ('async initialize(i){Ni("code/willInitWorkspaceService");const e=this.n;this.n=!1;'
              'const t=await this.cb(i);await this.hb(t,e),this.gb(!1),'
              'Ni("code/didInitWorkspaceService")}updateWorkspaceTrust(i){')
BUNDLE = "/*head*/" + HANDLER + "/*middle*/" + INITIALIZE + "/*tail*/"


def test_a_stalled_first_load_completes_once_the_workspace_file_has_loaded():
    """Seen on event 20: 4 of 14 fresh loads kept the Explorer's clock and opened no terminal.
    The handler threw before the workspace existed, and initialize() kept the stale value."""
    patched, outcome = race.patch(BUNDLE)
    assert outcome == "patched"
    assert ("then(()=>{this.c&&(this.c.initialized=this.z.initialized,this.gb(h))})"
            in patched)
    assert ("await this.hb(t,e),this.c.initialized=this.c.initialized||this.z.initialized"
            '/*pellier-workspace-race*/,this.gb(!1),Ni("code/didInitWorkspaceService")'
            in patched)
    assert patched.startswith("/*head*/") and patched.endswith("/*tail*/")


def test_a_second_run_changes_nothing():
    patched, _ = race.patch(BUNDLE)
    assert race.patch(patched) == (patched, "already patched")


def test_a_build_it_does_not_recognise_is_left_untouched():
    """Code Editor is not version-pinned. A build that renames or fixes either site stays as
    shipped rather than receiving a half-applied patch."""
    renamed = BUNDLE.replace("this.gb(!1)", "this.kb(!1)")
    fixed = BUNDLE.replace(HANDLER, "")
    for bundle in (renamed, fixed):
        unchanged, outcome = race.patch(bundle)
        assert unchanged == bundle and outcome.startswith("unrecognised")


def test_the_cli_writes_the_patch_and_reports_each_file(tmp_path, capsys, monkeypatch):
    workbench = tmp_path / "workbench.js"
    workbench.write_text(BUNDLE)
    monkeypatch.setattr("sys.argv", ["patch", str(workbench)])
    race.main()
    assert race.MARK in workbench.read_text()
    assert capsys.readouterr().out == f"{workbench}: patched\n"


def _box_home(tmp_path, bundle):
    """A participant home holding Code Editor's workbench, as the vendor installer lays it out."""
    workbench = (tmp_path / "home/.local/lib/code-editor-v9.9.9-linux-arm64/dist/out/vs/code"
                 / "browser/workbench/workbench.js")
    workbench.parent.mkdir(parents=True)
    workbench.write_text(bundle)
    return tmp_path / "home", workbench


def _start_check(home):
    """Run workshop-start.sh's own Code Editor step against a participant home."""
    source = (ROOT / "scripts/workshop-start.sh").read_text()
    functions = [source[source.index(f"{name}() {{"):] for name in ("pass", "warn")]
    functions = [body[:body.index("\n")] for body in functions]
    step = source[source.index("check_code_editor_patch() {"):]
    step = step[:step.index("\n}\n") + 3]
    program = "\n".join(["set -uo pipefail", "GREEN=; YEL=; NC=", *functions, step,
                         "check_code_editor_patch"])
    env = {**os.environ, "HOME": str(home), "SCRIPT_DIR": str(ROOT / "scripts"),
           "PYTHON": sys.executable}
    shown = subprocess.run(["bash", "-c", program], env=env, capture_output=True, text=True,
                           check=True).stdout
    return [line.strip() for line in shown.splitlines()]


def test_a_box_left_unpatched_is_not_ready_for_the_event(tmp_path):
    """A newer Code Editor build skips the patch with one bootstrap warning nobody reads across
    a room of boxes. The readiness record each box keeps names it instead."""
    home, workbench = _box_home(tmp_path, BUNDLE)
    lines = _start_check(home)
    assert lines == [("- WARN  Facilitator: Code Editor start-up race not patched; run "
                      f"python3.14 scripts/patch_code_editor_workspace_race.py {workbench}")]
    ready, reason = readiness.verdict(lines + ["+ OK    Ready for Lab 1"], 0, 60)
    assert not ready and reason.startswith("Facilitator: Code Editor start-up race not patched")


def test_a_build_the_patch_does_not_know_asks_for_the_script_to_be_updated(tmp_path):
    home, _ = _box_home(tmp_path, BUNDLE.replace("this.gb(!1)", "this.kb(!1)"))
    [line] = _start_check(home)
    assert line.startswith("- WARN  Facilitator: Code Editor start-up race not patched: this "
                           "Code Editor build is unrecognised")
    assert line.endswith("update scripts/patch_code_editor_workspace_race.py for it")


def test_a_patched_box_stays_ready_and_a_laptop_says_nothing(tmp_path):
    home, _ = _box_home(tmp_path, race.patch(BUNDLE)[0])
    lines = _start_check(home)
    assert lines == ["+ OK    Code Editor start-up race patched"]
    assert readiness.verdict(lines + ["+ OK    Ready for Lab 1"], 0, 60) == (True,
                                                                          readiness.READY)
    assert _start_check(tmp_path / "laptop-home") == []


def test_bootstrap_patches_the_editor_before_it_first_serves_a_page():
    env = (ROOT / "scripts/bootstrap-environment.sh").read_text()
    patch_at = env.index("scripts/patch_code_editor_workspace_race.py")
    assert env.index("scripts/configure_participant_workspace.py") < patch_at
    assert patch_at < env.index('systemctl start "code-editor@$CODE_EDITOR_USER"')
    assert 'sudo -u "$CODE_EDITOR_USER" python3.14' in env[patch_at - 200:patch_at]
