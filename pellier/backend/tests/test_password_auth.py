"""Password UI boundaries, with synthetic JWT verification and no live AWS calls."""
from unittest.mock import AsyncMock, Mock

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from config import settings
from routes import password_auth as module
from services.cognito_auth import get_cognito_auth_service


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(settings, 'COGNITO_CLIENT_ID', 'test-client')
    monkeypatch.setattr(settings, 'COGNITO_CLIENT_SECRET', None)
    cognito = Mock()
    cognito.exceptions = boto3.client('cognito-idp', region_name='us-east-1',
                                      aws_access_key_id='test', aws_secret_access_key='test').exceptions
    cognito.initiate_auth.return_value = {'AuthenticationResult': {
        'AccessToken': 'verified-access', 'IdToken': 'id', 'RefreshToken': 'refresh',
    }}
    monkeypatch.setattr(module, '_client', lambda: cognito)
    validator = Mock(validate_jwt=AsyncMock())
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_cognito_auth_service] = lambda: validator
    with TestClient(app, base_url='https://pellier.test') as client:
        yield client, cognito, validator


def post(client, path='sign-in', body=None, **kwargs):
    csrf = client.get('/api/auth/password/csrf')
    assert csrf.headers['cache-control'] == 'no-store'
    return client.post('/api/auth/password/' + path,
                       headers={'x-csrf-token': csrf.json()['csrfToken'], **kwargs.pop('headers', {})},
                       json=body or {'username': 'operator', 'password': 'transient-secret'}, **kwargs)


def test_verified_tokens_become_http_only_cookies_not_json(setup):
    client, cognito, validator = setup
    response = post(client, body={'username': 'operator', 'password': 'transient-secret', 'returnTo': '/operator'})
    assert response.json() == {'status': 'signed_in', 'returnTo': '/operator'}
    validator.validate_jwt.assert_awaited_once_with('verified-access')
    assert cognito.initiate_auth.call_args.kwargs['AuthFlow'] == 'USER_PASSWORD_AUTH'
    assert 'transient-secret' not in response.text
    assert 'verified-access' not in response.text
    cookie = next(value for value in response.headers.get_list('set-cookie') if value.startswith('access_token='))
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie


def test_rejects_unverified_token_without_session(setup):
    client, _, validator = setup
    validator.validate_jwt.side_effect = HTTPException(401, 'invalid_jwt')
    response = post(client)
    assert response.status_code == 502
    assert 'access_token' not in client.cookies


@pytest.mark.parametrize('status', [401, 503])
def test_verification_failure_logs_only_class_and_preserves_unavailability(setup, caplog, status):
    client, _, validator = setup
    cause = ValueError('private-verifier-detail verified-access transient-secret')
    failure = HTTPException(status, 'private-verifier-detail')
    failure.__cause__ = cause
    validator.validate_jwt.side_effect = failure
    response = post(client)
    assert response.status_code == (503 if status == 503 else 502)
    assert response.json() == {'detail': 'auth_unavailable'}
    assert 'access_token' not in client.cookies
    assert 'Cognito sign-in verification failed: ValueError' in caplog.text
    for private in ('private-verifier-detail', 'verified-access', 'transient-secret'):
        assert private not in caplog.text
        assert private not in response.text
    validator.validate_jwt.side_effect = None
    assert post(client).status_code == 200
    assert 'access_token' in client.cookies


def test_missing_provider_token_is_diagnosed_without_creating_a_session(setup, caplog):
    client, cognito, validator = setup
    cognito.initiate_auth.return_value = {'AuthenticationResult': {'IdToken': 'private-id'}}
    assert post(client).status_code == 502
    assert 'Cognito sign-in returned no access token' in caplog.text
    assert 'private-id' not in caplog.text
    assert 'access_token' not in client.cookies
    validator.validate_jwt.assert_not_called()


