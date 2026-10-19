from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token, hash_password, verify_password
from app.main import app
from app.models.user import User, UserRole


class FakeResult:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def scalar_one_or_none(self) -> User | None:
        return self.user


class FakeSession:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.added: User | None = None

    async def execute(self, _statement: object) -> FakeResult:
        return FakeResult(self.user)

    def add(self, user: User) -> None:
        self.added = user
        if user.id is None:
            user.id = uuid4()

    async def commit(self) -> None:
        return None

    async def refresh(self, _user: User) -> None:
        return None

    async def rollback(self) -> None:
        return None


def make_user(role: str = UserRole.USER.value, password: str = "correct-password") -> User:
    return User(
        id=uuid4(),
        email=f"{role}@example.com",
        password_hash=hash_password(password),
        role=role,
    )


@pytest.fixture(autouse=True)
def configured_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-only-secret-long-enough-for-hs256")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "jwt_access_token_expire_minutes", 30)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def use_user() -> Callable[[User | None], FakeSession]:
    sessions: list[FakeSession] = []

    def configure(user: User | None) -> FakeSession:
        session = FakeSession(user)
        sessions.append(session)

        async def override_get_db() -> AsyncIterator[FakeSession]:
            yield session

        app.dependency_overrides[get_db] = override_get_db
        return session

    yield configure
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_passwords_are_hashed_and_wrong_passwords_fail() -> None:
    password_hash = hash_password("correct-password")

    assert password_hash != "correct-password"
    assert verify_password("correct-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


@pytest.mark.asyncio
async def test_register_returns_public_user_data_only(
    client: AsyncClient,
    use_user: Callable[[User | None], FakeSession],
) -> None:
    session = use_user(None)

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "NewUser@Example.com", "password": "correct-password"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(session.added.id),
        "email": "newuser@example.com",
        "role": "user",
    }
    assert "password_hash" not in response.text
    assert session.added is not None
    assert verify_password("correct-password", session.added.password_hash)


@pytest.mark.asyncio
async def test_login_returns_jwt_without_password_hash(
    client: AsyncClient,
    use_user: Callable[[User | None], FakeSession],
) -> None:
    user = make_user()
    use_user(user)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {"id": str(user.id), "email": user.email, "role": "user"}
    assert "password_hash" not in response.text
    assert decode_access_token(body["access_token"])["sub"] == str(user.id)


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(
    client: AsyncClient,
    use_user: Callable[[User | None], FakeSession],
) -> None:
    user = make_user()
    use_user(user)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_user_route_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/user/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/user/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ordinary_user_cannot_access_admin_route(
    client: AsyncClient,
    use_user: Callable[[User | None], FakeSession],
) -> None:
    user = make_user()
    use_user(user)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct-password"},
    )

    response = await client.get(
        "/api/v1/admin/access-check",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


@pytest.mark.asyncio
async def test_admin_can_access_admin_route(
    client: AsyncClient,
    use_user: Callable[[User | None], FakeSession],
) -> None:
    admin = make_user(role=UserRole.ADMIN.value)
    use_user(admin)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "correct-password"},
    )

    response = await client.get(
        "/api/v1/admin/access-check",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "authorized", "role": "admin"}
