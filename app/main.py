import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import client_mongo
from app.exceptions import AppError
from app.integrations.registry import close_integrations, init_integrations
from app.logger import logger
from app.users.router import router as router_users
from app.materials.router import router as router_materials
from app.companies.router import router as router_companies
from app.deals.router import router as router_deals
from app.services.router import router as router_services
from app.stages.router import router as router_stages
from app.vehicles.router import router as router_vehicles
from app.adresses.router import router as router_adresses


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_integrations()
    yield
    await close_integrations()
    client_mongo.close()


app = FastAPI(
    title="grand_nerud",
    version="0.1.0",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.CORS_ORIGINS.strip() != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(router_users)
app.include_router(router_materials)
app.include_router(router_companies)
app.include_router(router_deals)
app.include_router(router_services)
app.include_router(router_stages)
app.include_router(router_vehicles)
app.include_router(router_adresses)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info("Request handling time", extra={"process_time": round(process_time, 4)})
    return response


@app.get("/")
def read_root():
    return {"success": True, "message": "Welcome to grand_nerud API"}


@app.get("/health")
async def health():
    try:
        await client_mongo.admin.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    status_code = 200 if mongo_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if mongo_ok else "degraded", "mongo": mongo_ok},
    )
