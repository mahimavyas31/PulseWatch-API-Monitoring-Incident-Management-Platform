from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.security import DUMMY_HASH, hash_password, verify_password


class EmailTaken(Exception):
    pass


def create_user(db: Session, email: str, password: str) -> User:
    if db.scalar(select(User).where(User.email == email)):
        raise EmailTaken()
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_password(password, DUMMY_HASH)  # equalise timing
        return None
    return user if verify_password(password, user.password_hash) else None
