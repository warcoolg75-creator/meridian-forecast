"""Authentication: sign-in, the login rate limit, refresh rotation, sign-out, /me,
password change, the role guard, demo users and UTC timestamps."""

from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.api.v1.auth import COOKIE_PATH, INVALID_CREDENTIALS, REFRESH_COOKIE
from app.models import RefreshToken, User, UserRole
from app.models.base import utcnow
from app.seed.users import DEMO_PASSWORD, DEMO_USERS, add_demo_users
from app.services import auth
from app.services.rate_limit import login_limiter
from tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
CHANGE_PASSWORD = "/api/v1/auth/change-password"
NEW_PASSWORD = "a brand new password"


def login(client, email="planner@example.com", password=TEST_PASSWORD, remember=False):
    return client.post(LOGIN, json={"email": email, "password": password, "remember": remember})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refresh_cookie(response) -> str:
    """The raw Set-Cookie header of the refresh cookie."""
    for value in response.headers.get_list("set-cookie"):
        if value.startswith(f"{REFRESH_COOKIE}="):
            return value
    raise AssertionError("the response set no refresh cookie")


def refresh_token_in(response) -> str:
    return refresh_cookie(response).split(";", 1)[0].split("=", 1)[1]


def refresh_with(client, token: str):
    """POST /refresh presenting exactly `token` (not whatever the cookie jar holds)."""
    client.cookies.clear()
    return client.post(REFRESH, headers={"Cookie": f"{REFRESH_COOKIE}={token}"})


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ------------------------------------------------------------------------------ sign-in


def test_login_returns_an_access_token_and_a_hardened_refresh_cookie(client, db, make_user):
    user = make_user()
    response = login(client, email="  Planner@Example.COM ", remember=True)  # emails are case-insensitive

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 15 * 60
    assert body["user"]["email"] == "planner@example.com" and body["user"]["role"] == "planner"
    claims = auth.decode_token(body["access_token"], auth.ACCESS)
    assert claims["sub"] == str(user.id) and claims["role"] == "planner"

    cookie = refresh_cookie(response).lower()
    for attribute in ("httponly", "secure", "samesite=lax", f"path={COOKIE_PATH}", "max-age=604800"):
        assert attribute in cookie
    assert refresh_token_in(response) not in response.text  # the refresh token never appears in the body
    db.refresh(user)
    assert utcnow() - user.last_login_at < timedelta(minutes=1)


def test_without_remember_me_the_refresh_cookie_is_a_browser_session_cookie(client, make_user):
    make_user()
    cookie = refresh_cookie(login(client, remember=False)).lower()
    assert "max-age" not in cookie and "expires" not in cookie


def test_failed_sign_in_reveals_nothing_about_the_account(client, make_user):
    make_user()
    make_user(email="former@example.com", is_active=False)
    responses = [
        login(client, password="wrong password"),  # real account, wrong password
        login(client, email="nobody@example.com"),  # no such account
        login(client, email="former@example.com"),  # deactivated account, right password
    ]
    assert [r.status_code for r in responses] == [401, 401, 401]
    assert [r.json() for r in responses] == [{"detail": INVALID_CREDENTIALS}] * 3
    assert all("set-cookie" not in r.headers for r in responses)


def test_unknown_email_runs_the_same_argon2_check_as_a_wrong_password(client, make_user, monkeypatch):
    """The timing defence is exercised, not just the message: an unknown email still
    costs one full argon2 verification, against a hash with the same parameters."""
    make_user()
    checked: list[str] = []
    real_verify = auth.verify_password

    def spy(password: str, password_hash: str) -> bool:
        checked.append(password_hash)
        return real_verify(password, password_hash)

    monkeypatch.setattr(auth, "verify_password", spy)

    login(client, email="nobody@example.com", password="anything")
    assert checked == [auth.DUMMY_PASSWORD_HASH]

    login(client, password="wrong password")
    assert len(checked) == 2 and checked[1] != auth.DUMMY_PASSWORD_HASH

    def cost(argon2_hash: str) -> list[str]:  # $argon2id$v=19$m=65536,t=3,p=4$salt$hash
        return argon2_hash.split("$")[1:4]

    assert cost(auth.DUMMY_PASSWORD_HASH) == cost(checked[1])


# ------------------------------------------------------------------------------ rate limit


def test_sixth_attempt_after_five_failures_is_rate_limited(client, make_user, monkeypatch):
    make_user()
    clock = FakeClock()
    monkeypatch.setattr(login_limiter, "clock", clock)

    for _ in range(5):
        assert login(client, password="wrong password").status_code == 401
    blocked = login(client)  # the right password, but blocked all the same
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["Retry-After"]) <= 15 * 60
    assert blocked.json()["detail"].startswith("Too many sign-in attempts")

    # Keyed on IP + email, and unknown emails are limited exactly like real ones,
    # so a 429 does not reveal whether an account exists either.
    for _ in range(5):
        assert login(client, email="nobody@example.com").status_code == 401
    assert login(client, email="nobody@example.com").status_code == 429

    # The window slides: 15 minutes after the failures, the right password works again.
    clock.advance(15 * 60)
    assert login(client).status_code == 200


def test_a_successful_sign_in_clears_the_failure_count(client, make_user):
    make_user()
    for _ in range(4):
        assert login(client, password="wrong password").status_code == 401
    assert login(client).status_code == 200
    for _ in range(5):
        assert login(client, password="wrong password").status_code == 401
    assert login(client, password="wrong password").status_code == 429


# ------------------------------------------------------------------------------ refresh


