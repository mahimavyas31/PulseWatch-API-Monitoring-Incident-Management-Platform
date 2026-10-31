import hashlib
import hmac
import os
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.utils import utcnow

COOKIE_NAME = "access_token"
ALGORITHM = "HS256"
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


# Used so that login takes similar time whether or not the email exists.
DUMMY_HASH = hash_password("not-a-real-password")


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id),
               "exp": utcnow() + timedelta(minutes=settings.token_expire_minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


bearer_scheme = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """REST API auth: Authorization: Bearer <token>."""
    user = _user_from_token(creds.credentials if creds else None, db)
    if user is None:
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return user


def web_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Dashboard auth: HttpOnly cookie. Returns None when logged out."""
    return _user_from_token(request.cookies.get(COOKIE_NAME), db)
