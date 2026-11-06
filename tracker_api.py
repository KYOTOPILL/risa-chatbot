"""Tracking dashboard API: mock login, submissions, step moves. Rules live in tracker.py; this only maps users and HTTP."""
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import state
from config import MOCK_USERS

router = APIRouter(prefix="/api/track")


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


class LoginIn(BaseModel):
    user_id: str


class SubmissionIn(BaseModel):
    title: str
    version_id: int
    researcher_ids: list[str]
    staff_id: str


class MoveIn(BaseModel):
    to_step: int
    note: str = ""


@router.get("/mock-users")
def mock_users():
    return [{"id": i, **u} for i, u in MOCK_USERS.items()]


@router.post("/login")
def login(body: LoginIn, response: Response):
    if body.user_id not in MOCK_USERS:
        raise HTTPException(401, "unknown user")
    response.set_cookie("uid", body.user_id, httponly=True, samesite="lax")
    return {"id": body.user_id, **MOCK_USERS[body.user_id]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("uid")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "role": user.role}


@router.get("/submissions")
def submissions(user: User = Depends(current_user)):
    return state.get_tracker().list_submissions(user.id, user.role)


@router.get("/submissions/{sid}")
def submission(sid: int, user: User = Depends(current_user)):
    sub = state.get_tracker().get_submission(sid, user.id, user.role)
    if sub is None:  # missing and not-yours look the same
        raise HTTPException(404, "not found")
    return sub


@router.post("/submissions")
def create_submission(body: SubmissionIn, _: User = Depends(require_staff)):
    people = [*body.researcher_ids, body.staff_id]
    if any(p not in MOCK_USERS for p in people) or MOCK_USERS[body.staff_id]["role"] != "staff" \
            or any(MOCK_USERS[r]["role"] != "researcher" for r in body.researcher_ids):
        raise HTTPException(400, "unknown user or wrong role")
    try:
        return {"id": state.get_tracker().create_submission(body.title, body.version_id, body.researcher_ids, body.staff_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/submissions/{sid}/move")
def move(sid: int, body: MoveIn, user: User = Depends(require_staff)):
    try:
        state.get_tracker().move_step(sid, user.id, body.to_step, body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
