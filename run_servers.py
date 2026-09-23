"""Menjalankan gRPC server dan REST API server bersamaan."""
import logging
import sys
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ayesh.servers")


def run_grpc():
    """Jalankan gRPC server di thread."""
    import asyncio

    from src.grpc_server import serve
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(serve())


def run_rest():
    """Jalankan REST API server."""
    import uvicorn

    from api_server import app

    logger.info("REST API server running on :8080")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")


def main():
    """Jalankan kedua server bersamaan."""
    logger.info("Starting Ayesh servers...")

    # Jalankan gRPC di thread terpisah
    grpc_thread = threading.Thread(target=run_grpc, daemon=True)
    grpc_thread.start()
    logger.info("gRPC server thread started")

    # Jalankan REST di main thread
    run_rest()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
