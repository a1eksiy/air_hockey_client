"""
Экран 2 — отрисовка игрового поля.
Координаты совпадают с server/constants.py (центр поля — 0,0; Y вверх).
"""
from __future__ import annotations

from dataclasses import dataclass
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
PUCKS_DIR = Path(__file__).resolve().parent.parent / "images" / "pucks"

# Мокапы полей — общая геометрия игры (682×1024 эталон)
MOCKUP_SIZE = (682, 1024)
PLAY_COORD_NORM = (56 / 682, 56 / 1024, 601 / 682, 916 / 1024)
SCORE_PANEL_W_NORM = 83 / 682

# X панели счёта подогнан под правый борт каждого мокапа (34px от борта до правого края цифр).
SCORE_PANEL_X_NORMS: dict[str, float] = {
    "Neon Velocity": 540 / 682,
    "Cosmic Rink": 541 / 682,
    "Sprinkle Slam": 564 / 682,
}
# Горизонталь вспышки ворот на мокапах: (x_left, width) в долях play_rect; высота фикс.
GOAL_FLASH_WIDTH_NORMS: dict[str, dict[str, tuple[float, float]]] = {
    "Neon Velocity": {
        "top": (0.2063, 0.5308),
        "bottom": (0.2146, 0.5208),
    },
    "Cosmic Rink": {
        "top": (0.2146, 0.5108),
        "bottom": (0.2163, 0.5092),
    },
    "Sprinkle Slam": {
        "top": (0.1997, 0.5491),
        "bottom": (0.1963, 0.5557),
    },
}
GOAL_FLASH_HEIGHT_FRAC = 0.048

DEFAULT_MODE = "Neon Velocity"
NEON_SCORE_COLOR = (47, 208, 255)
COSMIC_SCORE_COLOR = (180, 90, 255)
SPRINKLE_SCORE_COLOR = (255, 120, 200)


@dataclass(frozen=True)
class FieldTheme:
    field_file: str
    puck_file: str
    puck_visible_diam_frac: float
    score_text_color: tuple[int, int, int] = NEON_SCORE_COLOR


FIELD_THEMES: dict[str, FieldTheme] = {
    "Neon Velocity": FieldTheme(
        field_file="neon_velocity_field.png",
        puck_file="neon_velocity_puck.png",
        puck_visible_diam_frac=451 / 1024,
        score_text_color=NEON_SCORE_COLOR,
    ),
    "Cosmic Rink": FieldTheme(
        field_file="cosmic_rink_field.png",
        puck_file="cosmic_rink_moon.png",
        puck_visible_diam_frac=297 / 360,
        score_text_color=COSMIC_SCORE_COLOR,
    ),
    "Sprinkle Slam": FieldTheme(
        field_file="sprinkle_slam_field.png",
        puck_file="sprinkle_slam_pancake.png",
        puck_visible_diam_frac=651 / 980,
        score_text_color=SPRINKLE_SCORE_COLOR,
    ),
}

_field_image_cache: dict[str, pygame.Surface] = {}
_puck_image_cache: dict[str, pygame.Surface] = {}
_field_bg_cache: dict[tuple[str, int, int], tuple[pygame.Surface, pygame.Rect]] = {}
_field_scene_cache: dict[tuple[str, int, int], tuple[pygame.Surface, "FieldTransform", tuple[pygame.Rect, pygame.Rect]]] = {}
_score_overlay_cache: dict[tuple[str, int, int, int, int], pygame.Surface] = {}
_puck_surface_cache: dict[tuple[str, int], pygame.Surface] = {}

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


def get_theme(mode_name: str | None) -> FieldTheme:
    if mode_name and mode_name in FIELD_THEMES:
        return FIELD_THEMES[mode_name]
    return FIELD_THEMES[DEFAULT_MODE]


def reload_field_assets() -> None:
    _field_image_cache.clear()
    _puck_image_cache.clear()
    _field_bg_cache.clear()
    _field_scene_cache.clear()
    _score_overlay_cache.clear()
    _puck_surface_cache.clear()


