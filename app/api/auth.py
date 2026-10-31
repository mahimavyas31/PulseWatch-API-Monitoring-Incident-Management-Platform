from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginIn, TokenOut, UserCreate, UserOut
from app.security import create_token, current_user
from app.services.users import EmailTaken, authenticate, create_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: UserCreate, db: Session = Depends(get_db)):
    try:
        return create_user(db, body.email, body.password)
    except EmailTaken:
        raise HTTPException(409, "Email already registered")


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(401, "Invalid email or password")
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
