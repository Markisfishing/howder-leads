"""登入與權限（M1-12 ~ M1-14）。"""

import time
from collections.abc import Callable

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import AppError
from app.services.auth import verify_entra_token

Headers = Callable[[str], dict[str, str]]


def test_me_requires_login(client: TestClient) -> None:
    res = client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_creates_sales_user_on_first_login(client: TestClient, as_user: Headers) -> None:
    res = client.get("/api/v1/me", headers=as_user("sales1@example.com"))
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "sales1@example.com"
    assert body["role"] == "sales"


def test_bootstrap_admin_email_gets_admin_role(client: TestClient, as_user: Headers) -> None:
    assert client.get("/api/v1/me", headers=as_user("admin@example.com")).json()["role"] == "admin"


def test_sales_cannot_call_admin_api(client: TestClient, as_user: Headers) -> None:
    res = client.get("/api/v1/admin/users", headers=as_user("sales1@example.com"))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_admin_can_change_role_and_disable_user(client: TestClient, as_user: Headers) -> None:
    admin = as_user("admin@example.com")
    uid = client.get("/api/v1/me", headers=as_user("sales1@example.com")).json()["user_id"]
    res = client.patch(f"/api/v1/admin/users/{uid}", json={"role": "manager"}, headers=admin)
    assert res.json()["role"] == "manager"
    client.patch(f"/api/v1/admin/users/{uid}", json={"is_active": False}, headers=admin)
    res = client.get("/api/v1/me", headers=as_user("sales1@example.com"))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "USER_DISABLED"


def test_admin_cannot_demote_self(client: TestClient, as_user: Headers) -> None:
    admin = as_user("admin@example.com")
    uid = client.get("/api/v1/me", headers=admin).json()["user_id"]
    res = client.patch(f"/api/v1/admin/users/{uid}", json={"role": "sales"}, headers=admin)
    assert res.status_code == 409


# ---------- Entra token 驗證（用自己產生的金鑰模擬，不連網）----------
TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key: rsa.RSAPrivateKey, **overrides: object) -> str:
    claims: dict[str, object] = {
        "aud": CLIENT,
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "exp": int(time.time()) + 600,
        "preferred_username": "Sales.One@Example.com",
        "name": "業務一號",
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def _settings() -> Settings:
    return Settings(env="test", auth_mode="entra", entra_tenant_id=TENANT, entra_client_id=CLIENT)


def test_entra_token_valid(rsa_key: rsa.RSAPrivateKey) -> None:
    ident = verify_entra_token(_token(rsa_key), _settings(), signing_key=rsa_key.public_key())
    assert ident.email == "sales.one@example.com"
    assert ident.display_name == "業務一號"


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "someone-else"}, {"iss": "https://evil.example.com"}, {"exp": int(time.time()) - 10}],
)
def test_entra_token_rejected(rsa_key: rsa.RSAPrivateKey, overrides: dict[str, object]) -> None:
    with pytest.raises(AppError) as exc:
        verify_entra_token(_token(rsa_key, **overrides), _settings(), signing_key=rsa_key.public_key())
    assert exc.value.code == "INVALID_TOKEN"


def test_dev_auth_forbidden_in_production() -> None:
    with pytest.raises(ValueError):
        Settings(env="production", auth_mode="dev")


def test_live_mail_needs_allowlist_outside_production() -> None:
    with pytest.raises(ValueError):
        Settings(env="development", mail_mode="live")
