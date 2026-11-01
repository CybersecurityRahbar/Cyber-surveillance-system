import uvicorn

from traffic_surveillance.core.config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "traffic_surveillance.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    run()
