"""
mcp/security.py — Seguridad del control remoto (FASE 7).

El control por IA viaja por internet/Tailscale, así que el puerto MCP/REST se
protege como las allowlists de JARVIS:
    - bind preferente a la interfaz Tailscale (100.x), no a 0.0.0.0 crudo
    - token Bearer obligatorio en cada petición (excepto /health)

NUNCA exponer el control sin token a internet abierto.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


def verify_token(provided: str, expected: str) -> bool:
    """Comparación en tiempo constante."""
    if not expected:
        return True
    return hmac.compare_digest(provided or "", expected)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Exige 'Authorization: Bearer <token>' salvo en /health (si hay token)."""

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self.token = token or ""

    async def dispatch(self, request, call_next):
        if self.token and not request.url.path.rstrip("/").endswith("health"):
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or not verify_token(auth[7:], self.token):
                return JSONResponse({"error": "no autorizado"}, status_code=401)
        return await call_next(request)
