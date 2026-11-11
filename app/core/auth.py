"""Who is asking. The one place to swap when real CMU email login replaces the mock login."""
import hmac
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from app.core import state
from urllib.parse import urlsplit

from app.core.config import DEV_LOGIN, EXPOSED, IDLE_SECONDS, MOCK_USERS, PUBLIC_URL, SESSION_SECRET, SESSION_TTL


@dataclass
class User:
    id: str
    name: str
    role: str


def _sign(message: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), message.encode(), "sha256").hexdigest()


def authenticate(username: str, password: str) -> str | None:
    """User id for a right username and password, else None. Mock only: passwords live in config, never in the users table."""
    if DEV_LOGIN and hmac.compare_digest(username.strip().lower().encode(), DEV_LOGIN[0].encode()) & hmac.compare_digest(password.encode(), DEV_LOGIN[1].encode()):
        return DEV_LOGIN[0]  # the user id is the email; the login endpoint still requires an active row in the users table
    for uid, u in MOCK_USERS.items():
        if EXPOSED and u["default"]:
            continue  # a demo account on its public demo password is off while the app is reachable from outside
        if hmac.compare_digest(username.encode(), u["username"].encode()) & hmac.compare_digest(password.encode(), u["password"].encode()):
            return uid
    return None


REFRESH_AFTER = 60  # seconds: a busy person gets a fresh cookie at most once a minute, not on every request
PASSIVE = {"/api/track/notifications"}  # the bell asks every minute by itself: that is not the person using the app, so it never extends the session


def session_value(uid: str, epoch: int = 0, start: int | None = None) -> str:
    """id.start.expiry.signature. `start` is when the login began (the 8 h cap counts from it), `expiry` moves forward with use (idle limit).
    The signature also covers the person's session number (not in the cookie): logging out raises it and kills every cookie made before."""
    now = int(time.time())
    start = start or now
    exp = min(now + IDLE_SECONDS, start + SESSION_TTL)
    return f"{uid}.{start}.{exp}.{_sign(f'{uid}.{start}.{exp}.{epoch}')}"


_fails: dict[str, list[float]] = {}  # "ip|username" -> times of recent wrong logins
MAX_FAILS, FAIL_WINDOW = 5, 300
IP_MAX_FAILS = 30  # wrong logins from one address across all usernames in the window


def login_allowed(key: str, limit: int = MAX_FAILS) -> bool:
    now = time.time()
    recent = _fails[key] = [t for t in _fails.get(key, []) if now - t < FAIL_WINDOW]
    return len(recent) < limit


def login_failed(key: str) -> None:  # ponytail: in memory, per ip+username; shared store if more than one server process runs
    _fails.setdefault(key, []).append(time.time())


def current_user(request: Request) -> User:
    parts = request.cookies.get("uid", "").rsplit(".", 3)  # id.start.expiry.signature: split from the right, an email id has dots of its own
    uid, start, exp, sig = parts if len(parts) == 4 else ("", "", "", "")
    now = time.time()
    live = start.isdigit() and exp.isdigit() and now < int(exp) and now < int(start) + SESSION_TTL
    row = state.get_tracker().login_row(uid) if live else None  # read every request, so a role change applies without a new login
    if row is None or not hmac.compare_digest(sig.encode(), _sign(f"{uid}.{start}.{exp}.{row['session_epoch']}").encode()):
        raise HTTPException(401, "login required")  # also: idle too long, disabled, or logged out since (the session number moved)
    if request.url.path not in PASSIVE and int(exp) - now < IDLE_SECONDS - REFRESH_AFTER:
        request.state.new_session = session_value(uid, row["session_epoch"], int(start))  # the middleware in server.py puts it on the response
    return User(row["id"], row["name"], row["role"])


def same_origin(request: Request) -> None:
    """Block a cross-site browser post that carries the login cookie. Browsers send Origin on those; it must name this site (the Host, the proxy's
    forwarded host, or RISA_PUBLIC_URL). A request with no Origin (a script, a test, LINE's webhook) is not a browser form post and passes."""
    origin = request.headers.get("origin")
    if request.method in ("GET", "HEAD", "OPTIONS") or not origin:
        return
    ok = {request.headers.get("host", ""), request.headers.get("x-forwarded-host", ""), urlsplit(PUBLIC_URL).netloc} - {""}
    if urlsplit(origin).netloc not in ok:
        raise HTTPException(403, "cross-site request blocked")


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role != "staff":
        raise HTTPException(403, "staff only")
    return user


def require_researcher(user: User = Depends(current_user)) -> User:
    if user.role != "researcher":
        raise HTTPException(403, "researchers only")
    return user
