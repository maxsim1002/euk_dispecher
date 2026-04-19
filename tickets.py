from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from database import get_db
from auth import get_current_user
from typing import Optional, List
import os
import uuid

router = APIRouter(prefix="/tickets", tags=["tickets"])

class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str = "normal"

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    deadline: Optional[str] = None
    report: Optional[str] = None

@router.get("/")
async def get_tickets(request: Request):
    get_current_user(request)
    conn = get_db()
    tickets = conn.execute(
        "SELECT * FROM tickets ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(t) for t in tickets]

@router.post("/")
async def create_ticket(data: TicketCreate, request: Request):
    user = get_current_user(request)
    conn = get_db()
    conn.execute(
        "INSERT INTO tickets (title, description, priority, created_by) VALUES (?, ?, ?, ?)",
        (data.title, data.description, data.priority, user["id"])
    )
    conn.commit()
    conn.close()
    return {"message": "OK"}

@router.get("/{ticket_id}")
async def get_ticket(ticket_id: int, request: Request):
    get_current_user(request)
    conn = get_db()
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone()
    conn.close()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ne najdeno")
    return dict(ticket)

@router.put("/{ticket_id}")
async def update_ticket(ticket_id: int, data: TicketUpdate, request: Request):
    get_current_user(request)
    conn = get_db()
    if data.status is not None:
        conn.execute(
            "UPDATE tickets SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data.status, ticket_id)
        )
    if data.assigned_to is not None:
        conn.execute(
            "UPDATE tickets SET assigned_to=? WHERE id=?",
            (data.assigned_to, ticket_id)
        )
    if data.deadline is not None:
        conn.execute(
            "UPDATE tickets SET deadline=? WHERE id=?",
            (data.deadline, ticket_id)
        )
    if data.report is not None:
        conn.execute(
            "UPDATE tickets SET report=? WHERE id=?",
            (data.report, ticket_id)
        )
    conn.commit()
    conn.close()
    return {"message": "OK"}

@router.get("/{ticket_id}/comments")
async def get_comments(ticket_id: int, request: Request):
    get_current_user(request)
    conn = get_db()
    comments = conn.execute("""
        SELECT c.*, u.full_name FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.ticket_id = ?
        ORDER BY c.created_at ASC
    """, (ticket_id,)).fetchall()
    conn.close()
    result = []
    for c in comments:
        d = dict(c)
        d['photos'] = d['photo_path'].split(',') if d['photo_path'] else []
        result.append(d)
    return result

@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id: int,
    request: Request,
    text: str = Form(...),
    photos: List[UploadFile] = File(default=[])
):
    user = get_current_user(request)
    photo_paths = []
    for photo in photos:
        if photo.filename:
            ext = photo.filename.split('.')[-1]
            filename = f"{uuid.uuid4()}.{ext}"
            filepath = f"uploads/{filename}"
            with open(filepath, 'wb') as f:
                content = await photo.read()
                f.write(content)
            photo_paths.append(filename)

    conn = get_db()
    conn.execute(
        "INSERT INTO comments (ticket_id, user_id, text, photo_path) VALUES (?, ?, ?, ?)",
        (ticket_id, user["id"], text, ','.join(photo_paths) if photo_paths else None)
    )
    conn.commit()
    conn.close()
    return {"message": "OK"}