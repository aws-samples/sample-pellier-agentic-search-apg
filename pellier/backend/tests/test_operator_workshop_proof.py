"""A human decision must not be mistaken for a governed business effect."""
import copy
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('review_workshop_proof', Path(__file__).resolve().parents[3] / 'scripts/prove_operator_review.py')
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)
TURN = 'turn-' + 'b' * 32


def proposed():
    return {'review': {'id': 12, 'customer_id': 'CUST-JESSICA', 'tool': 'initiate_return',
        'source_turn_id': TURN, 'action_hash': 'a' * 64, 'write_key': 'operator-review:12:' + 'a' * 32,
        'status': 'pending', 'args': {'customer_id': 'CUST-JESSICA', 'product_id': 24, 'reason': 'changed_mind'}},
        'sourceTurnExists': True, 'toolCalls': [], 'receipts': [], 'writes': [], 'returns': []}


def executed():
    data = proposed()
    data['review'].update(status='approved', decided_by='staff-sub', execution_turn_id='execution-turn')
    key = data['review']['write_key']
    data['receipts'] = [dict(review_id=12, tool='initiate_return', customer_subject='jessica-sub',
        execution_turn_id='execution-turn', actor_principal='staff-sub', idempotency_key=key,
        rail='gateway-mcp', gateway_mode='ENFORCE', policy_outcome='ALLOW', aurora_outcome='PERMITTED')]
    data['toolCalls'] = [dict(tool='initiate_return', caller='gateway', args=dict(idempotency_key=key, customer_id='CUST-JESSICA', product_id=24, reason='changed_mind'))]
    data['writes'] = [dict(idempotency_key=key, completed_at='now', operation='initiate_return',
                          result=dict(status='success', return_id=42))]
    data['returns'] = [dict(id=42, product_id='24', customer_id='CUST-JESSICA', reason='changed_mind')]
    return data


def baseline():
    return proof.assess(proposed(), phase='proposed', source_turn=TURN)


def test_review_confirmation_and_execution_are_separate_observations():
    assert baseline()['passed']
    confirmed = proposed()
    confirmed['review'].update(status='approved', decided_by='staff-sub')
    assert proof.assess(confirmed, phase='confirmed', source_turn=TURN, baseline=baseline())['passed']
    assert not proof.assess(confirmed, phase='executed', source_turn=TURN, baseline=baseline())['passed']
    assert proof.assess(executed(), phase='executed', source_turn=TURN, baseline=baseline())['passed']
    assert not proof.assess(executed(), phase='confirmed', source_turn=TURN, baseline=baseline())['passed']


@pytest.mark.parametrize('section,field,value', [
    ('review','action_hash','c'*64), ('review','source_turn_id','other'),
    ('review','status','pending'), ('review','customer_id','CUST-ANNA'),
    ('receipts','actor_principal','other'), ('receipts','policy_outcome','NOT_EVALUATED'),
    ('receipts','aurora_outcome','DENIED'), ('receipts','gateway_mode','LOG_ONLY'),
    ('receipts','idempotency_key','other'), ('receipts','review_id',99),
    ('writes','completed_at',None), ('writes','idempotency_key','other'),
    ('returns','id',999), ('returns','product_id','99'), ('returns','customer_id','CUST-ANNA'),
])
def test_rejects_changed_terms_or_uncorrelated_execution(section, field, value):
    data = executed()
    target = data[section] if section == 'review' else data[section][0]
    target[field] = value
    assert not proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())['passed']


@pytest.mark.parametrize('section', ['receipts', 'toolCalls', 'writes', 'returns'])
def test_rejects_missing_evidence(section):
    data = executed()
    data[section] = []
    assert not proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())['passed']


def test_rejects_another_baseline_and_duplicate_effects():
    data = executed()
    data['returns'].append(copy.deepcopy(data['returns'][0]))
    assert not proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())['passed']
    wrong = baseline()
    wrong['observed']['review']['id'] = 99
    assert not proof.assess(executed(), phase='executed', source_turn=TURN, baseline=wrong)['passed']


def test_retains_failed_attempt_before_successful_same_key_retry():
    data = executed()
    failed = copy.deepcopy(data['receipts'][0])
    failed.update(policy_outcome='NOT_EVALUATED', aurora_outcome='NOT_REACHED')
    data['receipts'].insert(0, failed)
    report = proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())
    assert report['passed']
    assert report['observed']['receipts'][0]['policy_outcome'] == 'NOT_EVALUATED'
    data['receipts'].reverse()
    assert not proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())['passed']


def test_execution_requires_a_nonempty_assigned_turn():
    data = executed()
    data['review']['execution_turn_id'] = None
    data['receipts'][0]['execution_turn_id'] = None
    assert not proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())['passed']


@pytest.mark.parametrize('field,value', [('product_id',99), ('reason','damaged'),
                                        ('customer_id','CUST-ANNA'), ('idempotency_key','other')])
def test_execution_audit_must_match_the_reviewed_material(field, value):
    data = executed()
    data['toolCalls'][0]['args'][field] = value
    assert not proof.assess(data, phase='executed', source_turn=TURN, baseline=baseline())['passed']
