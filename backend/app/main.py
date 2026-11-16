"""
AquaLens AI - FastAPI Application Entry Point
Objective 3: Water Fingerprinting & Intelligent Quality Monitoring
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .core.config import settings
from .core.security import hash_password
from .core.workspaces import ensure_india_account
from .db.session import engine, Base, get_db
from .db.models import User, WaterSource, MonitoringStation
from .ml.inference import get_inference_engine
from .api import auth, sources, observations, monitoring, advanced
from .api import india, ground, satellite
from .satellite.schema import ensure_satellite_schema
from .satellite.service import recover_interrupted_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    Base.metadata.create_all(bind=engine)
    
    # Pre-load ML classifier
    engine_ml = get_inference_engine()
    if engine_ml.is_loaded:
        print(f"[AquaLens ML] Classifier loaded successfully. Classes: {engine_ml.classes_}")
    else:
        print(f"[AquaLens ML Warning] Classifier could not be loaded: {engine_ml.load_error}")

    # Seed baseline administrator and demo monitoring stations if database is empty
    with Session(engine) as db:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin_user = User(
                username="admin",
                email="admin@aqualens.ai",
                hashed_password=hash_password("AquaLens2026!"),
                role="admin",
                is_active=True,
            )
            db.add(admin_user)
            db.commit()
            print("[AquaLens DB] Seeded initial admin account: admin / AquaLens2026!")

        ensure_india_account(db)

    # Additive, non-destructive creation of the satellite tables only.
    created_tables = ensure_satellite_schema(engine)
    if created_tables:
        print(f"[AquaLens DB] Created satellite tables: {', '.join(created_tables)}")

    # A job row left queued/running belongs to a process that no longer exists (retrieval runs
    # in a daemon thread). Mark it interrupted so the dashboard stops polling and the user can
    # retry the remaining months. Nothing is started or deleted here.
    try:
        with Session(engine) as job_db:
            interrupted = recover_interrupted_jobs(job_db)
        if interrupted:
            print(
                "[AquaLens Satellite] Marked interrupted fetch job(s) from a previous process: "
                + ", ".join(str(job_id) for job_id in interrupted)
            )
    except Exception as error:  # noqa: BLE001 - never block startup on job bookkeeping
        print(f"[AquaLens Satellite Warning] Could not reconcile fetch jobs: {error}")

        # Initial source & monitoring stations if empty
        source_count = db.query(WaterSource).count()
        if source_count == 0:
            source_pacific = WaterSource(
                source_code="DEMO-PAC-01",
                name="Pacific Estuary (Demo Fixture)",
                source_type="Estuary",
                region="Pacific Northwest",
                description="Illustrative demonstration fixture for development and UI evaluation — not an active physical monitoring site.",
                is_demo=True,
            )
            source_lake = WaterSource(
                source_code="DEMO-SIERRA-02",
                name="Alpine Basin (Demo Fixture)",
                source_type="Reservoir",
                region="High Sierra",
                description="Illustrative demonstration fixture for development and UI evaluation — not an active physical monitoring site.",
                is_demo=True,
            )
            db.add(source_pacific)
            db.add(source_lake)
            db.flush()

            st1 = MonitoringStation(
                source_id=source_pacific.id,
                station_code="DEMO-ST-ALPHA",
                name="Demo Station 1 (Estuary Mouth)",
                latitude=46.2044,
                longitude=-124.0583,
                elevation_m=4.2,
                active=True,
                is_demo=True,
            )
            st2 = MonitoringStation(
                source_id=source_pacific.id,
                station_code="DEMO-ST-BETA",
                name="Demo Station 2 (Inner Bay)",
                latitude=46.1822,
                longitude=-123.9890,
                elevation_m=2.1,
                active=True,
                is_demo=True,
            )
            st3 = MonitoringStation(
                source_id=source_lake.id,
                station_code="DEMO-ST-GAMMA",
                name="Demo Station 3 (High Basin)",
                latitude=39.0968,
                longitude=-120.0324,
                elevation_m=1897.0,
                active=True,
                is_demo=True,
            )
            db.add_all([st1, st2, st3])
            db.commit()
            print("[AquaLens DB] Initialized illustrative demonstration fixtures.")
        else:
            # Ensure existing demo stations have is_demo correctly flagged
            for s in db.query(WaterSource).all():
                if "demo" in s.name.lower() or "demo" in s.source_code.lower() or "reserve" in s.name.lower():
                    s.is_demo = True
            for st in db.query(MonitoringStation).all():
                if "demo" in st.name.lower() or "alpha" in st.name.lower() or "beta" in st.name.lower() or "gamma" in st.name.lower():
                    st.is_demo = True
            db.commit()

    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "AquaLens AI: Water Fingerprinting & Intelligent Quality Monitoring API. "
        "Integrates Objective 2 Random Forest visual classification with Objective 3 "
        "source-specific baseline fingerprints, robust anomaly analysis, and Water Health Scores."
    ),
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in settings.CORS_ORIGINS if origin != "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def check_cookie_origin(request, call_next):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.cookies.get(settings.SESSION_COOKIE):
        origin = request.headers.get("origin")
        if origin and origin not in [item for item in settings.CORS_ORIGINS if item != "*"]:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Untrusted request origin."})
    response = await call_next(request)
    if "/auth/" in request.url.path:
        response.headers["Cache-Control"] = "no-store"
    return response


# Mount uploads static directory
app.mount("/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads")

# Mount API Routers under /api/v1
api_v1_prefix = settings.API_V1_STR
app.include_router(auth.router, prefix=api_v1_prefix)
app.include_router(sources.router, prefix=api_v1_prefix)
app.include_router(observations.router, prefix=api_v1_prefix)
app.include_router(monitoring.router, prefix=api_v1_prefix)
app.include_router(advanced.router, prefix=api_v1_prefix)

# Also expose standard top-level routes matching Section 7 specifications directly
app.include_router(auth.router)
app.include_router(sources.router)
app.include_router(observations.router)
app.include_router(monitoring.router)
app.include_router(advanced.router)
app.include_router(india.router)
app.include_router(ground.router)
app.include_router(satellite.router)
app.include_router(satellite.router, prefix=api_v1_prefix)


@app.get("/health", tags=["Operational"])
def health_check(db: Session = Depends(get_db)):
    """System health check verifying database persistence and model availability."""
    ml_engine = get_inference_engine()
    db_connected = False
    try:
        db.execute(Base.metadata.tables["users"].select().limit(1))
        db_connected = True
    except Exception:
        db_connected = False

    return {
        "status": "healthy" if (db_connected and ml_engine.is_loaded) else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database_connected": db_connected,
        "model_loaded": ml_engine.is_loaded,
        "model_version": ml_engine.model.__class__.__name__ if ml_engine.is_loaded else None,
        "classes": ml_engine.classes_,
        "feature_count": 20,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