def test_refresh_uses_the_cookie_and_rotates_it(client, make_user):
    make_user()
    first = login(client)
    rotated = client.post(REFRESH)  # the cookie jar sends the Secure, path-scoped cookie back

    assert rotated.status_code == 200
    assert auth.decode_token(rotated.json()["access_token"], auth.ACCESS)["sub"]
    assert refresh_token_in(rotated) != refresh_token_in(first)
    assert client.post(REFRESH).status_code == 200  # the new cookie works in turn


def test_a_replayed_refresh_token_revokes_the_whole_sign_in(client, db, make_user):
    make_user()
    token_a = refresh_token_in(login(client))
    token_b = refresh_token_in(refresh_with(client, token_a))
    token_c = refresh_token_in(refresh_with(client, token_b))

    replay = refresh_with(client, token_a)  # A was already spent: treat as stolen
    assert replay.status_code == 401
    assert "max-age=0" in refresh_cookie(replay).lower()  # and the cookie is cleared
    assert refresh_with(client, token_c).status_code == 401  # C was never used, but its family is gone

    db.expire_all()
    rows = db.scalars(sa.select(RefreshToken)).all()
    assert len(rows) == 3 and all(row.revoked_at is not None for row in rows)


def test_refresh_rejects_missing_malformed_wrong_type_and_expired_tokens(client, db, make_user):
    user = make_user()
    client.cookies.clear()
    assert client.post(REFRESH).status_code == 401
    assert refresh_with(client, "not-a-jwt").status_code == 401
    assert refresh_with(client, auth.create_access_token(user, utcnow())).status_code == 401

    stale = auth.issue_refresh_token(db, user, persistent=True, now=utcnow() - timedelta(days=8))
    db.commit()
    assert refresh_with(client, stale.token).status_code == 401


# ------------------------------------------------------------------------------ logout, me, password


def test_logout_revokes_the_session_and_clears_the_cookie(client, make_user):
    make_user()
    token = refresh_token_in(login(client))

    out = client.post(LOGOUT)
    assert out.status_code == 200 and out.json() == {"status": "signed_out"}
    assert "max-age=0" in refresh_cookie(out).lower()
    assert refresh_with(client, token).status_code == 401

    client.cookies.clear()
    assert client.post(LOGOUT).status_code == 200  # signing out without a session is fine


def test_me_needs_a_valid_unexpired_access_token(client, db, make_user):
    user = make_user()
    token = auth.create_access_token(user, utcnow())

    assert client.get(ME).status_code == 401
    assert client.get(ME, headers=bearer("not-a-jwt")).status_code == 401
    expired = auth.create_access_token(user, utcnow() - timedelta(minutes=16))
    assert client.get(ME, headers=bearer(expired)).status_code == 401
    refresh_token = auth.issue_refresh_token(db, user, persistent=False, now=utcnow()).token
    db.commit()
    assert client.get(ME, headers=bearer(refresh_token)).status_code == 401  # wrong token type

    me = client.get(ME, headers=bearer(token))
    assert me.status_code == 200 and me.json()["email"] == "planner@example.com"

    user.is_active = False  # deactivation applies at once, not when the token expires
    db.commit()
    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_change_password_needs_the_current_one_and_signs_out_other_sessions(client, make_user):
    make_user()
    other_browser = refresh_token_in(login(client))
    session = login(client)
    headers = bearer(session.json()["access_token"])

    def change(current: str, new: str):
        return client.post(CHANGE_PASSWORD, json={"current_password": current, "new_password": new},
                           headers=headers)

    assert client.post(CHANGE_PASSWORD, json={"current_password": TEST_PASSWORD,
                                              "new_password": NEW_PASSWORD}).status_code == 401
    assert change("not my password", NEW_PASSWORD).status_code == 400
    assert change(TEST_PASSWORD, "too short").status_code == 422
    assert change(TEST_PASSWORD, TEST_PASSWORD).status_code == 400

    changed = change(TEST_PASSWORD, NEW_PASSWORD)
    assert changed.status_code == 200 and changed.json()["access_token"]
    assert refresh_with(client, other_browser).status_code == 401
    assert refresh_with(client, refresh_token_in(changed)).status_code == 200  # this session lives on
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


# ------------------------------------------------------------------------------ role guard


@pytest.mark.parametrize(
    "role, expected",
    [(None, 401), (UserRole.VIEWER, 403), (UserRole.ANALYST, 403), (UserRole.PLANNER, 200), (UserRole.ADMIN, 200)],
)
def test_sales_import_is_limited_to_admins_and_planners(client, ids, auth_headers, role, expected):
    template = client.get("/api/v1/imports/sales/template").text
    headers = auth_headers(role) if role else {}
    response = client.post("/api/v1/imports/sales", files={"file": ("sales.csv", template.encode(), "text/csv")},
                           headers=headers)
    assert response.status_code == expected


# ------------------------------------------------------------------------------ seed & timestamps


def test_seed_creates_one_demo_user_per_role_with_the_demo_password(db):
    add_demo_users(db)
    db.commit()
    users = db.scalars(sa.select(User).order_by(User.id)).all()
    assert [(u.email, u.role) for u in users] == [(email, role) for email, _name, role in DEMO_USERS]
    assert {u.role for u in users} == set(UserRole)
    assert all(auth.verify_password(DEMO_PASSWORD, u.password_hash) for u in users)


def test_timestamps_are_timezone_aware_utc_on_every_dialect(db, make_user):
    user = make_user()
    user.last_login_at = utcnow()
    db.commit()
    db.expire_all()
    loaded = db.get(User, user.id)
    for value in (loaded.created_at, loaded.last_login_at):
        assert value.tzinfo is not None and value.utcoffset() == timedelta(0)

    loaded.last_login_at = loaded.last_login_at.replace(tzinfo=None)  # naive input is a bug
    with pytest.raises(sa.exc.StatementError):
        db.commit()
    db.rollback()
