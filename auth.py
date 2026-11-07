"""Who is asking. The one place to swap when real CMU email login replaces the mock login."""
import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from config import MOCK_USERS, SESSION_SECRET


@dataclass
class User:
    id: str
    name: str
    role: str


def _sign(uid: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), uid.encode(), "sha256").hexdigest()


def authenticate(username: str, password: str) -> str | None:
    """User id for a right username and password, else None."""
    for uid, u in MOCK_USERS.items():
        if hmac.compare_digest(username.encode(), u["username"].encode()) & hmac.compare_digest(password.encode(), u["password"].encode()):
            return uid
    return None


def session_value(uid: str) -> str:
    return f"{uid}.{_sign(uid)}"


def current_user(request: Request) -> User:
    uid, _, sig = request.cookies.get("uid", "").partition(".")
    if uid not in MOCK_USERS or not hmac.compare_digest(sig, _sign(uid)):
        raise HTTPException(401, "login required")
    u = MOCK_USERS[uid]
    return User(uid, u["name"], u["role"])


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role != "staff":
        raise HTTPException(403, "staff only")
    return user


def require_researcher(user: User = Depends(current_user)) -> User:
    if user.role != "researcher":
        raise HTTPException(403, "researchers only")
    return user
