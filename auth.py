from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from database import get_db
from passlib.hash import bcrypt
from jose import jwt, JWTError
import os
from dotenv import load_dotenv
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

router = APIRouter(prefix="/auth", tags=["auth"])


# ── JWT ──────────────────────────────────────────────────────────

def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(request: Request) -> dict:
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Недействительный токен")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return dict(user)


# ── Pydantic схемы ───────────────────────────────────────────────

class LoginData(BaseModel):
    username: str
    password: str

class RegisterData(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "executor"

class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None


# ── Эндпоинты ────────────────────────────────────────────────────

@router.post("/login")
async def login(data: LoginData, response: Response):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (data.username,)
    ).fetchone()
    conn.close()

    if not user or not pwd_context.verify(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_token(user["id"], user["role"])
    response.set_cookie("token", token, max_age=86400*TOKEN_EXPIRE_DAYS, httponly=True)
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"]
    }

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("token")
    return {"message": "Выход выполнен"}

@router.get("/me")
async def get_me(request: Request):
    return get_current_user(request)

@router.post("/register")
async def register(data: RegisterData, request: Request):
    current_user = get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Только admin может создавать пользователей")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)",
            (data.username, bcrypt.hash(data.password), data.full_name, data.role)
        )
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    conn.close()
    return {"message": "Пользователь создан"}

@router.get("/users")
async def get_users(request: Request):
    get_current_user(request)
    conn = get_db()
    users = conn.execute(
        "SELECT id, username, full_name, role FROM users"
    ).fetchall()
    conn.close()
    return [dict(u) for u in users]

@router.put("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate, request: Request):
    current_user = get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Нет прав")
    conn = get_db()
    if data.role:
        conn.execute("UPDATE users SET role=? WHERE id=?", (data.role, user_id))
    if data.password:
        conn.execute(
            "UPDATE users SET password=? WHERE id=?",
            (bcrypt.hash(data.password), user_id)
        )
    conn.commit()
    conn.close()
    return {"message": "OK"}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request):
    current_user = get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Нет прав")
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "OK"}