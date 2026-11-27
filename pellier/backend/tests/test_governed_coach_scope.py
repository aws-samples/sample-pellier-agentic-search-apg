"""The optional coach must be able to assist every governed authoring region."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_coach_scope_covers_every_marker_without_revealing_answers():
    import importlib.util
    spec = importlib.util.spec_from_file_location('coach_reset_contract', ROOT / 'scripts/reset_participant_exercises.py')
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    root = (ROOT / 'CLAUDE.md').read_text().split('### Maintainer mode')[0]
    backend = (ROOT / 'pellier/backend/CLAUDE.md').read_text().split('## Maintainer architecture')[0]
    for exercise in module.MARKER_EXERCISES:
        assert exercise.destination in root
        assert exercise.marker.removeprefix('WORKSHOP - ') in root
        if exercise.destination.startswith('pellier/backend/'):
            assert exercise.destination.removeprefix('pellier/backend/') in backend
    for exercise in module.FILE_EXERCISES:
        assert exercise.destination in root
    assert 'Lab 2 only' not in backend
    assert 'one hint' in root and 'explain the change as soon as asked' in root
    assert 'Ask for the prediction' not in root and 'participant\'s prediction' not in backend
    assert 'Never inspect `solutions/`' in backend


def test_agents_md_is_claude_md_so_every_coding_agent_reads_one_contract():
    agents = ROOT / 'AGENTS.md'
    assert agents.is_symlink() and agents.readlink() == Path('CLAUDE.md')


def test_bootstrap_points_all_four_labs_to_the_participant_troubleshooting_rules():
    bootstrap = (ROOT / 'scripts/bootstrap-labs.sh').read_text()
    guidance = bootstrap.split("<< 'CLAUDEEOF'\n", 1)[1].split('\nCLAUDEEOF', 1)[0]
    assert 'Labs 1 to 4' in guidance
    assert 'Participant mode' in guidance and '`CLAUDE.md`' in guidance
    assert 'Stop after one failed attempt' not in guidance
    # This block is the only guidance that loads when Claude starts outside the repository.
    assert '`solutions/`' in guidance and '`takeaway/`' in guidance


def _rows_a_failed_check_prints():
    """The row labels in a failed check's box, read from the renderer every check uses."""
    import importlib
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    workshop_check = importlib.import_module('workshop_check')
    box = workshop_check.render(workshop_check.Finding(
        task='1A', title='claim', state=workshop_check.FAILED, expected='row-value',
        observed='row-value', evidence=['row-value'], next_step='row-value'))
    return [line.split('│')[1].strip() for line in box.splitlines() if 'row-value' in line]


def test_troubleshooting_uses_the_participants_evidence_and_leaves_actions_to_them():
    participant = (ROOT / 'CLAUDE.md').read_text().split('### Participant mode', 1)[1]
    participant = participant.split('### Reuse mode', 1)[0]
    rows = _rows_a_failed_check_prints()
    assert len(rows) >= 3, rows
    for label in rows:
        assert f'`{label}`' in participant, f'Participant mode does not name the {label} row'
    assert 'one next step' in participant
    assert 'The participant runs' in participant
