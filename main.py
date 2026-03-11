from app.config import settings

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.app:create_app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        factory=True,
    )
