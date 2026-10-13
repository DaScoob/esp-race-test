from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routes import admin, device

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="ESP Race API",
        version="1.0.0",
        description="Backend for the ESP Race test environment (ESP32 heartbeats, events, pairing commands).",
        lifespan=lifespan,
    )

    if settings.frontend_origin:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.frontend_origin],
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["X-Admin-Key", "X-Device-Key", "Content-Type"],
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "validation_error",
                    "message": "Request payload failed schema validation.",
                    "errors": [
                        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
                        for error in exc.errors()
                    ],
                }
            },
        )

    application.include_router(device.router, prefix=API_V1_PREFIX, tags=["device"])
    application.include_router(admin.router, prefix=API_V1_PREFIX, tags=["admin"])

    @application.get("/api/v1/health", include_in_schema=False)
    def health() -> JSONResponse:
        return JSONResponse(status_code=200, content={"status": "ok"})

    @application.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return JSONResponse(status_code=200, content={"service": "ESP Race API", "docs": "/docs", "ui": "/ui/"})

    if settings.ui_dir:
        application.mount("/ui", StaticFiles(directory=settings.ui_dir, html=True), name="ui")

    if settings.downloads_dir:
        application.mount("/downloads", StaticFiles(directory=settings.downloads_dir, html=True), name="downloads")

    return application


app = create_app()