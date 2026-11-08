from app.core.config import MOCK_USERS

CREDS = {i: {"username": u["username"], "password": u["password"]} for i, u in MOCK_USERS.items()}
