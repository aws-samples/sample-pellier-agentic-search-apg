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
        "users": [shopper, {"username": "nadia", "password": "synthetic-old"}],
        "pool": "synthetic-pool",
    })}
    module.store(client, "test-secret", "nadia", "synthetic-new")
    saved = json.loads(client.put_secret_value.call_args.kwargs["SecretString"])
    assert saved == {"pool": "synthetic-pool", "users": [shopper, {
        "username": "nadia", "password": "synthetic-new",
    }]}


def test_invalid_secret_shape_is_not_overwritten():
    client = Mock()
    client.get_secret_value.return_value = {"SecretString": '{"users": {}}'}
    with pytest.raises(ValueError):
        module.store(client, "test-secret", "nadia", "synthetic-new")
    client.put_secret_value.assert_not_called()


def test_nadia_is_the_staff_user_everywhere_she_is_provisioned():
    """One staff identity, named the same in the seed, the gate and the credentials file."""
    bootstrap = (ROOT / "scripts/bootstrap-labs.sh").read_text()
    gate = (ROOT / "scripts/health-gate.sh").read_text()
    credentials = (ROOT / "scripts/write-test-credentials.sh").read_text()
    assert 'OPERATOR_USERNAME="${PELLIER_OPERATOR_USERNAME:-nadia}"' in bootstrap
    assert 'operator_user="${PELLIER_OPERATOR_USERNAME:-nadia}"' in gate
    assert 'scripts/store_operator_credential.py' in bootstrap
    assert 'secrets.token_urlsafe(24)' in bootstrap
    assert '--arg username "$operator_user"' in gate
    # The shopper filter follows the configured staff name; no literal is left.
    assert '!="operator"' not in gate and '!="nadia"' not in gate
    assert 'ROLE_LABEL[5]="Staff (Nadia)' in credentials
