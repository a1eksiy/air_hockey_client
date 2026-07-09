"""Фоновая музыка по тематическому режиму (music/*.mp3)."""
from __future__ import annotations

from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"

MODE_MUSIC_KEYS: dict[str, str] = {
    "Neon Velocity": "neon velocity",
    "Cosmic Rink": "cosmic rink",
    "Sprinkle Slam": "sprinkle slam",
}


def _music_path(mode_name: str) -> Path | None:
    key = MODE_MUSIC_KEYS.get(mode_name, MODE_MUSIC_KEYS["Neon Velocity"])
    for path in MUSIC_DIR.iterdir():
        if key in path.name.lower() and path.suffix.lower() == ".mp3":
            return path
    return None


class GameMusic:
    def __init__(self) -> None:
        self._current_mode: str | None = None

    def play_mode(self, mode_name: str, volume: float) -> None:
        path = _music_path(mode_name)
        if path is None:
            return
        vol = max(0.0, min(1.0, volume))
        if self._current_mode == mode_name and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(vol)
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(vol)
            pygame.mixer.music.play(-1)
            self._current_mode = mode_name
        except pygame.error:
            self._current_mode = None

    def set_volume(self, volume: float) -> None:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))

    def stop(self) -> None:
        try:
            # Проверяем, инициализирован ли микшер перед обращением к нему
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except pygame.error:
            # Игнорируем ошибку, если микшер уже выключен
            pass
        self._current_mode = None
