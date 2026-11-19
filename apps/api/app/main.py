from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import admin, auth, chat, documents, geo, health, library, search

settings = get_settings()

app = FastAPI(
    title="Портал ЖКХ 24 API",
    version="0.1.0",
    description="AI-юрист по жилищному законодательству Республики Казахстан",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(library.router, prefix="/v1")
app.include_router(search.router, prefix="/v1")
app.include_router(chat.router, prefix="/v1")
app.include_router(documents.router, prefix="/v1")
app.include_router(geo.router, prefix="/v1")
app.include_router(auth.router, prefix="/v1")
app.include_router(admin.router, prefix="/v1")