def _load_field_image(theme: FieldTheme) -> pygame.Surface:
    cached = _field_image_cache.get(theme.field_file)
    if cached is None:
        cached = pygame.image.load(str(FIELDS_DIR / theme.field_file)).convert()
        _field_image_cache[theme.field_file] = cached
    return cached


def _load_puck_image(theme: FieldTheme) -> pygame.Surface:
    cached = _puck_image_cache.get(theme.puck_file)
    if cached is None:
        cached = pygame.image.load(str(PUCKS_DIR / theme.puck_file)).convert_alpha()
        _puck_image_cache[theme.puck_file] = cached
    return cached


def _score_panel_x_norm(mode_name: str | None) -> float:
    if mode_name and mode_name in SCORE_PANEL_X_NORMS:
        return SCORE_PANEL_X_NORMS[mode_name]
    return SCORE_PANEL_X_NORMS["Neon Velocity"]


def _score_panel_rects(dest: pygame.Rect, mode_name: str | None = None) -> tuple[pygame.Rect, pygame.Rect]:
    x_norm = _score_panel_x_norm(mode_name)
    top = _norm_rect(dest, (x_norm, 80 / 1024, SCORE_PANEL_W_NORM, 417 / 1024))
    bottom = _norm_rect(dest, (x_norm, 520 / 1024, SCORE_PANEL_W_NORM, 429 / 1024))
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


def _draw_score_in_panel(
    surf: pygame.Surface,
    panel: pygame.Rect,
    value: int,
    color: tuple[int, int, int],
) -> None:
    _draw_digital_number(surf, panel, value, color)


def _norm_rect(dest: pygame.Rect, norm: tuple[float, float, float, float]) -> pygame.Rect:
    nx, ny, nw, nh = norm
    return pygame.Rect(
        int(dest.x + nx * dest.w),
        int(dest.y + ny * dest.h),
        max(1, int(nw * dest.w)),
        max(1, int(nh * dest.h)),
    )


