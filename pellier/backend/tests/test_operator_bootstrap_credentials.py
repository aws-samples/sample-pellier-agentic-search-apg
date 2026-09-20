import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("staff_credentials", ROOT / "scripts/store_operator_credential.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_staff_rotation_preserves_shoppers_and_secret_metadata():
    client = Mock()
    shopper = {"username": "marco", "password": "synthetic-shopper"}
    client.get_secret_value.return_value = {"SecretString": json.dumps({
        "users": [shopper, {"username": "operator", "password": "synthetic-old"}],
        "pool": "synthetic-pool",
    })}
    module.store(client, "test-secret", "operator", "synthetic-new")
    saved = json.loads(client.put_secret_value.call_args.kwargs["SecretString"])
    assert saved == {"pool": "synthetic-pool", "users": [shopper, {
        "username": "operator", "password": "synthetic-new",
    }]}


def test_invalid_secret_shape_is_not_overwritten():
    client = Mock()
    client.get_secret_value.return_value = {"SecretString": '{"users": {}}'}
    with pytest.raises(ValueError):
        module.store(client, "test-secret", "operator", "synthetic-new")
    client.put_secret_value.assert_not_called()


def test_readiness_and_lab_proof_share_the_managed_credential():
    bootstrap = (ROOT / "scripts/bootstrap-labs.sh").read_text()
    gate = (ROOT / "scripts/health-gate.sh").read_text()
    assert 'scripts/store_operator_credential.py' in bootstrap
    assert 'secrets.token_urlsafe(24)' in bootstrap
    assert 'Pellier-${WORKSHOP_ID:-dat416}-Operator1' not in gate
    assert '--arg username "$operator_user"' in gate
