"""
Aerohockey - интерактивный прототип Splash-экрана (реальное окно, кликабельно).
Черновая версия для теста механики — до нормального движка это дублирует
часть отрисовки из aerohockey_prototype.py, объединим при переходе на движок.

Управление:
  - клик по Menu  -> открыть/закрыть список режимов
  - клик по карточке режима -> выбрать (radio, один активный)
  - клик по Sound -> открыть/закрыть слайдер громкости, тащи кружок мышкой
  - клик по Play  -> overlay выбора счёта (2 карточки)
  - клик по карточке счёта -> выбрать счёт, затем overlay стиков снизу (2 варианта)
  - клик по стику -> выбрать (выбранный крупнее и подсвечен)
  - ESC / закрытие окна -> выход
"""
from pathlib import Path

import pygame

from game_field import DOWN_WALL, PLAYER_RADIUS, draw_game_field, draw_puck, get_field_scene
from network_client import GameClient

pygame.init()
pygame.font.init()

W, H = 1186, 670
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Aerohockey — Splash Prototype")
clock = pygame.time.Clock()

BLACK = (0, 0, 0)
BLUE = (38, 98, 238)
BLUE_HOVER = (58, 118, 255)
BLUE_GLOW = (90, 160, 255)
TEAL = (60, 140, 124)
TEAL_HOVER = (74, 168, 148)
CYAN = (47, 208, 255)
OLIVE = (206, 194, 90)
ICON_SHADOW = (18, 18, 18)
GRAY = (107, 107, 107)
PANEL = (58, 58, 58)
TEXT = (230, 230, 230)

FONT = pygame.font.SysFont("arial", 18)
FONT_SMALL = pygame.font.SysFont("arial", 14)
GAME_HINT_SURF = FONT_SMALL.render(
    "ESC — меню  |  мышь — стик  |  нужен сервер + 2 окна для матча",
    True,
    (120, 120, 120),
)
_status_surf_cache: dict[str, pygame.Surface] = {}

PLAY_CENTER = (593, 515)
PLAY_R = 74
MENU_CENTER = (1052, 86)
SOUND_CENTER = (1052, 262)
SMALL_R = 44

MODES = [
    "Cosmic Rink",      # космос: Земля/Марс, шайба — Луна
    "Neon Velocity",    # неон-классика (режим по умолчанию)
    "Sprinkle Slam",    # пончик: пончики, шайба — панкейк
]
SCORE_OPTIONS = [
    ("free", "Free Game"),
    ("to5", "First To Five"),
]
SCORE_LABELS = [label for _, label in SCORE_OPTIONS]

ASSETS_DIR = Path(__file__).resolve().parent.parent / "images"
ICONS_DIR = ASSETS_DIR / "icons"
STICKS_DIR = ASSETS_DIR / "sticks"
STICKERS_DIR = Path(__file__).resolve().parent.parent / "stickers"
STICK_NORMALIZED_SIZE = 256
STICK_DISPLAY_DIAMETER = 104
STICK_DISPLAY_DIAMETER_SELECTED = 152

# Готовые PNG стиков (images/sticks/), порядок: стик 1 / стик 2 для режима.
STICK_DEFS = {
    "Cosmic Rink": [
        "cosmic_rink_earth.png",
        "cosmic_rink_mars.png",
    ],
    "Neon Velocity": [
        "neon_velocity_blue.png",
        "neon_velocity_magenta.png",
    ],
    "Sprinkle Slam": [
        "sprinkle_slam_pink.png",
        "sprinkle_slam_chocolate.png",
    ],
}

CARD_X, CARD_Y0, CARD_W, CARD_H, CARD_GAP = 463, 50, 270, 40, 16
MODE_STICKER_H = 36
MODE_STICKER_GAP = 6
NEON_MODE_INDEX = 1
MODE_CARD_STICKERS = {
    0: {
        "left": "боковой стикер для иконки режима космос (слева).png",
        "right": "cosmic_rink_sticker_right.png",
    },
    2: {
        "left": "боковой стикер для иконки режима пончик (слева).png",
        "right": "боковой стикер для иконки режима пончик (справа).png",
    },
}
STICK_BAR_H = 132
STICK_BAR_Y = H - STICK_BAR_H - 34
STICK_SIZE_DEFAULT = STICK_DISPLAY_DIAMETER // 2
STICK_SIZE_SELECTED = STICK_DISPLAY_DIAMETER_SELECTED // 2
STICK_GAP = 80

