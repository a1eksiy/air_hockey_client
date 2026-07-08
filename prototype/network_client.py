"""
WebSocket-клиент для /ws_connect.
Фоновый поток: отправка позиции ~60/с, приём GameState и Message.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass

import websockets

DEFAULT_WS_URL = "ws://127.0.0.1:8000/ws_connect"
SEND_INTERVAL = 1.0 / 60.0


@dataclass
class ClientGameState:
    player1: tuple[float, float]
    player2: tuple[float, float]
    puck: tuple[float, float]
    score: tuple[int, int]


def _parse_position(obj: dict) -> tuple[float, float]:
    pos = obj.get("position", {})
    return float(pos.get("first", 0)), float(pos.get("second", 0))


def _parse_game_state(data: dict) -> ClientGameState:
    return ClientGameState(
        player1=_parse_position(data["player1"]),
        player2=_parse_position(data["player2"]),
        puck=_parse_position(data["puck"]),
        score=(int(data["score"]["first"]), int(data["score"]["second"])),
    )


class GameClient:
    def __init__(self, url: str = DEFAULT_WS_URL):
        self.url = url
        self._lock = threading.Lock()
        self._position = (0.0, -250.0)
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self.connected = False
        self.latest_state: ClientGameState | None = None
        self.status = "Подключение..."
        self._pending_messages: list[str] = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, name="ws-client", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: None)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self.connected = False
            self.latest_state = None
            self.status = "Отключено"

    def set_position(self, x: float, y: float) -> None:
        with self._lock:
            self._position = (x, y)

    def pop_messages(self) -> list[str]:
        with self._lock:
            msgs = self._pending_messages[:]
            self._pending_messages.clear()
            return msgs

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        finally:
            self._loop.close()
            self._loop = None

    async def _run(self) -> None:
        while self._running:
            try:
                async with websockets.connect(self.url, open_timeout=3) as ws:
                    with self._lock:
                        self.connected = True
                        self.status = "Ждём второго игрока..."
                    send_task = asyncio.create_task(self._send_loop(ws))
                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            self._handle_message(json.loads(raw))
                    finally:
                        send_task.cancel()
                        try:
                            await send_task
                        except asyncio.CancelledError:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                with self._lock:
                    self.connected = False
                    self.latest_state = None
                    self.status = f"Нет связи с сервером ({exc.__class__.__name__})"
                if self._running:
                    await asyncio.sleep(2.0)

    async def _send_loop(self, ws) -> None:
        while self._running:
            with self._lock:
                x, y = self._position
            await ws.send(json.dumps({"position": {"x": x, "y": y}}))
            await asyncio.sleep(SEND_INTERVAL)

    def _handle_message(self, packet: dict) -> None:
        msg_type = packet.get("type")
        data = packet.get("data")
        with self._lock:
            if msg_type == "GameState" and isinstance(data, dict):
                self.latest_state = _parse_game_state(data)
                self.status = "Игра идёт"
            elif msg_type == "Message":
                text = str(data)
                self._pending_messages.append(text)
                if "disconnect" in text.lower() or "max_score" in text.lower():
                    self.latest_state = None
                    self.status = text
            elif msg_type == "Error":
                self._pending_messages.append(f"Ошибка: {data}")