@pytest.mark.parametrize('target', ['https://outside.example', '//outside.example', '/\\outside.example'])
def test_rejects_external_return_destinations(setup, target):
    client, _, _ = setup
    assert post(client, body={'username': 'operator', 'password': 'secret', 'returnTo': target}).json()['returnTo'] == '/'


def test_requires_a_matching_signed_browser_nonce(setup):
    client, cognito, _ = setup
    response = client.post('/api/auth/password/sign-in', json={'username': 'operator', 'password': 'secret'})
    assert response.status_code == 403
    response = post(client, headers={'x-csrf-token': 'forged'})
    assert response.status_code == 403
    cognito.initiate_auth.assert_not_called()


def test_rejects_cross_site_posts_and_expired_state(setup, monkeypatch):
    client, cognito, _ = setup
    assert post(client, headers={'sec-fetch-site': 'cross-site'}).status_code == 403
    monkeypatch.setattr(module, '_verify_state', lambda _token: False)
    assert post(client).status_code == 403
    cognito.initiate_auth.assert_not_called()


@pytest.mark.parametrize('nonce', [b'\xff', b'x' * 1025])
def test_malformed_nonce_is_rejected_without_an_internal_error(setup, nonce):
    client, cognito, _ = setup
    assert post(client, headers={'x-csrf-token': nonce}).status_code == 403
    cognito.initiate_auth.assert_not_called()


def test_does_not_treat_an_authentication_challenge_as_a_session(setup):
    client, cognito, validator = setup
    cognito.initiate_auth.return_value = {'ChallengeName': 'SOFTWARE_TOKEN_MFA', 'Session': 'private-session'}
    response = post(client)
    assert response.json() == {'status': 'verification_required'}
    assert 'private-session' not in response.text
    assert 'access_token' not in client.cookies
    validator.validate_jwt.assert_not_called()


@pytest.mark.parametrize('name', ['NotAuthorizedException', 'UserNotFoundException'])
def test_wrong_credentials_are_indistinguishable(setup, name):
    client, cognito, _ = setup
    cognito.initiate_auth.side_effect = getattr(cognito.exceptions, name)({'Error': {'Code': name, 'Message': 'private'}}, 'InitiateAuth')
    response = post(client)
    assert response.status_code == 401
    assert response.json() == {'detail': 'invalid_credentials'}


def test_input_errors_do_not_echo_passwords(setup):
    client, cognito, _ = setup
    response = post(client, body={'username': 'operator', 'password': 'secret' * 100})
    assert response.status_code == 400
    assert 'secret' not in response.text
    cognito.initiate_auth.assert_not_called()


@pytest.mark.parametrize('name', ['UserNotFoundException', 'InvalidParameterException'])
def test_recovery_does_not_disclose_account_or_contact_existence(setup, name):
    client, cognito, _ = setup
    cognito.forgot_password.side_effect = getattr(cognito.exceptions, name)({'Error': {'Code': name, 'Message': 'private'}}, 'ForgotPassword')
    assert post(client, 'forgot', {'username': 'somebody'}).json() == {'status': 'recovery_requested'}


def test_reset_requires_provider_confirmation_and_never_signs_in(setup):
    client, cognito, _ = setup
    cognito.confirm_forgot_password.return_value = {}
    response = post(client, 'reset', {'username': 'operator', 'password': 'new-secret', 'code': '123456'})
    assert response.json() == {'status': 'password_reset'}
    assert cognito.confirm_forgot_password.call_args.kwargs['ConfirmationCode'] == '123456'
    assert 'access_token' not in client.cookies


def test_maps_throttling_to_a_bounded_retry_message(setup):
    client, cognito, _ = setup
    cognito.initiate_auth.side_effect = cognito.exceptions.TooManyRequestsException({'Error': {'Code': 'TooManyRequestsException', 'Message': 'private'}}, 'InitiateAuth')
    response = post(client)
    assert response.status_code == 429
    assert response.json() == {'detail': 'try_later'}
