"""
integrations/telegram_notifier.py — Avisos salientes por Telegram (FASE 4).

Envía mensajes al operador vía la Bot API (HTTPS con httpx). NO corre un bot: solo
salida. Es FIRE-AND-FORGET y no bloquea el hilo de la UI (usa QThreadPool). Si
Telegram falla o está desactivado, degrada elegantemente a log local: la emisión
nunca se rompe por un aviso.

Avisos típicos del protocolo offline (Fase 4):
    "⚠️ Compu <emisora> está sin recibir señal. Reintentando reconexión (15 s)…"
    "🔴 <emisora>: sin señal. Protocolo offline activado: publicidad al aire."
    "🟢 <emisora>: señal recuperada. Volviendo al estudio."
"""

from __future__ import annotations

import logging

import httpx
from PyQt6.QtCore import QRunnable, QThreadPool

log = logging.getLogger("redyungas_oil.telegram")


class _SendTask(QRunnable):
    def __init__(self, token: str, chat_id: str, text: str) -> None:
        super().__init__()
        self.token = token
        self.chat_id = chat_id
        self.text = text
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": self.text},
                timeout=8.0,
            )
            if resp.status_code != 200:
                log.warning("Telegram %s: %s", resp.status_code, resp.text[:160])
        except Exception as exc:  # nunca propagar: la emisión no debe romperse
            log.warning("Telegram no enviado: %s", exc)


class TelegramNotifier:
    def __init__(self, config: dict) -> None:
        tg = (config or {}).get("telegram", {}) or {}
        self.enabled = bool(tg.get("enabled"))
        self.token = tg.get("bot_token", "") or ""
        self.chat_id = str(tg.get("chat_id", "") or "")
        self._pool = QThreadPool.globalInstance()

    def notify(self, text: str) -> bool:
        """Despacha un aviso (no bloqueante). Devuelve True si se intentó enviar."""
        log.info("Aviso: %s", text)
        if not (self.enabled and self.token and self.chat_id):
            return False
        self._pool.start(_SendTask(self.token, self.chat_id, text))
        return True
