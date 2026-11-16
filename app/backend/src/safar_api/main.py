import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from safar_api.api.routes import router
from safar_api.config import settings
from safar_api.logging_config import configure_logging
from safar_api.tracing import configure_langsmith

configure_logging()
_langsmith_on = configure_langsmith()
logger = logging.getLogger("safar_api")

app = FastAPI(title="Safar AI", version="0.1.0")


@app.on_event("startup")
def _on_startup() -> None:
    logger.info(
        "Safar AI started | supervisor_model=%s langsmith=%s",
        settings.supervisor_model,
        "on" if _langsmith_on else "off",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
