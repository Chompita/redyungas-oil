"""
mcp/server.py — Servidor MCP de control (FASE 7).

Expone REDYUNGAS OIL como servidor **Model Context Protocol** (transporte HTTP
streamable, endpoint `/mcp`) para que agentes de IA (Antigravity/Gemini/qwen/Claude)
controlen el playout. Sería el PRIMER servidor MCP del ecosistema JARVIS.

THREAD-SAFETY: el servidor corre en un hilo aparte (uvicorn). Las tools NO tocan el
motor directamente: encolan la operación en `MainThreadBridge`, que la ejecuta en el
hilo de Qt y devuelve el resultado. Seguridad: token Bearer + bind a Tailscale.

También sirve un REST mínimo en el mismo puerto: `GET /health` y `POST /mention`
(para que n8n/Telegram inyecten menciones sin hablar MCP).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future

import anyio
from PyQt6.QtCore import QObject, QTimer

from ..core.constants import APP_NAME, APP_VERSION
from .security import TokenAuthMiddleware

log = logging.getLogger("redyungas_oil.mcp")


class MainThreadBridge(QObject):
    """Ejecuta funciones en el hilo de Qt a petición de otros hilos (MCP)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        import queue
        self._queue = queue.Queue()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(30)

    def call(self, func, *args, timeout: float = 5.0, **kwargs):
        fut: Future = Future()
        self._queue.put((func, args, kwargs, fut))
        return fut.result(timeout=timeout)

    def _drain(self) -> None:
        while not self._queue.empty():
            func, args, kwargs, fut = self._queue.get_nowait()
            try:
                fut.set_result(func(*args, **kwargs))
            except Exception as exc:  # propaga al hilo que llamó
                fut.set_exception(exc)


class MCPServer:
    def __init__(self, config: dict, control, bridge: MainThreadBridge) -> None:
        mcpcfg = (config.get("mcp", {}) or {})
        self.host = mcpcfg.get("host", "127.0.0.1")
        self.port = int(mcpcfg.get("port", 8770))
        self.token = mcpcfg.get("token", "") or ""
        self.control = control
        self.bridge = bridge
        self._server = None
        self._thread: threading.Thread | None = None

    # --------------------------------------------------------------- build
    def _build_app(self):
        from mcp.server.fastmcp import FastMCP

        server = FastMCP(APP_NAME, host=self.host, port=self.port,
                         stateless_http=True, json_response=True)
        ctl = self.control

        async def run(fn, *args):
            return await anyio.to_thread.run_sync(lambda: self.bridge.call(fn, *args))

        # --- tools de control ---
        @server.tool()
        async def play() -> str:
            """Reproduce / reanuda la emisión."""
            return await run(ctl.play)

        @server.tool()
        async def stop() -> str:
            """Detiene la emisión."""
            return await run(ctl.stop)

        @server.tool()
        async def pause() -> str:
            """Pausa o reanuda."""
            return await run(ctl.pause)

        @server.tool()
        async def next_track() -> str:
            """Salta a la pista siguiente."""
            return await run(ctl.next)

        @server.tool()
        async def play_index(index: int) -> str:
            """Reproduce la pista en la posición dada (0-based)."""
            return await run(ctl.play_index, index)

        @server.tool()
        async def add_track(path: str) -> str:
            """Añade una pista de audio a la lista."""
            return await run(ctl.add_track, path)

        @server.tool()
        async def load_list(path: str) -> str:
            """Carga una lista .lst (reemplaza la actual)."""
            return await run(ctl.load_list, path)

        @server.tool()
        async def add_cue(slot: int, path: str) -> str:
            """Asigna una cuña a un slot del cartwall (0-8)."""
            return await run(ctl.add_cue, slot, path)

        @server.tool()
        async def fire_cart(slot: int) -> str:
            """Dispara la cuña de un slot del cartwall (0-8)."""
            return await run(ctl.fire_cart, slot)

        @server.tool()
        async def set_mention(text: str, when: str) -> str:
            """Programa una mención que brillará a la hora dada (HH:MM o HH:MM:SS)."""
            return await run(ctl.set_mention, text, when)

        @server.tool()
        async def start_recording() -> str:
            """Inicia la grabación de la transmisión."""
            return await run(ctl.start_recording)

        @server.tool()
        async def stop_recording() -> str:
            """Detiene la grabación."""
            return await run(ctl.stop_recording)

        @server.tool()
        async def get_status() -> dict:
            """Estado actual: índice sonando, siguiente, conteo, grabando, duración total."""
            return await run(ctl.get_status)

        @server.tool()
        async def get_now_playing() -> dict:
            """Pista que suena ahora."""
            return await run(ctl.get_now_playing)

        @server.tool()
        async def get_playlist() -> list:
            """Lista completa (índice, título, tipo, duración)."""
            return await run(ctl.get_playlist)

        # --- REST mínimo en el mismo puerto ---
        from starlette.responses import JSONResponse

        @server.custom_route("/health", methods=["GET"])
        async def health(request):
            return JSONResponse({"app": APP_NAME, "version": APP_VERSION, "ok": True})

        @server.custom_route("/mention", methods=["POST"])
        async def add_mention(request):
            data = await request.json()
            text, when = data.get("text", ""), data.get("when", "")
            if not text or not when:
                return JSONResponse({"error": "se requieren 'text' y 'when'"}, status_code=400)
            await run(ctl.set_mention, text, when)
            return JSONResponse({"ok": True})

        app = server.streamable_http_app()
        app.add_middleware(TokenAuthMiddleware, token=self.token)
        return app

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        import uvicorn

        app = self._build_app()
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

        def _run() -> None:
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(target=_run, daemon=True, name="mcp-server")
        self._thread.start()
        log.info("Servidor MCP en http://%s:%s/mcp (token=%s)",
                 self.host, self.port, "sí" if self.token else "NO")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
