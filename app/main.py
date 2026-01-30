import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import Optional, List

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
    # при запуске
    yield


app = FastAPI(
    title="grand_nerud",
    version="0.1.0",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

app.include_router(router_users)
app.include_router(router_materials)
app.include_router(router_companies)
app.include_router(router_deals)
app.include_router(router_services)
app.include_router(router_stages)
app.include_router(router_vehicles)
app.include_router(router_adresses)

services = [
    {"_id": "1", "name": "продажа сырья"},
    {"_id": "2", "name": "утилизация"},
    {"_id": "3", "name": "доставка"}
]
companies = [
    {"_id": "c1", "name": "ООО Ромашка", "inn": "1234567890"},
    {"_id": "c2", "name": "ООО Лотос", "inn": "9876543210"},
]


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    # При подключении Prometheus + Grafana подобный лог не требуется
    logger.info("Request handling time", extra={
        "process_time": round(process_time, 4)
    })

    response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.get("/")
def read_root():
    return {
        "success": True,
        "message": "Welcome to telegram API"
    }


@app.get("/deals/new", response_class=HTMLResponse)
async def new_deal(request: Request):
    return templates.TemplateResponse("deal_form.html", {
        "request": request,
        "services": services,
        "companies": companies,
    })


@app.post("/deals", response_class=HTMLResponse)
async def save_deal(
        request: Request,
        serviceId: str = Form(...),
        customerId: str = Form(...),
        quantity: float = Form(...),
        amountPerUnit: float = Form(...),
):
    total = quantity * amountPerUnit
    return templates.TemplateResponse("deal_success.html", {
        "request": request,
        "serviceId": serviceId,
        "customerId": customerId,
        "total": total
    })


# пересчёт суммы (htmx)
@app.get("/deals/calc", response_class=HTMLResponse)
async def calc_total(
        quantity: float = Query(0),
        amountPerUnit: float = Query(0)
):
    total = quantity * amountPerUnit
    return f"<span class='font-bold text-blue-600'>{total:.2f} ₽</span>"


# автопоиск компаний (htmx)
@app.get("/companies/search", response_class=HTMLResponse)
async def company_search(q: str = Query("")):
    results = [c for c in companies if q.lower() in c["name"].lower() or q in c["inn"]]
    html = "".join(
        f"<option value='{c['_id']}'>{c['name']} ({c['inn']})</option>"
        for c in results
    )
    return html or "<option disabled>Ничего не найдено</option>"
