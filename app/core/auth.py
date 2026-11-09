"""Who is asking. The one place to swap when real CMU email login replaces the mock login."""
import hmac
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from app.core import state
from app.core.config import DEV_LOGIN, MOCK_USERS, SESSION_SECRET, SESSION_TTL


@dataclass
class User:
    id: str
    name: str
    role: str


def _sign(uid: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), uid.encode(), "sha256").hexdigest()


def authenticate(username: str, password: str) -> str | None:
    """User id for a right username and password, else None. Mock only: passwords live in config, never in the users table."""
    if DEV_LOGIN and hmac.compare_digest(username.strip().lower().encode(), DEV_LOGIN[0].encode()) & hmac.compare_digest(password.encode(), DEV_LOGIN[1].encode()):
        return DEV_LOGIN[0]  # the user id is the email; the login endpoint still requires an active row in the users table
    for uid, u in MOCK_USERS.items():
        if hmac.compare_digest(username.encode(), u["username"].encode()) & hmac.compare_digest(password.encode(), u["password"].encode()):
            return uid
    return None


def session_value(uid: str) -> str:
    exp = int(time.time()) + SESSION_TTL
    return f"{uid}.{exp}.{_sign(f'{uid}.{exp}')}"


_fails: dict[str, list[float]] = {}  # "ip|username" -> times of recent wrong logins
MAX_FAILS, FAIL_WINDOW = 5, 300


def login_allowed(key: str) -> bool:
    now = time.time()
    recent = _fails[key] = [t for t in _fails.get(key, []) if now - t < FAIL_WINDOW]
    return len(recent) < MAX_FAILS


def login_failed(key: str) -> None:  # ponytail: in memory, per ip+username; shared store if more than one server process runs
    _fails.setdefault(key, []).append(time.time())


def current_user(request: Request) -> User:
    parts = request.cookies.get("uid", "").rsplit(".", 2)  # id.expiry.signature: split from the right, an email id has dots of its own
    uid, exp, sig = parts if len(parts) == 3 else ("", "", "")
    if (not exp.isdigit() or int(exp) < time.time()
            or not hmac.compare_digest(sig.encode(), _sign(f"{uid}.{exp}").encode())):
        raise HTTPException(401, "login required")
    u = state.get_tracker().get_user(uid, active_only=True)  # read every request: a role change applies without a new login and a disabled person is out at once
    if u is None:
        raise HTTPException(401, "login required")
    return User(u["id"], u["name"], u["role"])


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role != "staff":
        raise HTTPException(403, "staff only")
    return user


def require_researcher(user: User = Depends(current_user)) -> User:
    if user.role != "researcher":
        raise HTTPException(403, "researchers only")
    return user
