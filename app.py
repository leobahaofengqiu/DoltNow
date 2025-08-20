from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os
from dotenv import load_dotenv
import bcrypt
import uuid
import random
import string

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility: password hashing & verification
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# Utility: generate random passcode
def generate_passcode(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# -------------------------------
# Pydantic models
class UserSignup(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class TaskCreate(BaseModel):
    workspace_code: str
    task_name: str
    assigned_by: int
    assigned_to: int
    due_date: datetime

# -------------------------------
# USER SIGNUP
@app.post("/signup")
def signup(user: UserSignup):
    cursor = conn.cursor()
    hashed_password = hash_password(user.password)
    workspace_code = str(uuid.uuid4())
    passcode = generate_passcode()
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, workspace_code, passcode, role)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
        """, (user.username, hashed_password, user.email, workspace_code, passcode, "member"))
        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return {"user_id": user_id, "workspace_code": workspace_code, "passcode": passcode}
    except psycopg2.Error as e:
        cursor.close()
        raise HTTPException(status_code=400, detail=str(e))

# -------------------------------
# USER LOGIN
@app.post("/login")
def login(user: UserLogin):
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, workspace_code FROM users WHERE username=%s", (user.username,))
    row = cursor.fetchone()
    cursor.close()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    user_id, password_hash, workspace_code = row
    if not verify_password(user.password, password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    return {"user_id": user_id, "workspace_code": workspace_code}

# -------------------------------
# TASKS
@app.post("/tasks/create")
def create_task(task: TaskCreate):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO tasks (workspace_code, task_name, assigned_by, assigned_to, due_date)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (task.workspace_code, task.task_name, task.assigned_by, task.assigned_to, task.due_date))
        task_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return {"task_id": task_id, "message": "Task created successfully"}
    except psycopg2.Error as e:
        cursor.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/tasks/{workspace_code}")
def get_tasks(workspace_code: str):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.task_name, t.assigned_by, t.assigned_to, t.due_date, t.completed,
               u1.username AS assigned_by_name, u2.username AS assigned_to_name
        FROM tasks t
        LEFT JOIN users u1 ON t.assigned_by = u1.id
        LEFT JOIN users u2 ON t.assigned_to = u2.id
        WHERE t.workspace_code=%s
        ORDER BY t.due_date ASC
    """, (workspace_code,))
    rows = cursor.fetchall()
    cursor.close()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "task_name": row[1],
            "assigned_by": {"id": row[2], "username": row[6]},
            "assigned_to": {"id": row[3], "username": row[7]},
            "due_date": row[4].isoformat(),
            "completed": row[5]
        })
    return tasks

@app.put("/tasks/complete/{task_id}")
def complete_task(task_id: int):
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET completed=TRUE, updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING id;", (task_id,))
    updated = cursor.fetchone()
    if updated is None:
        cursor.close()
        raise HTTPException(status_code=404, detail="Task not found")
    conn.commit()
    cursor.close()
    return {"message": "Task marked complete"}

# -------------------------------
# HEALTH CHECK
@app.get("/health")
def health_check():
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return {"status": "ok", "message": "API and Database are healthy"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
