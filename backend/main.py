"""
HPC Automation API (FastAPI).

Run from the project root:   python -m uvicorn backend.main:app --reload
API docs:                    http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import SessionLocal, init_db
from backend.models.entities import encrypt_stored_passwords
from backend.routers.activities_grid import router as activities_grid_router
from backend.routers.activity_library import router as activity_library_router
from backend.routers.auth import router as auth_router
from backend.routers.class_template import router as class_template_router
from backend.routers.hpc_cards import router as hpc_cards_router
from backend.routers.schools import router as schools_router
from backend.routers.teachers import router as teachers_router
from backend.services.activity_library import recover_interrupted_syncs
from backend.services.upload_jobs import recover_interrupted_jobs

init_db()
with SessionLocal() as _db:
    if encrypt_stored_passwords(_db):
        print("[startup] Encrypted stored passwords that were plain text.")


@asynccontextmanager
async def lifespan(app):
    count = recover_interrupted_jobs()
    if count:
        print(f"[startup] {count} upload(s) were interrupted by a restart and marked FAILED.")
    if recover_interrupted_syncs():
        print("[startup] An activity sync was interrupted by a restart and marked FAILED.")
    from backend.services.activity_library import start_auto_sync_timer
    start_auto_sync_timer()                      # daily update of the activities with the school admin's session
    yield


app = FastAPI(title="HPC Automation API", version="3.0.0", lifespan=lifespan,
              description="Schools, teachers and syncing class workbooks to the PARAKH HPC portal.")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",   # the Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth_router, schools_router, teachers_router, hpc_cards_router, activity_library_router,
               activities_grid_router, class_template_router):
    app.include_router(router, prefix="/api/v1")


@app.get("/")
def root():
    return {"status": "online", "service": "HPC Automation API", "docs": "/docs"}