def _field_background(
    screen_size: tuple[int, int],
    theme: FieldTheme,
) -> tuple[pygame.Surface, pygame.Rect]:
    key = (theme.field_file, screen_size[0], screen_size[1])
    cached = _field_bg_cache.get(key)
    if cached is not None:
        return cached

    mockup = _load_field_image(theme)
    sw, sh = screen_size
    iw, ih = mockup.get_size()
    scale = min(sw / iw, sh / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(mockup, (nw, nh))
    bg = pygame.Surface(screen_size)
    bg.fill((0, 0, 0))
    
    # Изображение ровно по центру окна
    dest_rect = scaled.get_rect(center=(sw // 2, sh // 2))
    bg.blit(scaled, dest_rect)
    _field_bg_cache[key] = (bg, dest_rect)
    return bg, dest_rect


class FieldTransform:
    """Игровые координаты → пиксели. Игрок 1 (я) — снизу (отрицательный Y)."""

    def __init__(
        self,
        field_rect: pygame.Rect,
        score_panel_rects: tuple[pygame.Rect, pygame.Rect],
        mockup_rect: pygame.Rect | None = None,
    ):
        self.field_rect = field_rect
        self.mockup_rect = mockup_rect if mockup_rect is not None else field_rect
        self.score_panel_rects = score_panel_rects
        self.scale = field_rect.width / FIELD_W
        
        # === ИСПРАВЛЕНИЕ ===
        # За 0,0 берем не кривую физическую зону (где справа табло),
        # а ИДЕАЛЬНЫЙ геометрический центр фоновой картинки (mockup_rect).
        self.origin_x = self.mockup_rect.centerx
        self.origin_y = self.mockup_rect.centery

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

    def field_overlay_rect(self) -> pygame.Rect:
        """Видимое поле на экране (мокап) — для оверлеев по центру картинки."""
        return self.mockup_rect

    def field_overlay_center(self) -> tuple[int, int]:
        return self.mockup_rect.center


def goal_flash_rect(
    tf: FieldTransform,
    mode_name: str | None,
    target: str,
) -> pygame.Rect:
    """Вспышка вплотную к краю поля: зелёная — вверх, красная — вниз."""
    theme_name = mode_name if mode_name in GOAL_FLASH_WIDTH_NORMS else DEFAULT_MODE
    nx, nw = GOAL_FLASH_WIDTH_NORMS[theme_name][target]
    rink = tf.field_rect
    width = max(8, int(nw * rink.width))
    height = max(6, int(GOAL_FLASH_HEIGHT_FRAC * rink.height))
    left = int(rink.x + nx * rink.width)
    if target == "top":
        top = rink.top
    else:
        top = rink.bottom - height
    return pygame.Rect(left, top, width, height)


def draw_score_values(
    surf: pygame.Surface,
    score_panel_rects: tuple[pygame.Rect, pygame.Rect],
    score_first: int,
    score_second: int,
    score_text_color: tuple[int, int, int],
) -> None:
    top_panel, bottom_panel = score_panel_rects
    _draw_score_in_panel(surf, top_panel, score_second, score_text_color)
    _draw_score_in_panel(surf, bottom_panel, score_first, score_text_color)


def get_field_scene(
    screen_size: tuple[int, int],
    mode_name: str | None = None,
) -> tuple[pygame.Surface, FieldTransform, tuple[pygame.Rect, pygame.Rect]]:
    theme = get_theme(mode_name)
    key = (theme.field_file, screen_size[0], screen_size[1])
    cached = _field_scene_cache.get(key)
    if cached is not None:
        return cached

    bg, dest_rect = _field_background(screen_size, theme)
    play_rect = _norm_rect(dest_rect, PLAY_COORD_NORM)
    score_panel_rects = _score_panel_rects(dest_rect, mode_name)
    tf = FieldTransform(play_rect, score_panel_rects, mockup_rect=dest_rect)
    scene = (bg, tf, score_panel_rects)
    _field_scene_cache[key] = scene
    return scene


def _score_overlay(
    mode_name: str | None,
    screen_size: tuple[int, int],
    score_panel_rects: tuple[pygame.Rect, pygame.Rect],
    live_score: tuple[int, int],
) -> pygame.Surface:
    theme = get_theme(mode_name)
    key = (theme.field_file, screen_size[0], screen_size[1], live_score[0], live_score[1])
    overlay = _score_overlay_cache.get(key)
    if overlay is None:
        overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
        draw_score_values(
            overlay,
            score_panel_rects,
            live_score[0],
            live_score[1],
            theme.score_text_color,
        )
        _score_overlay_cache[key] = overlay
    return overlay


def _apply_circle_mask(surf: pygame.Surface) -> pygame.Surface:
    size = surf.get_width()
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
    circular = surf.copy().convert_alpha()
    circular.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return circular


def _puck_surface(theme: FieldTheme, radius: int) -> pygame.Surface:
    key = (theme.puck_file, radius)
    cached = _puck_surface_cache.get(key)
    if cached is not None:
        return cached

    source = _load_puck_image(theme)
    diameter = max(4, int(round(2 * radius / theme.puck_visible_diam_frac)))
    scaled = pygame.transform.scale(source, (diameter, diameter))
    cached = _apply_circle_mask(scaled)
    _puck_surface_cache[key] = cached
    return cached


def draw_puck(
    surf: pygame.Surface,
    tf: FieldTransform,
    gx: float,
    gy: float,
    mode_name: str | None = None,
) -> None:
    theme = get_theme(mode_name)
    radius = tf.radius_px(PUCK_RADIUS)
    puck_surf = _puck_surface(theme, radius)
    center = tf.to_screen(gx, gy)
    surf.blit(puck_surf, puck_surf.get_rect(center=center))


def warm_game_assets(
    screen_size: tuple[int, int],
    mode_name: str | None = None,
) -> FieldTransform:
    _, tf, _ = get_field_scene(screen_size, mode_name)
    theme = get_theme(mode_name)
    _puck_surface(theme, tf.radius_px(PUCK_RADIUS))
    return tf


def draw_game_field(
    surf: pygame.Surface,
    screen_size: tuple[int, int],
    mode_name: str | None = None,
    live_score: tuple[int, int] | None = None,
):
    bg, tf, score_panel_rects = get_field_scene(screen_size, mode_name)
    surf.blit(bg, (0, 0))
    if live_score is not None:
        surf.blit(_score_overlay(mode_name, screen_size, score_panel_rects, live_score), (0, 0))
    return tf