from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import uuid
import bcrypt

# Load environment variables
load_dotenv()

app = FastAPI()

# CORS middleware for Flutter/frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)

# -------------------------------
# Pydantic Models
class SignupModel(BaseModel):
    username: str
    email: str
    password: str
    workspace_code: str = None  # Optional, for joining existing workspace
    role: str = "member"        # Default role

class LoginModel(BaseModel):
    username: str
    password: str

class TaskModel(BaseModel):
    workspace_code: str
    task_name: str
    assigned_by: int
    assigned_to: int
    due_date: datetime

# -------------------------------
# Signup Endpoint
@app.post("/signup")
def signup(user: SignupModel):
    cursor = conn.cursor()
    
    # Check if username/email exists
    cursor.execute("SELECT id FROM users WHERE username=%s OR email=%s", (user.username, user.email))
    if cursor.fetchone():
        cursor.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")
    
    # Hash password
    hashed_pw = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    # Generate workspace_code if not provided
    if not user.workspace_code:
        user.workspace_code = str(uuid.uuid4())
    
    # Generate random passcode
    passcode = ''.join(uuid.uuid4().hex[:6].upper())
    
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, email, workspace_code, passcode, role)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (user.username, hashed_pw, user.email, user.workspace_code, passcode, user.role)
    )
    user_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    
    return {"message": "User created successfully", "user_id": user_id, "workspace_code": user.workspace_code, "passcode": passcode}

# -------------------------------
# Login Endpoint
@app.post("/login")
def login(credentials: LoginModel):
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, workspace_code, role, passcode FROM users WHERE username=%s", (credentials.username,))
    row = cursor.fetchone()
    cursor.close()
    
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    
    user_id, password_hash, workspace_code, role, passcode = row
    
    # Verify password
    if not bcrypt.checkpw(credentials.password.encode("utf-8"), password_hash.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    return {"user_id": user_id, "workspace_code": workspace_code, "role": role, "passcode": passcode}

# -------------------------------
# Add Task
@app.post("/add_task")
def add_task(task: TaskModel):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (workspace_code, task_name, assigned_by, assigned_to, due_date)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (task.workspace_code, task.task_name, task.assigned_by, task.assigned_to, task.due_date)
    )
    conn.commit()
    cursor.close()
    return {"message": "Task added successfully"}

# -------------------------------
# Get Tasks for a Workspace
@app.get("/get_tasks/{workspace_code}")
def get_tasks(workspace_code: str):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT t.id, t.workspace_code, t.task_name, t.assigned_by, t.assigned_to, t.due_date, t.completed, u1.username AS assigned_by_name, u2.username AS assigned_to_name "
        "FROM tasks t "
        "LEFT JOIN users u1 ON t.assigned_by = u1.id "
        "LEFT JOIN users u2 ON t.assigned_to = u2.id "
        "WHERE t.workspace_code=%s "
        "ORDER BY t.due_date ASC",
        (workspace_code,)
    )
    rows = cursor.fetchall()
    cursor.close()
    
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "workspace_code": row[1],
            "task_name": row[2],
            "assigned_by": {"id": row[3], "username": row[7]},
            "assigned_to": {"id": row[4], "username": row[8]},
            "due_date": row[5].isoformat(),
            "completed": row[6]
        })
    return tasks

# -------------------------------
# Mark Task Complete
@app.put("/complete_task/{task_id}")
def complete_task(task_id: int):
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET completed=TRUE, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (task_id,)
    )
    conn.commit()
    cursor.close()
    return {"message": "Task marked complete"}

# -------------------------------
# Health Check
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
