"""
WebSocket-клиент для /ws_connect.
Фоновый поток: отправка позиции ~60/с, приём GameState и Message.
"""
from __future__ import annotations

import asyncio
import json
import threading
import math
from dataclasses import dataclass

import websockets
from websockets.exceptions import ConnectionClosed

DEFAULT_WS_URL = "wss://practice2026-qw8b.onrender.com/ws_connect"
SEND_INTERVAL = 1.0 / 120.0


@dataclass
class ClientGameState:
    player1: tuple[float, float]
    player2: tuple[float, float]
    puck: tuple[float, float]
    score: tuple[int, int]
    puck_speed: float = 0.0
    puck_vector: tuple[float, float] = (0.0, 0.0)
    player1_speed: float = 0.0
    player1_vector: tuple[float, float] = (0.0, 0.0)
    player2_speed: float = 0.0
    player2_vector: tuple[float, float] = (0.0, 0.0)


def _parse_position(obj: dict) -> tuple[float, float]:
    pos = obj.get("position", {})
    return float(pos.get("first", 0)), float(pos.get("second", 0))


def _parse_vector(obj: dict) -> tuple[float, float]:
    sv = obj.get("speed_vector", {})
    return float(sv.get("first", 0) or 0), float(sv.get("second", 0) or 0)


def _parse_game_state(data: dict) -> ClientGameState:
    puck = data.get("puck", {})
    player1 = data.get("player1", {})
    player2 = data.get("player2", {})
    return ClientGameState(
        player1=_parse_position(player1),
        player2=_parse_position(player2),
        puck=_parse_position(puck),
        score=(int(data["score"]["first"]), int(data["score"]["second"])),
        puck_speed=float(puck.get("speed", 0) or 0),
        puck_vector=_parse_vector(puck),
        player1_speed=float(player1.get("speed", 0) or 0),
        player1_vector=_parse_vector(player1),
        player2_speed=float(player2.get("speed", 0) or 0),
        player2_vector=_parse_vector(player2),
    )


class GameClient:
    def __init__(self, url: str = DEFAULT_WS_URL):
        self.url = url
        self._lock = threading.Lock()
        self._position = (0.0, -250.0)
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None  # Ссылка на активный веб-сокет для принудительного закрытия

        self.connected = False
        self.latest_state: ClientGameState | None = None
        self.last_score: tuple[int, int] | None = None
        self.status = "Подключение..."
        self.ping = 0.0
        self._pending_messages: list[str] = []
        self._state_queue: list[ClientGameState] = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, name="ws-client", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        loop = self._loop
        ws = self._ws
        
        # Принудительно закрываем веб-сокет из главного потока
        if loop is not None and loop.is_running():
            if ws is not None:
                try:
                    asyncio.run_coroutine_threadsafe(ws.close(), loop)
                except Exception:
                    pass
            else:
                loop.call_soon_threadsafe(lambda: None)
                
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
            
        with self._lock:
            self.connected = False
            self.latest_state = None
            self.last_score = None
            self._state_queue.clear()
            self.status = "Отключено"

    def set_position(self, x: float, y: float) -> None:
        with self._lock:
            self._position = (x, y)

    def pop_messages(self) -> list[str]:
        with self._lock:
            msgs = self._pending_messages[:]
            self._pending_messages.clear()
            return msgs

    def snapshot(self) -> tuple[
        bool,
        ClientGameState | None,
        str,
        list[str],
        list[ClientGameState],
        tuple[int, int] | None,
        float,
    ]:
        with self._lock:
            live = self.latest_state
            if live is not None:
                live = ClientGameState(
                    live.player1,
                    live.player2,
                    live.puck,
                    live.score,
                    live.puck_speed,
                    live.puck_vector,
                    live.player1_speed,
                    live.player1_vector,
                    live.player2_speed,
                    live.player2_vector,
                )
            states = self._state_queue[:]
            self._state_queue.clear()
            msgs = self._pending_messages[:]
            self._pending_messages.clear()
            return self.connected, live, self.status, msgs, states, self.last_score, self.ping

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
                async with websockets.connect(
                    self.url,
                    ping_interval=1.0,
                    open_timeout=5,
                    close_timeout=2,
                ) as ws:
                    self._ws = ws  # Сохраняем ссылку на сокет
                    with self._lock:
                        self.connected = True
                        self.latest_state = None
                        self.last_score = None
                        self.ping = 0.0
                        self._state_queue.clear()
                        self.status = "Ждём второго игрока..."
                    send_task = asyncio.create_task(self._send_loop(ws))
                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            
                            if hasattr(ws, 'latency') and not math.isnan(ws.latency):
                                with self._lock:
                                    self.ping = ws.latency * 1000
                                    
                            self._handle_message(json.loads(raw))
                    finally:
                        self._ws = None  # Очищаем ссылку при выходе
                        send_task.cancel()
                        try:
                            await send_task
                        except asyncio.CancelledError:
                            pass
            except asyncio.CancelledError:
                break
            except ConnectionClosed:
                with self._lock:
                    self.connected = False
                    self.latest_state = None
                    self._pending_messages.append("disconnect")
                    self.status = "Соединение разорвано"
            except OSError:
                with self._lock:
                    self.connected = False
                    self.latest_state = None
                    self.last_score = None
                    self._state_queue.clear()
                    self._pending_messages.append("disconnect")
                    self.status = "Сервер не отвечает"
            except Exception as exc:
                with self._lock:
                    self.connected = False
                    self.latest_state = None
                    self.last_score = None
                    self._state_queue.clear()
                    self._pending_messages.append("disconnect")
                    self.status = "Сервер не отвечает"
            else:
                continue
            
            if self._running:
                await asyncio.sleep(2.0)

    async def _send_loop(self, ws) -> None:
        try:
            while self._running:
                with self._lock:
                    x, y = self._position
                await ws.send(json.dumps({"position": {"x": x, "y": y}}))
                await asyncio.sleep(SEND_INTERVAL)
        except (ConnectionClosed, asyncio.CancelledError):
            pass

    def _handle_message(self, packet: dict) -> None:
        msg_type = packet.get("type")
        data = packet.get("data")
        with self._lock:
            if msg_type == "GameState" and isinstance(data, dict):
                parsed = _parse_game_state(data)
                self.latest_state = parsed
                self.last_score = parsed.score
                self._state_queue.append(parsed)
                self.status = "Игра идёт"
            elif msg_type == "Message":
                text = str(data)
                self._pending_messages.append(text)
                lower = text.lower()
                if "disconnect" in lower:
                    self.latest_state = None
                if "max_score" in lower or "game stops" in lower:
                    self.status = text
            elif msg_type == "Error":
                self._pending_messages.append(f"Ошибка: {data}")