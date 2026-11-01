"""
HPC Automation API (FastAPI).

Run from the project root:   python -m uvicorn backend.main:app --reload
API docs:                    http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import config

from backend.database import SessionLocal, init_db
from backend.models.entities import encrypt_stored_passwords
from backend.routers.activities_grid import router as activities_grid_router
from backend.routers.activity_library import router as activity_library_router
from backend.routers.auth import router as auth_router
from backend.routers.class_template import router as class_template_router
from backend.routers.hpc_cards import router as hpc_cards_router
from backend.routers.platform import router as platform_router
from backend.routers.schools import router as schools_router
from backend.routers.teachers import router as teachers_router
from backend.services.activity_library import recover_interrupted_syncs
import backend.services.register_data  # noqa: F401,E402  (the School Register's values reach every card save)
from backend.services.safe_paths import UnsafePath
from backend.services.upload_jobs import recover_interrupted_jobs

init_db()
with SessionLocal() as _db:
    if encrypt_stored_passwords(_db):
        print("[startup] Encrypted stored passwords that were plain text.")


@asynccontextmanager
async def lifespan(app):
    import anyio
    # routes are plain functions run in worker threads, and an upload's sync runs in one for all its minutes: the
    # default 40 threads would let a few long uploads and PARAKH's slow answers hold up every other request
    anyio.to_thread.current_default_thread_limiter().total_tokens = config.WORKER_THREADS
    count = recover_interrupted_jobs()
    if count:
        print(f"[startup] {count} upload(s) were interrupted by a restart and marked FAILED.")
    if recover_interrupted_syncs():
        print("[startup] An activity sync was interrupted by a restart and marked FAILED.")
    from backend.services import audit, hpc_sessions
    pruned = hpc_sessions.prune_uploads()             # uploaded workbooks older than HPC_UPLOAD_KEEP_DAYS (L-12)
    if pruned:
        print(f"[startup] Deleted {pruned} uploaded workbook(s) older than the kept days.")
    scrubbed = audit.scrub_sensitive()                # UDID and guardian names out of older audit rows (M-7)
    if scrubbed:
        print(f"[startup] Hid UDID / guardian name values in {scrubbed} older audit row(s).")
    from backend.services.activity_library import start_auto_sync_timer
    start_auto_sync_timer()                      # daily update of the activities with the school's session
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

# Every answer tells the browser: no guessing file types, not inside another site's frame (clickjacking), no address
# sent to other sites; the app's pages may load only its own scripts and styles (images also as data: - the captcha).
_PAGE_POLICY = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "connect-src 'self'; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; "
                "frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if not request.url.path.startswith(("/api/", "/docs", "/redoc", "/openapi.json")):   # the API docs load their own scripts
        response.headers.setdefault("Content-Security-Policy", _PAGE_POLICY)
    return response


@app.exception_handler(UnsafePath)
async def unsafe_path(request: Request, exc: UnsafePath):
    """An id, stage or file name that would reach outside its folder (C-1, C-2)."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


from backend.routers.register_reports import school_router as register_reports_router  # noqa: E402
from backend.routers.register_reports import teacher_router as register_teacher_reports_router  # noqa: E402

for router in (auth_router, schools_router, teachers_router, hpc_cards_router, activity_library_router,
               activities_grid_router, class_template_router, platform_router, register_reports_router,
               register_teacher_reports_router):
    app.include_router(router, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "online", "service": "HPC Automation API", "docs": "/docs"}


# The built web app (frontend/dist, made by `npm run build`) is served from here too, so one server - without
# the Vite dev server - runs everything. Without a build, "/" just says the API is online.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str):
        """Files of the build (favicon ...) by name; every other path is a page of the app (index.html)."""
        if path.startswith(("api/", "docs", "openapi.json", "redoc")):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file = (_DIST / path).resolve()
        if path and file.is_file() and _DIST in file.parents:
            return FileResponse(file)
        return FileResponse(_DIST / "index.html", headers={"Cache-Control": "no-cache"})
else:
    @app.get("/")
    def root():
        return health()
