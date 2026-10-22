"""
FastAPI Enterprise Application Entrypoint
PARAKH Holistic Progress Card (HPC) Multi-Tenant Automation Backend
"""
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database import engine, Base
import backend.models.entities  # Ensure models are loaded before create_all

# Initialize MySQL Tables automatically
try:
    Base.metadata.create_all(bind=engine)
    print("[DB] Initialized MySQL tables for Schools, Teachers, and Sessions successfully.")
except Exception as e:
    print(f"[DB ERROR] Error initializing database tables: {e}")

from backend.routers.auth import router as auth_router
from backend.routers.schools import router as schools_router
from backend.routers.teachers import router as teachers_router

app = FastAPI(
    title="PARAKH HPC Automation Enterprise API",
    description="Multi-tenant backend for School Registration, Teacher Management, and Automated HPC Submissions.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for Next.js / React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows Next.js (http://localhost:3000) and other frontends
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(schools_router, prefix="/api/v1")
app.include_router(teachers_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "PARAKH HPC Automation Enterprise API",
        "version": "2.0.0",
        "database": "MySQL (XAMPP)",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
