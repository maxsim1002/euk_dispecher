from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from database import get_db, init_db
from auth import router as auth_router, get_current_user
from tickets import router as tickets_router
import os
import json


app = FastAPI(title="Dispatch App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.include_router(auth_router)
app.include_router(tickets_router)

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/static/{filename}")
async def static_files(filename: str):
    filepath = f"static/{filename}"
    if os.path.exists(filepath):
        return FileResponse(filepath)
    return {"detail": "Not Found"}

# WebSocket чат
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.get("/chat/history")
async def chat_history(request: Request):
    from auth import get_current_user
    from database import get_db   # <-- добавить эту строку
    get_current_user(request)
    conn = get_db()
    messages = conn.execute("""
        SELECT m.*, u.full_name FROM messages m
        JOIN users u ON m.user_id = u.id
        ORDER BY m.created_at ASC
        LIMIT 100
    """).fetchall()
    conn.close()
    return [dict(m) for m in messages]

def get_user_from_token(websocket: WebSocket):
    token = websocket.cookies.get("token")
    if not token:
        return None
    try:
        from jose import jwt, JWTError
        import os
        from dotenv import load_dotenv
        load_dotenv()
        SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
        ALGORITHM = "HS256"
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        # проверим, существует ли пользователь в БД
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return user
    except Exception:
        return None

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await manager.connect(websocket)
    user = get_user_from_token(websocket)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    # Отправляем историю сообщений при подключении
    conn = get_db()
    history = conn.execute("""
        SELECT m.*, u.full_name FROM messages m
        JOIN users u ON m.user_id = u.id
        ORDER BY m.created_at DESC LIMIT 50
    """).fetchall()
    conn.close()
    for msg in reversed(history):
        await websocket.send_json({
            "user_id": msg["user_id"],
            "full_name": msg["full_name"],
            "text": msg["text"],
            "time": msg["created_at"]
        })

    try:
        while True:
            data = await websocket.receive_json()
            conn = get_db()
            conn.execute(
                "INSERT INTO messages (user_id, text) VALUES (?, ?)",
                (user["id"], data["text"])
            )
            conn.commit()
            conn.close()
            await manager.broadcast({
                "user_id": user["id"],
                "full_name": user["full_name"],
                "text": data["text"],
                "time": None  # можно сгенерировать datetime.now()
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/health")
def health():
    return {"status": "ok"}
