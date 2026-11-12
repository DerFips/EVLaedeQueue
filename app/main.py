import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from pathlib import Path

from app.config import settings
from app.db.session import Base, engine, SessionLocal
from app.models import models  # noqa: F401
from app.models.models import User, UserRole
from app.security import hash_password
from app.rate_limit import limiter
from app.routers import auth as auth_router
from app.routers import admin as admin_router
from app.routers import charging as charging_router
from app.routers import queue as queue_router
from app.routers import checkout as checkout_router
from app.routers import mobile as mobile_router
from app.routers import rewards as rewards_router

API_V1_PREFIX = "/api/v1"
logger = logging.getLogger("app")

tags_metadata = [
    {"name": "auth", "description": "Registrierung, Login, Token-Verwaltung."},
    {"name": "admin", "description": "Verwaltung von Standorten und Ladepunkten (nur Admin)."},
    {"name": "charging", "description": "Ladepunkt-Status und Check-in fuer Mitglieder."},
    {"name": "queue", "description": "Warteschlangen-Verwaltung inkl. Parkplatz-Tauschangebot."},
    {"name": "checkout", "description": "Abstoepsel-Workflow mit Benachrichtigung/Ueberspringen."},
    {"name": "mobile", "description": "Schnittstellen speziell fuer die mobile App (Geraete-Registrierung, Dashboard)."},
    {"name": "rewards", "description": "Belohnungspunkte, Leaderboard-Opt-In und Profilbild-Upload."},
]


def bootstrap_admin():
    if not settings.admin_bootstrap_email or not settings.admin_bootstrap_password:
        return
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.admin_bootstrap_email.lower()).first()
        if existing:
            return
        admin = User(
            email=settings.admin_bootstrap_email.lower(),
            hashed_password=hash_password(settings.admin_bootstrap_password),
            full_name="System Admin",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()


def ensure_indexes():
    """create_all legt Indizes nur zusammen mit NEUEN Tabellen an. Fuer bestehende
    Datenbanken werden nachtraeglich hinzugekommene Indizes hier ergaenzt."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            try:
                index.create(bind=engine, checkfirst=True)
            except Exception as exc:  # noqa: BLE001 - z. B. Unique-Index trifft auf Altdaten
                logger.warning("Index %s konnte nicht angelegt werden: %s", index.name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_indexes()
    bootstrap_admin()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="REST-API fuer die EVLädeQueue, nutzbar von Web- und Mobile-Clients.",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.add_middleware(GZipMiddleware, minimum_size=1024)

DOCS_PATHS = (f"{API_V1_PREFIX}/docs", f"{API_V1_PREFIX}/redoc")
# Datei-Uploads duerfen groesser sein als JSON-Anfragen (Bild + Multipart-Rahmen).
UPLOAD_BODY_LIMIT = settings.avatar_max_upload_bytes + 64 * 1024


@app.middleware("http")
async def limit_request_body(request, call_next):
    """Weist uebergrosse Anfragen anhand von Content-Length ab, bevor der Body gelesen
    (und bei Multipart auf die Platte gespoolt) wird."""
    if request.method in ("POST", "PUT", "PATCH"):
        is_upload = request.headers.get("content-type", "").startswith("multipart/form-data")
        limit = UPLOAD_BODY_LIMIT if is_upload else settings.max_request_body_bytes
        declared = request.headers.get("content-length")
        if declared is None:
            if request.headers.get("transfer-encoding"):
                return JSONResponse({"detail": "Content-Length erforderlich"}, status_code=411)
        elif not declared.isdigit() or int(declared) > limit:
            return JSONResponse({"detail": "Anfrage ist zu gross"}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Setzt gaengige Sicherheits-Header (Security-Hardening, AP7).
    Hinweis: Der 'Server: uvicorn'-Header wird von Uvicorn selbst NACH der
    Middleware gesetzt und kann hier nicht entfernt werden. Stattdessen muss
    der Server mit --no-server-header gestartet werden (siehe Dockerfile/README)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Swagger UI/ReDoc laden ihre Skripte von einem CDN und wuerden von der strikten
    # CSP blockiert; sie verarbeiten keine Nutzerdaten der App.
    if request.url.path not in DOCS_PATHS:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(charging_router.router)
app.include_router(queue_router.router)
app.include_router(checkout_router.router)
app.include_router(mobile_router.router)
app.include_router(rewards_router.router)


@app.get(f"{API_V1_PREFIX}/health", tags=["health"])
def health_check():
    return {"status": "ok", "app": settings.app_name, "version": app.version}


STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
@app.get("/reset-password", include_in_schema=False)
def serve_frontend():
    # no-cache: index.html verweist auf unversionierte JS/CSS-Dateien.
    return FileResponse(str(TEMPLATES_DIR / "index.html"), headers={"Cache-Control": "no-cache"})
