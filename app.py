from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Load .env variables
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

# Task Pydantic model
class Task(BaseModel):
    family_code: str
    task_name: str
    assigned_by: str
    assigned_to: str
    due_date: datetime

# Add new task
@app.post("/add_task")
def add_task(task: Task):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (family_code, task_name, assigned_by, assigned_to, due_date)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (task.family_code, task.task_name, task.assigned_by, task.assigned_to, task.due_date)
    )
    conn.commit()
    cursor.close()
    return {"message": "Task added successfully"}

# Get tasks for a family
@app.get("/get_tasks/{family_code}")
def get_tasks(family_code: str):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE family_code=%s ORDER BY due_date ASC", (family_code,))
    rows = cursor.fetchall()
    cursor.close()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "family_code": row[1],
            "task_name": row[2],
            "assigned_by": row[3],
            "assigned_to": row[4],
            "due_date": row[5].isoformat(),
            "completed": row[6]
        })
    return tasks

# Mark task complete
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

# Health check endpoint
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
