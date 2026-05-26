from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from safar_api.api.routes import router
from safar_api.config import settings

from pathlib import Path

_root = Path(__file__).resolve().parents[4]
load_dotenv(_root / ".env")
load_dotenv(_root / "app" / ".env")

app = FastAPI(title="Safar AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
