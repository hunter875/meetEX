"""Foreground owner process; the CLI uses verified HTTP shutdown, never PID kill."""

import asyncio
import socket
import os

import uvicorn

from .main import create_app


async def run():
    # Reserve the actual port before touching credentials or persistent state.
    listener = socket.socket()
    try:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 8765))
        listener.listen(128)
        application = create_app()
        server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=8765,
                workers=1,
                access_log=False,
                timeout_graceful_shutdown=30,
            )
        )

        async def requested_shutdown():
            while not application.state.ready:
                await asyncio.sleep(0.05)
            await application.state.shutdown_requested.wait()
            server.should_exit = True

        monitor = asyncio.create_task(requested_shutdown())
        try:
            await server.serve(sockets=[listener])
            if not server.started:
                raise RuntimeError("START_FAILED: backend never became ready; see startup error.")
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
    finally:
        listener.close()


if __name__ == "__main__":
    asyncio.run(run())
