"""Who is asking. The one place to swap when real CMU email login replaces the mock login."""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from config import MOCK_USERS


@dataclass
class User:
    id: str
    name: str
    role: str


def current_user(request: Request) -> User:
    # ponytail: plain uid cookie, anyone can forge it; replaced by CMU email login before real use
    uid = request.cookies.get("uid")
    if uid not in MOCK_USERS:
        raise HTTPException(401, "login required")
    return User(uid, **MOCK_USERS[uid])


def require_staff(user: User = Depends(current_user)) -> User:
    if user.role != "staff":
        raise HTTPException(403, "staff only")
    return user
