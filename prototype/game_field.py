"""
Экран 2 — отрисовка игрового поля.
Координаты совпадают с server/constants.py (центр поля — 0,0; Y вверх).
"""
from __future__ import annotations

from pathlib import Path

import pygame

# Зеркало server/constants.py — не менять без согласования с сервером.
LEFT_WALL = -200.0
RIGHT_WALL = 200.0
TOP_WALL = 300.0
DOWN_WALL = -300.0
GOAL_LEFT = -100.0
GOAL_RIGHT = 100.0
CENTER_CIRCLE_R = 65.0
PLAYER_RADIUS = 50.0
PUCK_RADIUS = 20.0

FIELD_W = RIGHT_WALL - LEFT_WALL
FIELD_H = TOP_WALL - DOWN_WALL

FIELDS_DIR = Path(__file__).resolve().parent.parent / "images" / "fields"
NEON_VELOCITY_FIELD_FILE = "neon_velocity_field.png"

# Области внутри мокапа 682×1024.
NEON_MOCKUP_SIZE = (682, 1024)
# Координаты игры — площадь внутри cyan-борта (те же отступы, что на старом мокапе).
NEON_COORD_NORM = (56 / 682, 56 / 1024, 601 / 682, 916 / 1024)
# Счётные панели — справа на поле (цифры рисуем поверх, без затемнения).
NEON_SCORE_TOP_PANEL_NORM = (540 / 682, 80 / 1024, 83 / 682, 417 / 1024)
NEON_SCORE_BOTTOM_PANEL_NORM = (540 / 682, 520 / 1024, 83 / 682, 429 / 1024)

NEON_THEME = {
    "background": (0, 0, 0),
    "score_text": (47, 208, 255),
}

_neon_field_image: pygame.Surface | None = None
_field_bg_cache: dict[tuple[int, int], tuple[pygame.Surface, pygame.Rect]] = {}
_field_scene_cache: dict[tuple[int, int], tuple[pygame.Surface, "FieldTransform", tuple[pygame.Rect, pygame.Rect]]] = {}
_score_overlay_cache: dict[tuple[int, int, int, int], pygame.Surface] = {}
_puck_surface_cache: dict[int, pygame.Surface] = {}

# 7-segment LED: a=верх, b=верх-право, c=низ-право, d=низ, e=низ-лево, f=верх-лево, g=середина.
_SEVEN_SEGMENT_ON: dict[str, str] = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
}


def reload_field_assets() -> None:
    """Сброс кэша после замены images/fields/neon_velocity_field.png."""
    global _neon_field_image
    _neon_field_image = None
    _field_bg_cache.clear()
    _field_scene_cache.clear()
    _score_overlay_cache.clear()


def _load_neon_field_image() -> pygame.Surface:
    global _neon_field_image
    if _neon_field_image is None:
        _neon_field_image = pygame.image.load(str(FIELDS_DIR / NEON_VELOCITY_FIELD_FILE)).convert()
    return _neon_field_image