_stick_sources = {}
_sticker_cache = {}
_field_stick_cache = {}
_sound_note_icon = None

SLIDER_RECT = pygame.Rect(930, 385, 220, 8)
SLIDER_TRACK_H = 8
SLIDER_SIGN_OFFSET = 28


def draw_glow_circle(surf, center, radius, fill_color, glow_color, layers=10, max_extra=34):
    pad = max_extra
    glow = pygame.Surface((radius * 2 + pad * 2, radius * 2 + pad * 2), pygame.SRCALPHA)
    gc = (glow.get_width() // 2, glow.get_height() // 2)
    for i in range(layers, 0, -1):
        alpha = int(200 * (i / layers) ** 2)
        r = radius + int(pad * (i / layers))
        pygame.draw.circle(glow, (*glow_color, alpha), gc, r)
    surf.blit(glow, (center[0] - gc[0], center[1] - gc[1]))
    pygame.draw.circle(surf, fill_color, center, radius)
    pygame.draw.circle(surf, glow_color, center, radius, width=3)


def draw_glow_only(surf, center, radius, glow_color, layers=10, max_extra=28):
    pad = max_extra
    glow = pygame.Surface((radius * 2 + pad * 2, radius * 2 + pad * 2), pygame.SRCALPHA)
    gc = (glow.get_width() // 2, glow.get_height() // 2)
    for i in range(layers, 0, -1):
        alpha = int(180 * (i / layers) ** 2)
        r = radius + int(pad * (i / layers))
        pygame.draw.circle(glow, (*glow_color, alpha), gc, r)
    surf.blit(glow, (center[0] - gc[0], center[1] - gc[1]))


def draw_icon_with_shadow(draw_fn, surf, center, size, color, shadow_offset=(3, 4)):
    shadow_center = (center[0] + shadow_offset[0], center[1] + shadow_offset[1])
    draw_fn(surf, shadow_center, size, ICON_SHADOW)
    draw_fn(surf, center, size, color)


def sound_note_icon():
    global _sound_note_icon
    if _sound_note_icon is None:
        _sound_note_icon = pygame.image.load(str(ICONS_DIR / "sound_note.png")).convert_alpha()
    return _sound_note_icon


def blit_image_icon_with_shadow(surf, center, image, height=40, shadow_offset=(3, 4)):
    src_w, src_h = image.get_size()
    scale = height / src_h
    size = (max(1, int(src_w * scale)), height)
    icon = pygame.transform.smoothscale(image, size)
    rect = icon.get_rect(center=center)
    shadow_icon = icon.copy()
    shadow_icon.fill((0, 0, 0, 180), special_flags=pygame.BLEND_RGBA_MULT)
    shadow_rect = rect.copy()
    shadow_rect.x += shadow_offset[0]
    shadow_rect.y += shadow_offset[1]
    surf.blit(shadow_icon, shadow_rect)
    surf.blit(icon, rect)


def draw_rounded_rect(surf, rect, color, radius=4):
    pygame.draw.rect(surf, color, rect, border_radius=radius)


def draw_triangle(surf, center, size, color):
    x, y = center
    pts = [(x - size * 0.45, y - size * 0.65), (x - size * 0.45, y + size * 0.65), (x + size * 0.75, y)]
    pygame.draw.polygon(surf, color, pts)


def draw_hamburger(surf, center, size, color):
    x, y = center
    for dy in (-size * 0.35, 0, size * 0.35):
        pygame.draw.rect(surf, color, (x - size * 0.5, y + dy - 3, size, 6), border_radius=3)


def draw_note(surf, center, size, color):
    x, y = center
    stem_x = x - size * 0.05
    pygame.draw.circle(surf, color, (int(x - size * 0.28), int(y + size * 0.32)), int(size * 0.16))
    pygame.draw.line(surf, color, (stem_x, y + size * 0.32), (stem_x, y - size * 0.5), 4)
    pygame.draw.line(surf, color, (stem_x, y - size * 0.5), (stem_x + size * 0.32, y - size * 0.62), 4)


def card_rects(labels, y0=CARD_Y0):
    rects = []
    y = y0
    for _ in labels:
        rects.append(pygame.Rect(CARD_X, y, CARD_W, CARD_H))
        y += CARD_H + CARD_GAP
    return rects


def mode_card_rects():
    return card_rects(MODES)


def score_card_rects():
    total_h = len(SCORE_LABELS) * CARD_H + (len(SCORE_LABELS) - 1) * CARD_GAP
    y0 = (H - total_h) // 2
    return card_rects(SCORE_LABELS, y0=y0)


def draw_overlay_panel():
    panel = pygame.Surface((W - 40, H - 20), pygame.SRCALPHA)
    panel.fill((*PANEL, 235))
    screen.blit(panel, (18, 10))


def draw_cards(labels, rects, selected_index):
    for i, rect in enumerate(rects):
        color = TEAL if i == selected_index else GRAY
        card = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(card, (*color, 210), (0, 0, rect.w, rect.h), border_radius=14)
        screen.blit(card, rect.topleft)
        label = FONT.render(labels[i], True, TEXT)
        screen.blit(
            label,
            (rect.centerx - label.get_width() // 2, rect.y + rect.h // 2 - label.get_height() // 2),
        )


def load_sticker(filename):
    if filename not in _sticker_cache:
        _sticker_cache[filename] = pygame.image.load(str(STICKERS_DIR / filename)).convert_alpha()
    return _sticker_cache[filename]


def scaled_sticker(filename, target_h):
    source = load_sticker(filename)
    src_w, src_h = source.get_size()
    scale = target_h / src_h
    target_w = max(1, int(src_w * scale))
    return pygame.transform.smoothscale(source, (target_w, target_h))


def draw_card_neon_glow(rect):
    glow_surf = pygame.Surface((rect.w + 24, rect.h + 24), pygame.SRCALPHA)
    inner = pygame.Rect(12, 12, rect.w, rect.h)
    for i in range(6, 0, -1):
        alpha = int(70 + 20 * i)
        inflated = inner.inflate(i * 2, i * 2)
        pygame.draw.rect(glow_surf, (*CYAN, alpha), inflated, width=2, border_radius=14 + i)
    screen.blit(glow_surf, (rect.x - 12, rect.y - 12))


def draw_mode_cards(selected_index):
    rects = mode_card_rects()
    for i, rect in enumerate(rects):
        if i == NEON_MODE_INDEX:
            draw_card_neon_glow(rect)

        color = TEAL if i == selected_index else GRAY
        card = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(card, (*color, 210), (0, 0, rect.w, rect.h), border_radius=14)
        screen.blit(card, rect.topleft)

        label = FONT.render(MODES[i], True, TEXT)
        screen.blit(
            label,
            (rect.centerx - label.get_width() // 2, rect.y + rect.h // 2 - label.get_height() // 2),
        )

        stickers = MODE_CARD_STICKERS.get(i)
        if stickers:
            left = scaled_sticker(stickers["left"], MODE_STICKER_H)
            right = scaled_sticker(stickers["right"], MODE_STICKER_H)
            left_x = rect.x - MODE_STICKER_GAP - left.get_width()
            right_x = rect.right + MODE_STICKER_GAP
            sticker_y = rect.centery - MODE_STICKER_H // 2
            screen.blit(left, (left_x, sticker_y))
            screen.blit(right, (right_x, sticker_y))


def current_mode_index():
    if state.selected_mode is not None:
        return state.selected_mode
    return 1


def current_mode_name():
    return MODES[current_mode_index()]


def trim_stick_image(surf):
    w, h = surf.get_size()
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = surf.get_at((x, y))
            if a < 128:
                continue
            if r > 240 and g > 240 and b > 240:
                continue
            if r + g + b < 25:
                continue
            found = True
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
    if not found:
        return surf.copy()
    rect = pygame.Rect(minx, miny, maxx - minx + 1, maxy - miny + 1)
    return surf.subsurface(rect).copy()


def normalize_stick_source(surf):
    """Обрезает пустые поля и приводит все стики к одному квадратному размеру."""
    trimmed = trim_stick_image(surf)
    tw, th = trimmed.get_size()
    scale = STICK_NORMALIZED_SIZE / max(tw, th)
    nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
    scaled = pygame.transform.smoothscale(trimmed, (nw, nh))
    canvas = pygame.Surface((STICK_NORMALIZED_SIZE, STICK_NORMALIZED_SIZE), pygame.SRCALPHA)
    canvas.blit(scaled, ((STICK_NORMALIZED_SIZE - nw) // 2, (STICK_NORMALIZED_SIZE - nh) // 2))
    return canvas


def load_stick_source(mode_name, stick_index):
    key = (mode_name, stick_index)
    if key in _stick_sources:
        return _stick_sources[key]

    filename = STICK_DEFS[mode_name][stick_index]
    image = pygame.image.load(str(STICKS_DIR / filename)).convert_alpha()
    source = normalize_stick_source(image)
    _stick_sources[key] = source
    return source


def scaled_stick_surface(mode_name, stick_index, selected):
    source = load_stick_source(mode_name, stick_index)
    target = STICK_DISPLAY_DIAMETER_SELECTED if selected else STICK_DISPLAY_DIAMETER
    return pygame.transform.smoothscale(source, (target, target))


def stick_display_radius(stick_index):
    selected = stick_index == state.selected_stick
    size = STICK_SIZE_SELECTED if selected else STICK_SIZE_DEFAULT
    return size + 6


def stick_centers():
    n = 2
    slot = STICK_SIZE_SELECTED * 2 + STICK_GAP
    total_w = n * slot - STICK_GAP
    x = (W - total_w) // 2 + STICK_SIZE_SELECTED
    cy = STICK_BAR_Y + STICK_BAR_H // 2 + 8
    return [(x + i * slot, cy) for i in range(n)]


def stick_hit_radius(index):
    return stick_display_radius(index) + 10


def draw_stick_sprite(center, stick_index):
    selected = stick_index == state.selected_stick
    surf = scaled_stick_surface(current_mode_name(), stick_index, selected)
    if selected:
        glow_r = surf.get_width() // 2 + 8
        draw_glow_only(screen, center, glow_r, CYAN, layers=8, max_extra=22)
    rect = surf.get_rect(center=center)
    screen.blit(surf, rect)


def draw_sound_slider():
    track_rect = pygame.Rect(SLIDER_RECT.x, SLIDER_RECT.centery - SLIDER_TRACK_H // 2, SLIDER_RECT.width, SLIDER_TRACK_H)
    draw_rounded_rect(screen, track_rect, GRAY, radius=4)

    minus = FONT.render("-", True, TEXT)
    plus = FONT.render("+", True, TEXT)
    screen.blit(minus, (SLIDER_RECT.x - SLIDER_SIGN_OFFSET - minus.get_width(), SLIDER_RECT.centery - minus.get_height() // 2))
    screen.blit(plus, (SLIDER_RECT.right + SLIDER_SIGN_OFFSET, SLIDER_RECT.centery - plus.get_height() // 2))

    knob_x = SLIDER_RECT.x + state.volume * SLIDER_RECT.width
    draw_glow_circle(screen, (knob_x, SLIDER_RECT.centery), 10, BLUE, BLUE_GLOW, layers=6, max_extra=14)
    pct = FONT_SMALL.render(f"{int(state.volume * 100)}%", True, TEXT)
    screen.blit(pct, (SLIDER_RECT.centerx - pct.get_width() // 2, SLIDER_RECT.top - 24))


def draw_stick_bar():
    bar = pygame.Surface((W - 36, STICK_BAR_H), pygame.SRCALPHA)
    bar.fill((*PANEL, 220))
    screen.blit(bar, (18, STICK_BAR_Y))

    title = FONT_SMALL.render("Choose Your Stick", True, TEXT)
    screen.blit(title, (W // 2 - title.get_width() // 2, STICK_BAR_Y + 10))

    for i, center in enumerate(stick_centers()):
        draw_stick_sprite(center, i)


def field_stick_surface(mode_name, stick_index, tf):
    diam = max(16, tf.radius_px(PLAYER_RADIUS) * 2)
    key = (mode_name, stick_index, diam)
    if key not in _field_stick_cache:
        source = load_stick_source(mode_name, stick_index)
        scaled = pygame.transform.smoothscale(source, (diam, diam))
        _field_stick_cache[key] = _apply_circle_mask(scaled)
    return _field_stick_cache[key]


def _apply_circle_mask(surf):
    """Обрезает спрайт по кругу — стик на поле выглядит круглым."""
    size = surf.get_width()
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
    circular = surf.copy()
    circular.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return circular


def draw_field_stick(tf, gx, gy, stick_index=None):
    if stick_index is None:
        stick_index = state.selected_stick if state.selected_stick is not None else 0
    surf = field_stick_surface(current_mode_name(), stick_index, tf)
    center = tf.to_screen(gx, gy)
    rect = surf.get_rect(center=center)
    screen.blit(surf, rect)


def stop_game():
    if state.game_client is not None:
        state.game_client.stop()
        state.game_client = None
    state.screen = "splash"
    state.field_transform = None
    state.game_status = ""


def start_game():
    stop_game()
    state.screen = "game"
    state.show_menu = False
    state.show_sound = False
    state.show_score = False
    state.show_stick = False
    state.field_transform = None
    state.player_stick_pos = (0.0, DOWN_WALL + PLAYER_RADIUS)
    state.game_status = "Подключение к серверу..."
    mode = current_mode_name()
    _, state.field_transform, _ = get_field_scene((W, H), mode)
    state.game_client = GameClient()
    state.game_client.start()


def update_player_stick_from_mouse(pos):
    if state.field_transform is None:
        return
    gx, gy = state.field_transform.to_game(pos[0], pos[1])
    state.player_stick_pos = state.field_transform.clamp_player1(gx, gy)


def in_circle(pos, center, radius):
    dx, dy = pos[0] - center[0], pos[1] - center[1]
    return dx * dx + dy * dy <= radius * radius


class State:
    screen = "splash"
    show_menu = False
    show_sound = False
    show_score = False
    show_stick = False
    selected_mode = None
    selected_score = None
    selected_stick = None
    volume = 0.7
    dragging_slider = False
    play_flash_frames = 0
    field_transform = None
    player_stick_pos = (0.0, -250.0)
    game_client = None
    game_status = ""


state = State()


def handle_click(pos):
    if in_circle(pos, MENU_CENTER, SMALL_R):
        state.show_menu = not state.show_menu
        state.show_sound = False
        state.show_score = False
        state.show_stick = False
        return

    if in_circle(pos, SOUND_CENTER, SMALL_R):
        state.show_sound = not state.show_sound
        state.show_menu = False
        state.show_score = False
        state.show_stick = False
        return

    if in_circle(pos, PLAY_CENTER, PLAY_R):
        if state.selected_stick is not None:
            start_game()
            state.play_flash_frames = 12
            return
        state.show_score = True
        state.show_stick = False
        state.show_menu = False
        state.show_sound = False
        state.play_flash_frames = 12
        return

    if state.show_stick:
        for i, center in enumerate(stick_centers()):
            if in_circle(pos, center, stick_hit_radius(i)):
                state.selected_stick = i
                return
        stick_bar_rect = pygame.Rect(18, STICK_BAR_Y, W - 36, STICK_BAR_H)
        if not stick_bar_rect.collidepoint(pos):
            state.show_stick = False
        return

    if state.show_score:
        for i, rect in enumerate(score_card_rects()):
            if rect.collidepoint(pos):
                state.selected_score = i
                state.show_score = False
                state.show_stick = True
                return
        state.show_score = False
        return

    if state.show_menu:
        for i, rect in enumerate(mode_card_rects()):
            if rect.collidepoint(pos):
                state.selected_mode = i
                return
        state.show_menu = False
        return

    if state.show_sound:
        knob_x = SLIDER_RECT.x + state.volume * SLIDER_RECT.width
        knob_center = (knob_x, SLIDER_RECT.centery)
        if in_circle(pos, knob_center, 12) or SLIDER_RECT.inflate(0, 20).collidepoint(pos):
            state.dragging_slider = True
            update_volume_from_x(pos[0])
        else:
            state.show_sound = False


def update_volume_from_x(x):
    t = (x - SLIDER_RECT.x) / SLIDER_RECT.width
    state.volume = max(0.0, min(1.0, t))


def draw_game_screen():
    client = state.game_client
    connected = False
    live = None
    if client is not None:
        connected, live, status, msgs = client.snapshot()
        if msgs:
            state.game_status = msgs[-1]
        if status:
            state.game_status = status

    if live is not None:
        live_score = live.score
    elif connected:
        live_score = (0, 0)
    else:
        live_score = None

    mode = current_mode_name()
    tf = draw_game_field(screen, (W, H), mode_name=mode, live_score=live_score)
    state.field_transform = tf

    update_player_stick_from_mouse(pygame.mouse.get_pos())
    if client is not None:
        client.set_position(state.player_stick_pos[0], state.player_stick_pos[1])

    my_stick = state.selected_stick if state.selected_stick is not None else 0
    opp_stick = 1 if my_stick == 0 else 0

    if live is not None:
        draw_field_stick(tf, state.player_stick_pos[0], state.player_stick_pos[1], stick_index=my_stick)
        draw_field_stick(tf, live.player2[0], live.player2[1], stick_index=opp_stick)
        draw_puck(screen, tf, live.puck[0], live.puck[1], mode_name=mode)
    else:
        draw_field_stick(tf, state.player_stick_pos[0], state.player_stick_pos[1], stick_index=my_stick)
        draw_puck(screen, tf, 0.0, 0.0, mode_name=mode)

    if state.game_status:
        status_surf = _status_surf_cache.get(state.game_status)
        if status_surf is None:
            status_surf = FONT_SMALL.render(state.game_status, True, (180, 220, 255))
            _status_surf_cache[state.game_status] = status_surf
        screen.blit(status_surf, (18, 12))

    screen.blit(GAME_HINT_SURF, (18, H - 26))
    pygame.display.flip()


def draw():
    if state.screen == "game":
        draw_game_screen()
        return

    screen.fill(BLACK)

    play_color = TEAL_HOVER if state.play_flash_frames > 0 else TEAL
    draw_glow_circle(screen, PLAY_CENTER, PLAY_R, play_color, CYAN)
    draw_icon_with_shadow(draw_triangle, screen, PLAY_CENTER, 50, OLIVE)

    draw_glow_circle(screen, MENU_CENTER, SMALL_R, TEAL, CYAN)
    draw_icon_with_shadow(draw_hamburger, screen, MENU_CENTER, 40, OLIVE)

    draw_glow_circle(screen, SOUND_CENTER, SMALL_R, TEAL, CYAN)
    blit_image_icon_with_shadow(screen, SOUND_CENTER, sound_note_icon(), height=40)

    if state.show_menu:
        draw_overlay_panel()
        draw_mode_cards(state.selected_mode)

    if state.show_score:
        draw_overlay_panel()
        draw_cards(SCORE_LABELS, score_card_rects(), state.selected_score)

    if state.show_stick:
        draw_stick_bar()

    if state.show_sound:
        draw_sound_slider()

    hint = FONT_SMALL.render("ESC — выход  |  Play → счёт → стик → Play", True, (120, 120, 120))
    screen.blit(hint, (18, H - 26))

    pygame.display.flip()


running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if state.screen == "game":
                stop_game()
            else:
                running = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            handle_click(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            state.dragging_slider = False
        elif event.type == pygame.MOUSEMOTION and state.dragging_slider:
            update_volume_from_x(event.pos[0])

    if state.play_flash_frames > 0:
        state.play_flash_frames -= 1

    draw()
    clock.tick(60)

pygame.quit()
if state.game_client is not None:
    state.game_client.stop()
print("Окно закрыто.")
