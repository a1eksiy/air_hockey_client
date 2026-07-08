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

# Области внутри мокапа 703×1024.
NEON_MOCKUP_SIZE = (703, 1024)
# Координаты игры — вся площадь внутри cyan-борта (включая зону у табло и ворот).
NEON_COORD_NORM = (58 / 703, 58 / 1024, 613 / 703, 908 / 1024)
NEON_SCORE_NORM = (584 / 703, 58 / 1024, 82 / 703, 908 / 1024)

NEON_THEME = {
    "background": (0, 0, 0),
    "score_text": (47, 208, 255),
}

_neon_field_image: pygame.Surface | None = None


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


def _norm_rect(dest: pygame.Rect, norm: tuple[float, float, float, float]) -> pygame.Rect:
    nx, ny, nw, nh = norm
    return pygame.Rect(
        int(dest.x + nx * dest.w),
        int(dest.y + ny * dest.h),
        max(1, int(nw * dest.w)),
        max(1, int(nh * dest.h)),
    )


def _resolve_circle_rect(sx: float, sy: float, rad: float, rect: pygame.Rect) -> tuple[float, float]:
    """Выталкивает круг из прямоугольника (обводка табло), если он заехал внутрь."""
    if not rect.collidepoint(sx, sy):
        nearest_x = max(rect.left, min(sx, rect.right))
        nearest_y = max(rect.top, min(sy, rect.bottom))
        dx = sx - nearest_x
        dy = sy - nearest_y
        if dx * dx + dy * dy >= rad * rad:
            return sx, sy

    # Ближайшая точка снаружи rect для центра круга.
    if sx < rect.left:
        sx = rect.left - rad
    elif sx > rect.right:
        sx = rect.right + rad
    elif sy < rect.top:
        sy = rect.top - rad
    elif sy > rect.bottom:
        sy = rect.bottom + rad
    else:
        # Центр внутри — выталкиваем в ближайшую сторону.
        dist_left = sx - rect.left
        dist_right = rect.right - sx
        dist_top = sy - rect.top
        dist_bottom = rect.bottom - sy
        best = min(
            (dist_left, "left"),
            (dist_right, "right"),
            (dist_top, "top"),
            (dist_bottom, "bottom"),
            key=lambda item: item[0],
        )
        if best[1] == "left":
            sx = rect.left - rad
        elif best[1] == "right":
            sx = rect.right + rad
        elif best[1] == "top":
            sy = rect.top - rad
        else:
            sy = rect.bottom + rad
    return sx, sy


class FieldTransform:
    """Игровые координаты → пиксели. Игрок 1 (я) — снизу (отрицательный Y)."""

    def __init__(self, field_rect: pygame.Rect, score_box_rect: pygame.Rect):
        self.field_rect = field_rect
        self.score_box_rect = score_box_rect
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
        """
        Нижняя половина: бортики, центральная линия, обводка табло (не внутрь цифр).
        Можно ходить у ворот, под табло и по всей своей половине.
        """
        r = PLAYER_RADIUS
        gx = max(LEFT_WALL + r, min(RIGHT_WALL - r, gx))
        gy = max(DOWN_WALL + r, min(-r, gy))

        rad = self.radius_px(r)
        rink = self.field_rect
        sb = self.score_box_rect
        sx, sy = self.to_screen(gx, gy)

        # Бортики и центральная линия.
        sx = max(rink.left + rad, min(rink.right - rad, sx))
        sy = max(self.to_screen(0, -r)[1], min(rink.bottom - rad, sy))

        # Обводка табло — нельзя заезжать на цифры, но можно под табло у правого борта.
        sx, sy = _resolve_circle_rect(sx, sy, rad, sb)

        gx, gy = self.to_game(sx, sy)
        gx = max(LEFT_WALL + r, min(RIGHT_WALL - r, gx))
        gy = max(DOWN_WALL + r, min(-r, gy))
        return gx, gy

    def radius_px(self, game_radius: float) -> int:
        return max(1, int(round(game_radius * self.scale)))


def draw_score_values(
    surf: pygame.Surface,
    score_box_rect: pygame.Rect,
    score_first: int,
    score_second: int,
) -> None:
    """score_first — мой счёт (низ), score_second — соперник (верх)."""
    cover = pygame.Surface((score_box_rect.w, score_box_rect.h), pygame.SRCALPHA)
    cover.fill((0, 0, 0, 180))
    surf.blit(cover, score_box_rect.topleft)

    font = pygame.font.SysFont("arial", max(24, score_box_rect.w // 2), bold=True)
    color = NEON_THEME["score_text"]

    top_y = score_box_rect.top + score_box_rect.height // 4
    bot_y = score_box_rect.top + 3 * score_box_rect.height // 4
    cx = score_box_rect.centerx

    for value, y in ((score_second, top_y), (score_first, bot_y)):
        text = font.render(str(value), True, color)
        surf.blit(text, (cx - text.get_width() // 2, y - text.get_height() // 2))


def draw_puck(surf: pygame.Surface, tf: "FieldTransform", gx: float, gy: float) -> None:
    center = tf.to_screen(gx, gy)
    radius = tf.radius_px(PUCK_RADIUS)
    pygame.draw.circle(surf, (80, 255, 120), center, radius)
    pygame.draw.circle(surf, (200, 255, 220), center, max(1, radius // 3))


def draw_game_field(
    surf: pygame.Surface,
    screen_size: tuple[int, int],
    theme: dict | None = None,
    live_score: tuple[int, int] | None = None,
):
    """Neon Velocity — фон и табло строго из мокапа. live_score — для будущего обновления с сервера."""
    theme = theme or NEON_THEME
    mockup = _load_neon_field_image()
    dest_rect = _fit_image_on_screen(surf, mockup)

    play_rect = _norm_rect(dest_rect, NEON_COORD_NORM)
    score_rect = _norm_rect(dest_rect, NEON_SCORE_NORM)
    tf = FieldTransform(play_rect, score_rect)

    if live_score is not None:
        draw_score_values(surf, score_rect, live_score[0], live_score[1])

    return tf
