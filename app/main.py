from fastapi import FastAPI

from app.api.routes import router
from app.core.database import Base, engine


def create_app() -> FastAPI:
    app = FastAPI(
        title="Personal Assistant Backend",
        version="0.1.0",
        summary="Assistente operacional via WhatsApp para personal trainer.",
    )
    Base.metadata.create_all(bind=engine)
    app.include_router(router)
    return app


app = create_app()
