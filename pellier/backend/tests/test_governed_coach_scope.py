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
        assert exercise.marker.removeprefix('WORKSHOP · ') in root
        if exercise.destination.startswith('pellier/backend/'):
            assert exercise.destination.removeprefix('pellier/backend/') in backend
    for exercise in module.FILE_EXERCISES:
        assert exercise.destination in root
    assert 'Lab 1 only' not in backend
    assert 'prediction' in root and 'one hint' in root
    assert 'Never inspect `solutions/`' in backend
