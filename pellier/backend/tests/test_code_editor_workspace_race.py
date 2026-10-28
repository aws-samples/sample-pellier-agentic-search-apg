"""Code Editor's first load of the multi-root workspace must not stall on its start-up race."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "patch_code_editor_workspace_race", ROOT / "scripts/patch_code_editor_workspace_race.py"
)
race = importlib.util.module_from_spec(spec)
spec.loader.exec_module(race)

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


def test_bootstrap_patches_the_editor_before_it_first_serves_a_page():
    env = (ROOT / "scripts/bootstrap-environment.sh").read_text()
    patch_at = env.index("scripts/patch_code_editor_workspace_race.py")
    assert env.index("scripts/configure_participant_workspace.py") < patch_at
    assert patch_at < env.index('systemctl start "code-editor@$CODE_EDITOR_USER"')
    assert 'sudo -u "$CODE_EDITOR_USER" python3.14' in env[patch_at - 200:patch_at]