def _fit_image_on_screen(surf: pygame.Surface, image: pygame.Surface) -> pygame.Rect:
    sw, sh = surf.get_size()
    iw, ih = image.get_size()
    scale = min(sw / iw, sh / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(image, (nw, nh))
    rect = scaled.get_rect(center=(sw // 2, sh // 2))
    surf.fill((0, 0, 0))
    surf.blit(scaled, rect)
    return rect


def _score_panel_rects(dest: pygame.Rect) -> tuple[pygame.Rect, pygame.Rect]:
    """Верхняя и нижняя счётные панели на мокапе (соперник / я)."""
    top = _norm_rect(dest, NEON_SCORE_TOP_PANEL_NORM)
    bottom = _norm_rect(dest, NEON_SCORE_BOTTOM_PANEL_NORM)
    return top, bottom


def _segment_rects(digit_w: int, digit_h: int, thick: int) -> dict[str, pygame.Rect]:
    gap = max(1, thick // 3)
    inner_w = max(thick, digit_w - 2 * (thick + gap))
    half_h = digit_h // 2
    inner_h = max(thick, half_h - thick - gap)
    return {
        "a": pygame.Rect(thick + gap, 0, inner_w, thick),
        "d": pygame.Rect(thick + gap, digit_h - thick, inner_w, thick),
        "g": pygame.Rect(thick + gap, half_h - thick // 2, inner_w, thick),
        "f": pygame.Rect(0, thick + gap, thick, inner_h),
        "b": pygame.Rect(digit_w - thick, thick + gap, thick, inner_h),
        "e": pygame.Rect(0, half_h + gap, thick, inner_h),
        "c": pygame.Rect(digit_w - thick, half_h + gap, thick, inner_h),
    }


def _draw_neon_segment(surf: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> None:
    r, g, b = color
    pad = 6
    layer = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2), pygame.SRCALPHA)
    local = pygame.Rect(pad, pad, rect.w, rect.h)
    radius = max(1, min(local.w, local.h) // 3)
    for spread, alpha in ((4, 40), (2, 100), (0, 255)):
        glow = local.inflate(spread * 2, spread * 2)
        tone = (
            min(255, r + (40 if spread == 0 else 0)),
            min(255, g + (40 if spread == 0 else 0)),
            255,
            alpha,
        )
        pygame.draw.rect(layer, tone, glow, border_radius=radius + spread // 2)
    surf.blit(layer, (rect.x - pad, rect.y - pad))


def _draw_digital_number(
    surf: pygame.Surface,
    panel: pygame.Rect,
    value: int,
    color: tuple[int, int, int],
) -> None:
    text = str(value)
    digit_h = max(12, int(panel.h * 0.58))
    digit_w = max(8, int(digit_h * 0.52))
    gap = max(2, int(digit_w * 0.2))
    thick = max(2, int(digit_h * 0.1))
    total_w = len(text) * digit_w + max(0, len(text) - 1) * gap
    start_x = panel.centerx - total_w // 2
    start_y = panel.centery - digit_h // 2

    for index, char in enumerate(text):
        segments_on = _SEVEN_SEGMENT_ON.get(char)
        if segments_on is None:
            continue
        origin_x = start_x + index * (digit_w + gap)
        for name, seg in _segment_rects(digit_w, digit_h, thick).items():
            if name in segments_on:
                _draw_neon_segment(surf, seg.move(origin_x, start_y), color)


def _draw_score_in_panel(surf: pygame.Surface, panel: pygame.Rect, value: int) -> None:
    """LED-цифры по центру панели табло (без затемнения фона)."""
    _draw_digital_number(surf, panel, value, NEON_THEME["score_text"])


def _norm_rect(dest: pygame.Rect, norm: tuple[float, float, float, float]) -> pygame.Rect:
    nx, ny, nw, nh = norm
    return pygame.Rect(
        int(dest.x + nx * dest.w),
        int(dest.y + ny * dest.h),
        max(1, int(nw * dest.w)),
        max(1, int(nh * dest.h)),
    )


def _field_background(screen_size: tuple[int, int]) -> tuple[pygame.Surface, pygame.Rect]:
    cached = _field_bg_cache.get(screen_size)
    if cached is not None:
        return cached

    mockup = _load_neon_field_image()
    sw, sh = screen_size
    iw, ih = mockup.get_size()
    scale = min(sw / iw, sh / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(mockup, (nw, nh))
    bg = pygame.Surface(screen_size)
    bg.fill((0, 0, 0))
    dest_rect = scaled.get_rect(center=(sw // 2, sh // 2))
    bg.blit(scaled, dest_rect)
    _field_bg_cache[screen_size] = (bg, dest_rect)
    return bg, dest_rect


class FieldTransform:
    """Игровые координаты → пиксели. Игрок 1 (я) — снизу (отрицательный Y)."""

    def __init__(
        self,
        field_rect: pygame.Rect,
        score_panel_rects: tuple[pygame.Rect, pygame.Rect],
    ):
        self.field_rect = field_rect
        self.score_panel_rects = score_panel_rects
        self.scale = field_rect.width / FIELD_W
        self.origin_x = field_rect.centerx
        self.origin_y = field_rect.centery

    def to_screen(self, gx: float, gy: float) -> tuple[int, int]:
        sx = self.origin_x + gx * self.scale
        sy = self.origin_y - gy * self.scale
        return int(round(sx)), int(round(sy))

    def to_game(self, sx: float, sy: float) -> tuple[float, float]:
        gx = (sx - self.origin_x) / self.scale
        gy = (self.origin_y - sy) / self.scale
        return gx, gy

    def clamp_player1(self, gx: float, gy: float) -> tuple[float, float]:
        """Нижняя половина: только бортики и центральная линия (табло не блокирует)."""
        r = PLAYER_RADIUS
        gx = max(LEFT_WALL + r, min(RIGHT_WALL - r, gx))
        gy = max(DOWN_WALL + r, min(-r, gy))

        rad = self.radius_px(r)
        rink = self.field_rect
        sx, sy = self.to_screen(gx, gy)
        sx = max(rink.left + rad, min(rink.right - rad, sx))
        sy = max(self.to_screen(0, -r)[1], min(rink.bottom - rad, sy))

        gx, gy = self.to_game(sx, sy)
        gx = max(LEFT_WALL + r, min(RIGHT_WALL - r, gx))
        gy = max(DOWN_WALL + r, min(-r, gy))
        return gx, gy

    def radius_px(self, game_radius: float) -> int:
        return max(1, int(round(game_radius * self.scale)))


def draw_score_values(
    surf: pygame.Surface,
    score_panel_rects: tuple[pygame.Rect, pygame.Rect],
    score_first: int,
    score_second: int,
) -> None:
    """score_first — мой счёт (низ), score_second — соперник (верх)."""
    top_panel, bottom_panel = score_panel_rects
    _draw_score_in_panel(surf, top_panel, score_second)
    _draw_score_in_panel(surf, bottom_panel, score_first)


def get_field_scene(
    screen_size: tuple[int, int],
) -> tuple[pygame.Surface, FieldTransform, tuple[pygame.Rect, pygame.Rect]]:
    """Кэш фона и FieldTransform — не пересчитываем каждый кадр."""
    cached = _field_scene_cache.get(screen_size)
    if cached is not None:
        return cached

    bg, dest_rect = _field_background(screen_size)
    play_rect = _norm_rect(dest_rect, NEON_COORD_NORM)
    score_panel_rects = _score_panel_rects(dest_rect)
    tf = FieldTransform(play_rect, score_panel_rects)
    scene = (bg, tf, score_panel_rects)
    _field_scene_cache[screen_size] = scene
    return scene


def _score_overlay(
    screen_size: tuple[int, int],
    score_panel_rects: tuple[pygame.Rect, pygame.Rect],
    live_score: tuple[int, int],
) -> pygame.Surface:
    key = (screen_size[0], screen_size[1], live_score[0], live_score[1])
    overlay = _score_overlay_cache.get(key)
    if overlay is None:
        overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
        draw_score_values(overlay, score_panel_rects, live_score[0], live_score[1])
        _score_overlay_cache[key] = overlay
    return overlay


def draw_puck(surf: pygame.Surface, tf: "FieldTransform", gx: float, gy: float) -> None:
    radius = tf.radius_px(PUCK_RADIUS)
    puck_surf = _puck_surface_cache.get(radius)
    if puck_surf is None:
        size = radius * 2 + 2
        puck_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(puck_surf, (80, 255, 120), center, radius)
        pygame.draw.circle(puck_surf, (200, 255, 220), center, max(1, radius // 3))
        _puck_surface_cache[radius] = puck_surf
    center = tf.to_screen(gx, gy)
    surf.blit(puck_surf, puck_surf.get_rect(center=center))


def draw_game_field(
    surf: pygame.Surface,
    screen_size: tuple[int, int],
    theme: dict | None = None,
    live_score: tuple[int, int] | None = None,
):
    """Neon Velocity — фон и табло строго из мокапа."""
    bg, tf, score_panel_rects = get_field_scene(screen_size)
    surf.blit(bg, (0, 0))
    if live_score is not None:
        surf.blit(_score_overlay(screen_size, score_panel_rects, live_score), (0, 0))
    return tf
