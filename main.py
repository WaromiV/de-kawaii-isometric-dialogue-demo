"""Isometric pixel-art dialogue demo with Disco-like skill checks.

Run:
    python main.py
"""

from __future__ import annotations

import math
import os
import random
import struct
import wave
from dataclasses import dataclass, field

import pygame

from narration_engine import NarrationEngine


# ---------------------------------------------------------------------------
# Core config
# ---------------------------------------------------------------------------

INTERNAL_SIZE = (640, 360)
SCALE = 2
WINDOW_SIZE = (INTERNAL_SIZE[0] * SCALE, INTERNAL_SIZE[1] * SCALE)
FPS = 60

TILE_W = 32
TILE_H = 16
MAP_W = 20
MAP_H = 20
MAP_ORIGIN = (INTERNAL_SIZE[0] // 2, 32)

SKILL_GRID = [
    ["Charm", "Empathy", "Logic"],
    ["Intimidation", "Deception", "Composure"],
    ["Luck", "Streetwise", "Instinct"],
]

FONT_DIR = os.path.join("assets", "fonts")
PIXEL_FONT_REGULAR = os.path.join(FONT_DIR, "Silkscreen-Regular.ttf")
PIXEL_FONT_BOLD = os.path.join(FONT_DIR, "Silkscreen-Bold.ttf")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
CHARACTER_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
NARRATOR_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def iso_to_screen(
    tx: float,
    ty: float,
    origin: tuple[int, int] = MAP_ORIGIN,
    tile_w: int = TILE_W,
    tile_h: int = TILE_H,
) -> tuple[int, int]:
    sx = origin[0] + int((tx - ty) * (tile_w / 2))
    sy = origin[1] + int((tx + ty) * (tile_h / 2))
    return sx, sy


def wrapped_lines(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def load_pixel_font(size: int, bold: bool = False) -> pygame.font.Font:
    path = PIXEL_FONT_BOLD if bold else PIXEL_FONT_REGULAR
    if os.path.exists(path):
        return pygame.font.Font(path, size)
    return pygame.font.SysFont("consolas", size, bold=bold)


# ---------------------------------------------------------------------------
# Runtime audio generation
# ---------------------------------------------------------------------------


def _write_stereo_wav(
    path: str, duration: float, sampler, sample_rate: int = 22050
) -> None:
    frames = bytearray()
    total = int(duration * sample_rate)
    for i in range(total):
        t = i / sample_rate
        sample = clamp(float(sampler(t)), -1.0, 1.0)
        value = int(sample * 32767)
        frames += struct.pack("<hh", value, value)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)


def ensure_audio_assets() -> dict[str, str]:
    audio_dir = os.path.join("assets", "audio")
    os.makedirs(audio_dir, exist_ok=True)

    ambient = os.path.join(audio_dir, "at_the_end_of_hope_loop.wav")
    roll = os.path.join(audio_dir, "roll.wav")
    click = os.path.join(audio_dir, "ui_click.wav")
    success = os.path.join(audio_dir, "success.wav")
    fail = os.path.join(audio_dir, "fail.wav")

    if not os.path.exists(ambient):
        ambient = ""

    if not os.path.exists(roll):

        def roll_sampler(t: float) -> float:
            env = max(0.0, 1.0 - t / 0.35)
            tone = math.sin(2 * math.pi * (140 + 110 * t) * t)
            rattle = 0.35 * math.sin(2 * math.pi * 980.0 * t)
            return env * (0.45 * tone + rattle)

        _write_stereo_wav(roll, duration=0.35, sampler=roll_sampler)

    if not os.path.exists(click):

        def click_sampler(t: float) -> float:
            env = max(0.0, 1.0 - t / 0.09)
            return env * math.sin(2 * math.pi * 680.0 * t)

        _write_stereo_wav(click, duration=0.09, sampler=click_sampler)

    if not os.path.exists(success):

        def success_sampler(t: float) -> float:
            env = max(0.0, 1.0 - t / 0.22)
            a = math.sin(2 * math.pi * 440.0 * t)
            b = math.sin(2 * math.pi * 659.25 * t)
            return env * (0.35 * a + 0.3 * b)

        _write_stereo_wav(success, duration=0.22, sampler=success_sampler)

    if not os.path.exists(fail):

        def fail_sampler(t: float) -> float:
            env = max(0.0, 1.0 - t / 0.25)
            return env * (0.45 * math.sin(2 * math.pi * 170.0 * t))

        _write_stereo_wav(fail, duration=0.25, sampler=fail_sampler)

    return {
        "ambient": ambient,
        "roll": roll,
        "click": click,
        "success": success,
        "fail": fail,
    }


class AudioBank:
    def __init__(self) -> None:
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.paths = ensure_audio_assets()

        try:
            pygame.mixer.pre_init(22050, -16, 2, 512)
            pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False
            return

        try:
            self.sounds["roll"] = pygame.mixer.Sound(self.paths["roll"])
            self.sounds["click"] = pygame.mixer.Sound(self.paths["click"])
            self.sounds["success"] = pygame.mixer.Sound(self.paths["success"])
            self.sounds["fail"] = pygame.mixer.Sound(self.paths["fail"])
            self.sounds["roll"].set_volume(0.35)
            self.sounds["click"].set_volume(0.35)
            self.sounds["success"].set_volume(0.5)
            self.sounds["fail"].set_volume(0.5)
        except pygame.error:
            self.enabled = False
            return

        music_path = self.paths["ambient"]
        if music_path:
            try:
                pygame.mixer.music.load(music_path)
                pygame.mixer.music.set_volume(0.28)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound:
            sound.play()


# ---------------------------------------------------------------------------
# Pixel-art assets (generated surfaces)
# ---------------------------------------------------------------------------


class PixelAssets:
    def __init__(self) -> None:
        self.tiles: dict[str, pygame.Surface] = {}
        self.props: dict[str, pygame.Surface] = {}
        self.characters: dict[str, dict[str, dict[str, list[pygame.Surface]]]] = {}
        self._build_tiles()
        self._build_props()
        self._build_characters()

    @staticmethod
    def _iso_tile(
        top: tuple[int, int, int], outline: tuple[int, int, int]
    ) -> pygame.Surface:
        surf = pygame.Surface((TILE_W, TILE_H), pygame.SRCALPHA)
        diamond = [
            (TILE_W // 2, 0),
            (TILE_W - 1, TILE_H // 2),
            (TILE_W // 2, TILE_H - 1),
            (0, TILE_H // 2),
        ]
        pygame.draw.polygon(surf, top, diamond)
        pygame.draw.polygon(surf, outline, diamond, 1)
        return surf

    def _build_tiles(self) -> None:
        grass = self._iso_tile((73, 136, 84), (38, 73, 43))
        for _ in range(28):
            x = random.randint(4, TILE_W - 5)
            y = random.randint(3, TILE_H - 4)
            grass.set_at((x, y), (86, 164, 99, 255))
        self.tiles["grass"] = grass

        road = self._iso_tile((130, 111, 89), (68, 57, 42))
        for _ in range(32):
            x = random.randint(3, TILE_W - 4)
            y = random.randint(2, TILE_H - 3)
            road.set_at((x, y), (150, 129, 102, 255))
        self.tiles["road"] = road

        stone = self._iso_tile((121, 127, 144), (71, 76, 90))
        for _ in range(30):
            x = random.randint(3, TILE_W - 4)
            y = random.randint(2, TILE_H - 3)
            stone.set_at((x, y), (145, 151, 169, 255))
        self.tiles["stone"] = stone

        water = self._iso_tile((63, 102, 151), (35, 59, 90))
        for _ in range(26):
            x = random.randint(4, TILE_W - 5)
            y = random.randint(3, TILE_H - 4)
            water.set_at((x, y), (92, 140, 195, 255))
        self.tiles["water"] = water

    def _build_props(self) -> None:
        self.props["crate"] = self._make_crate()
        self.props["barrel"] = self._make_barrel()
        self.props["lamp"] = self._make_lamp()
        self.props["bench"] = self._make_bench()
        self.props["sign"] = self._make_sign()
        self.props["bush"] = self._make_bush()
        self.props["trash"] = self._make_trash_bag()
        self.props["post"] = self._make_postbox()
        self.props["stall"] = self._make_stall()

    def _make_crate(self) -> pygame.Surface:
        surf = pygame.Surface((26, 26), pygame.SRCALPHA)
        top = [(13, 4), (22, 9), (13, 14), (4, 9)]
        left = [(4, 9), (13, 14), (13, 22), (4, 16)]
        right = [(22, 9), (13, 14), (13, 22), (22, 16)]
        pygame.draw.polygon(surf, (158, 114, 70), top)
        pygame.draw.polygon(surf, (117, 82, 47), left)
        pygame.draw.polygon(surf, (94, 65, 36), right)
        pygame.draw.lines(surf, (82, 53, 28), True, top, 1)
        pygame.draw.lines(surf, (82, 53, 28), True, left, 1)
        pygame.draw.lines(surf, (82, 53, 28), True, right, 1)
        return surf

    def _make_barrel(self) -> pygame.Surface:
        surf = pygame.Surface((22, 28), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (118, 78, 48), (4, 2, 14, 8))
        pygame.draw.rect(surf, (103, 67, 41), (4, 6, 14, 14))
        pygame.draw.ellipse(surf, (85, 56, 35), (4, 16, 14, 8))
        pygame.draw.line(surf, (55, 35, 22), (4, 9), (18, 9), 1)
        pygame.draw.line(surf, (55, 35, 22), (4, 14), (18, 14), 1)
        return surf

    def _make_lamp(self) -> pygame.Surface:
        surf = pygame.Surface((24, 46), pygame.SRCALPHA)
        pygame.draw.rect(surf, (62, 58, 71), (11, 12, 2, 24))
        pygame.draw.circle(surf, (255, 230, 150), (12, 10), 4)
        pygame.draw.rect(surf, (73, 67, 82), (8, 36, 8, 4))
        pygame.draw.ellipse(surf, (255, 236, 162, 80), (1, 4, 22, 16))
        return surf

    def _make_bench(self) -> pygame.Surface:
        surf = pygame.Surface((34, 24), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (127, 83, 55), [(4, 11), (17, 5), (30, 11), (17, 17)])
        pygame.draw.rect(surf, (92, 58, 36), (8, 16, 3, 6))
        pygame.draw.rect(surf, (92, 58, 36), (23, 16, 3, 6))
        return surf

    def _make_sign(self) -> pygame.Surface:
        surf = pygame.Surface((24, 38), pygame.SRCALPHA)
        pygame.draw.rect(surf, (84, 61, 42), (11, 14, 2, 20))
        pygame.draw.polygon(surf, (201, 169, 116), [(4, 8), (20, 8), (20, 16), (4, 16)])
        pygame.draw.rect(surf, (82, 60, 42), (4, 8, 16, 8), 1)
        return surf

    def _make_bush(self) -> pygame.Surface:
        surf = pygame.Surface((30, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (43, 105, 53), (2, 4, 26, 14))
        pygame.draw.ellipse(surf, (58, 131, 71), (5, 2, 12, 10))
        pygame.draw.ellipse(surf, (58, 131, 71), (14, 5, 10, 8))
        return surf

    def _make_trash_bag(self) -> pygame.Surface:
        surf = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (53, 55, 66), (4, 8, 16, 10))
        pygame.draw.polygon(surf, (65, 67, 81), [(10, 9), (14, 9), (12, 4)])
        return surf

    def _make_postbox(self) -> pygame.Surface:
        surf = pygame.Surface((20, 30), pygame.SRCALPHA)
        pygame.draw.rect(surf, (148, 53, 64), (5, 8, 10, 14))
        pygame.draw.rect(surf, (91, 29, 35), (7, 12, 6, 2))
        pygame.draw.rect(surf, (73, 47, 51), (9, 22, 2, 6))
        return surf

    def _make_stall(self) -> pygame.Surface:
        surf = pygame.Surface((64, 58), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (117, 53, 75), [(8, 16), (32, 4), (56, 16), (32, 28)])
        pygame.draw.polygon(surf, (96, 44, 61), [(8, 16), (32, 28), (32, 42), (8, 30)])
        pygame.draw.polygon(
            surf, (78, 34, 51), [(56, 16), (32, 28), (32, 42), (56, 30)]
        )
        pygame.draw.rect(surf, (92, 66, 49), (14, 30, 36, 14))
        pygame.draw.rect(surf, (67, 47, 33), (14, 44, 36, 10))
        return surf

    def _build_characters(self) -> None:
        self.characters["player"] = self._make_character_set(
            skin=(240, 207, 173),
            coat=(78, 149, 175),
            accent=(248, 161, 120),
            hair=(69, 61, 86),
            eye=(30, 37, 52),
        )
        self.characters["man"] = self._make_character_set(
            skin=(228, 194, 165),
            coat=(131, 91, 148),
            accent=(251, 195, 106),
            hair=(64, 48, 60),
            eye=(41, 31, 46),
        )

    @staticmethod
    def _set_px(
        surf: pygame.Surface, x: int, y: int, color: tuple[int, int, int]
    ) -> None:
        if 0 <= x < surf.get_width() and 0 <= y < surf.get_height():
            surf.set_at((x, y), (*color, 255))

    @staticmethod
    def _darken(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
        return (
            max(0, color[0] - amount),
            max(0, color[1] - amount),
            max(0, color[2] - amount),
        )

    def _draw_face(
        self,
        surf: pygame.Surface,
        head_x: int,
        direction: str,
        eye: tuple[int, int, int],
        eye_state: str,
        mouth_state: str,
        hair: tuple[int, int, int],
        blush: tuple[int, int, int],
        y_off: int = 0,
    ) -> None:
        front = 1 if direction in ("SE", "SW") else -1
        fx = head_x + front
        bx = head_x - front
        eye_y = 9 + y_off

        # eyebrows
        brow = self._darken(hair, 22)
        self._set_px(surf, fx, eye_y - 2, brow)
        self._set_px(surf, bx, eye_y - 2, brow)

        if eye_state == "blink":
            self._set_px(surf, fx - 1, eye_y, eye)
            self._set_px(surf, fx, eye_y, eye)
            self._set_px(surf, bx, eye_y, eye)
        elif eye_state == "half":
            self._set_px(surf, fx, eye_y, eye)
            self._set_px(surf, bx, eye_y, eye)
        else:
            self._set_px(surf, fx, eye_y, eye)
            dim_eye = self._darken(eye, 35)
            self._set_px(surf, bx, eye_y, dim_eye)

        # tiny blush dots keep the character expressive in low resolution.
        self._set_px(surf, head_x + front * 2, 11, blush)
        self._set_px(surf, head_x - front * 2, 11, blush)

        mouth_y = 12 + y_off
        mouth_col = self._darken(eye, 25)
        if mouth_state == "smile":
            self._set_px(surf, head_x - 1, mouth_y, mouth_col)
            self._set_px(surf, head_x, mouth_y + 1, mouth_col)
            self._set_px(surf, head_x + 1, mouth_y, mouth_col)
        elif mouth_state == "talk_open":
            self._set_px(surf, head_x, mouth_y, mouth_col)
            self._set_px(surf, head_x, mouth_y + 1, mouth_col)
        elif mouth_state == "talk_wide":
            self._set_px(surf, head_x - 1, mouth_y, mouth_col)
            self._set_px(surf, head_x, mouth_y, mouth_col)
            self._set_px(surf, head_x + 1, mouth_y, mouth_col)
        else:
            self._set_px(surf, head_x, mouth_y, mouth_col)

    def _compose_character_frame(
        self,
        direction: str,
        sway: int,
        step: int,
        skin: tuple[int, int, int],
        coat: tuple[int, int, int],
        accent: tuple[int, int, int],
        hair: tuple[int, int, int],
        eye: tuple[int, int, int],
        eye_state: str,
        mouth_state: str,
        body_bob: int = 0,
    ) -> pygame.Surface:
        surf = pygame.Surface((28, 42), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (0, 0, 0, 70), (7, 30, 14, 6))

        body_x = 12 + sway // 2
        leg_shift = -1 if step == 0 else 1
        y_off = body_bob

        pygame.draw.rect(surf, (45, 43, 56), (body_x - 3 + leg_shift, 24 + y_off, 2, 8))
        pygame.draw.rect(surf, (45, 43, 56), (body_x + 1 - leg_shift, 24 + y_off, 2, 8))
        pygame.draw.rect(surf, coat, (body_x - 4, 14 + y_off, 8, 11))
        pygame.draw.rect(surf, accent, (body_x - 3, 17 + y_off, 6, 2))

        # head + fringe
        pygame.draw.circle(surf, skin, (body_x, 10 + y_off), 4)
        pygame.draw.rect(surf, hair, (body_x - 4, 6 + y_off, 8, 2))
        pygame.draw.rect(surf, self._darken(hair, 18), (body_x - 4, 13 + y_off, 8, 1))

        self._draw_face(
            surf,
            head_x=body_x,
            direction=direction,
            eye=eye,
            eye_state=eye_state,
            mouth_state=mouth_state,
            hair=hair,
            blush=(243, 162, 171),
            y_off=y_off,
        )
        return surf

    def _make_character_set(
        self,
        skin: tuple[int, int, int],
        coat: tuple[int, int, int],
        accent: tuple[int, int, int],
        hair: tuple[int, int, int],
        eye: tuple[int, int, int],
    ) -> dict[str, dict[str, list[pygame.Surface]]]:
        directions = {"NE": 1, "NW": -1, "SE": 2, "SW": -2}
        frames: dict[str, dict[str, list[pygame.Surface]]] = {}

        idle_pattern = [
            ("open", "neutral"),
            ("open", "neutral"),
            ("open", "neutral"),
            ("half", "neutral"),
            ("blink", "neutral"),
            ("half", "neutral"),
            ("open", "smile"),
            ("open", "neutral"),
        ]
        talk_pattern = [
            ("open", "talk_open"),
            ("open", "talk_wide"),
            ("half", "talk_open"),
            ("open", "neutral"),
        ]

        for direction, sway in directions.items():
            walk_frames = [
                self._compose_character_frame(
                    direction,
                    sway,
                    step=0,
                    skin=skin,
                    coat=coat,
                    accent=accent,
                    hair=hair,
                    eye=eye,
                    eye_state="open",
                    mouth_state="neutral",
                ),
                self._compose_character_frame(
                    direction,
                    sway,
                    step=1,
                    skin=skin,
                    coat=coat,
                    accent=accent,
                    hair=hair,
                    eye=eye,
                    eye_state="open",
                    mouth_state="smile",
                ),
            ]

            idle_frames = [
                self._compose_character_frame(
                    direction,
                    sway,
                    step=0,
                    skin=skin,
                    coat=coat,
                    accent=accent,
                    hair=hair,
                    eye=eye,
                    eye_state=eye_state,
                    mouth_state=mouth_state,
                )
                for eye_state, mouth_state in idle_pattern
            ]

            talk_frames = [
                self._compose_character_frame(
                    direction,
                    sway,
                    step=i % 2,
                    skin=skin,
                    coat=coat,
                    accent=accent,
                    hair=hair,
                    eye=eye,
                    eye_state=eye_state,
                    mouth_state=mouth_state,
                    body_bob=-1 if i % 2 == 0 else 0,
                )
                for i, (eye_state, mouth_state) in enumerate(talk_pattern)
            ]

            frames[direction] = {
                "walk": walk_frames,
                "idle": idle_frames,
                "talk": talk_frames,
            }
        return frames


# ---------------------------------------------------------------------------
# Skill state + UI
# ---------------------------------------------------------------------------


class SkillState:
    def __init__(self) -> None:
        self.max_points_per_skill = 4
        self.unspent_points = 6
        self.values = {name: 1 for row in SKILL_GRID for name in row}

    def increase(self, skill: str) -> bool:
        if self.unspent_points <= 0:
            return False
        if self.values[skill] >= self.max_points_per_skill:
            return False
        self.values[skill] += 1
        self.unspent_points -= 1
        return True


class SkillMenuUI:
    def __init__(self) -> None:
        self.is_open = False
        self.last_buttons: list[tuple[str, pygame.Rect]] = []
        self.panel_rect = pygame.Rect(48, 30, 544, 300)

    def toggle(self) -> None:
        self.is_open = not self.is_open

    def close(self) -> None:
        self.is_open = False

    def handle_click(self, pos: tuple[int, int], state: SkillState) -> bool:
        for skill, rect in self.last_buttons:
            if rect.collidepoint(pos):
                return state.increase(skill)
        return False

    def draw(
        self,
        surf: pygame.Surface,
        fonts: dict[str, pygame.font.Font],
        state: SkillState,
    ) -> None:
        if not self.is_open:
            return

        overlay = pygame.Surface(INTERNAL_SIZE, pygame.SRCALPHA)
        overlay.fill((8, 9, 16, 170))
        surf.blit(overlay, (0, 0))

        pygame.draw.rect(surf, (31, 34, 52), self.panel_rect, border_radius=8)
        pygame.draw.rect(surf, (108, 113, 158), self.panel_rect, 2, border_radius=8)

        title = fonts["title"].render("Skill Grid [O to close]", False, (240, 243, 255))
        surf.blit(title, (self.panel_rect.x + 16, self.panel_rect.y + 12))

        pts = fonts["body"].render(
            f"Unspent points: {state.unspent_points}", False, (248, 216, 138)
        )
        surf.blit(pts, (self.panel_rect.x + 16, self.panel_rect.y + 38))

        self.last_buttons.clear()
        cell_w = 165
        cell_h = 67
        gap = 8
        base_x = self.panel_rect.x + 16
        base_y = self.panel_rect.y + 64

        for r, row in enumerate(SKILL_GRID):
            for c, skill in enumerate(row):
                x = base_x + c * (cell_w + gap)
                y = base_y + r * (cell_h + gap)
                rect = pygame.Rect(x, y, cell_w, cell_h)
                pygame.draw.rect(surf, (42, 47, 70), rect, border_radius=6)
                pygame.draw.rect(surf, (92, 98, 145), rect, 1, border_radius=6)

                val = state.values[skill]
                text = fonts["body"].render(skill, False, (225, 230, 255))
                surf.blit(text, (x + 8, y + 8))

                meter_text = fonts["small"].render(
                    f"{val}/{state.max_points_per_skill}", False, (180, 212, 255)
                )
                surf.blit(meter_text, (x + 8, y + 28))

                # tiny pip meter
                for i in range(state.max_points_per_skill):
                    pip_col = (107, 223, 158) if i < val else (79, 84, 109)
                    pygame.draw.rect(
                        surf,
                        pip_col,
                        pygame.Rect(x + 8 + i * 18, y + 47, 14, 8),
                        border_radius=2,
                    )

                plus_rect = pygame.Rect(x + cell_w - 26, y + 22, 18, 18)
                can_add = state.unspent_points > 0 and val < state.max_points_per_skill
                plus_col = (102, 198, 130) if can_add else (91, 93, 110)
                pygame.draw.rect(surf, plus_col, plus_rect, border_radius=3)
                pygame.draw.rect(surf, (28, 31, 41), plus_rect, 1, border_radius=3)
                plus = fonts["body"].render(
                    "+", False, (16, 24, 20) if can_add else (40, 44, 52)
                )
                surf.blit(plus, (plus_rect.x + 4, plus_rect.y - 2))

                self.last_buttons.append((skill, plus_rect))


# ---------------------------------------------------------------------------
# Dialogue + checks
# ---------------------------------------------------------------------------


@dataclass
class PassiveCheck:
    check_id: str
    skill: str
    dc: int
    line: str
    set_flag: str | None = None


@dataclass
class ActiveCheck:
    check_id: str
    skill: str
    dc: int
    kind: str  # "white" or "red"
    modifiers: list[tuple[str, int, str | None]] = field(default_factory=list)


@dataclass
class DialogueOption:
    text: str
    condition_flag: str | None = None
    check: ActiveCheck | None = None
    target: str | None = None
    success_target: str | None = None
    fail_target: str | None = None
    success_money: int = 0
    fail_money: int = 0
    success_flags: tuple[str, ...] = ()
    fail_flags: tuple[str, ...] = ()
    success_log: str = ""
    fail_log: str = ""


@dataclass
class DialogueNode:
    node_id: str
    speaker: str
    text: str
    passives: list[PassiveCheck] = field(default_factory=list)
    options: list[DialogueOption] = field(default_factory=list)


@dataclass
class OptionRenderState:
    option: DialogueOption
    rect: pygame.Rect
    enabled: bool
    reason: str = ""


class DialogueSystem:
    def __init__(
        self,
        skills: SkillState,
        audio: AudioBank,
        narration: NarrationEngine | None = None,
    ) -> None:
        self.skills = skills
        self.audio = audio
        self.narration = narration

        self.nodes = self._build_nodes()
        self.current_node_id = "intro"
        self.flags: set[str] = set()
        self.seen_passives: set[str] = set()
        self.current_passive_lines: list[str] = []

        self.white_locks: dict[str, tuple[str, int]] = {}
        self.red_used: set[str] = set()

        self.is_active = False
        self.finished = False
        self.money = 0
        self.status_log = ""
        self.final_line = ""

        self.roll_state: dict | None = None
        self.rendered_options: list[OptionRenderState] = []
        self.roll_flash_color: tuple[int, int, int] | None = None
        self.roll_flash_started = 0
        self.roll_flash_duration_ms = 420
        self.pending_status_voice: str | None = None
        self.intro_voice_played = False

    def reset(self) -> None:
        self.current_node_id = "intro"
        self.flags.clear()
        self.seen_passives.clear()
        self.current_passive_lines.clear()
        self.white_locks.clear()
        self.red_used.clear()
        self.is_active = False
        self.finished = False
        self.money = 0
        self.status_log = ""
        self.final_line = ""
        self.roll_state = None
        self.rendered_options.clear()
        self.roll_flash_color = None
        self.roll_flash_started = 0
        self.pending_status_voice = None
        self.intro_voice_played = False

    def _queue_character_line(self, text: str) -> None:
        if self.narration is not None:
            self.narration.queue_character(text)

    def _queue_narrator_line(self, text: str) -> None:
        if self.narration is not None:
            self.narration.queue_narrator(text)

    def start(self) -> None:
        if self.finished:
            return
        self.is_active = True
        self._enter_node(self.current_node_id)

    def close(self) -> None:
        self.is_active = False

    def get_roll_vignette(self) -> tuple[tuple[int, int, int], float] | None:
        if self.roll_flash_color is None:
            return None
        elapsed = pygame.time.get_ticks() - self.roll_flash_started
        if elapsed >= self.roll_flash_duration_ms:
            self.roll_flash_color = None
            return None
        intensity = 1.0 - (elapsed / self.roll_flash_duration_ms)
        return self.roll_flash_color, intensity

    def voiceover_manifest(self) -> tuple[list[str], list[str]]:
        character_lines: list[str] = []
        narrator_lines: list[str] = []

        for node in self.nodes.values():
            character_lines.append(node.text)
            for passive in node.passives:
                narrator_lines.append(f"[{passive.skill}] {passive.line}")
            for option in node.options:
                if option.success_log:
                    narrator_lines.append(option.success_log)
                if option.fail_log:
                    narrator_lines.append(option.fail_log)

        return character_lines, narrator_lines

    @property
    def current_node(self) -> DialogueNode:
        return self.nodes[self.current_node_id]

    def refresh_locks(self) -> None:
        to_remove = []
        for check_id, (skill, needed) in self.white_locks.items():
            if self.skills.values[skill] >= needed:
                to_remove.append(check_id)
        for check_id in to_remove:
            self.white_locks.pop(check_id, None)

    def _enter_node(self, node_id: str) -> None:
        self.current_node_id = node_id
        self.current_passive_lines.clear()
        node = self.current_node
        should_voice = not (node_id == "intro" and self.intro_voice_played)
        if should_voice:
            self._queue_character_line(node.text)
            if node_id == "intro":
                self.intro_voice_played = True

        if self.pending_status_voice:
            self._queue_narrator_line(self.pending_status_voice)
            self.pending_status_voice = None

        for p in node.passives:
            if p.check_id in self.seen_passives:
                continue
            self.seen_passives.add(p.check_id)
            score = self.skills.values[p.skill] + 6
            if score >= p.dc:
                passive_line = f"[{p.skill}] {p.line}"
                self.current_passive_lines.append(passive_line)
                self._queue_narrator_line(passive_line)
                if p.set_flag:
                    self.flags.add(p.set_flag)

    def _active_bonus(self, check: ActiveCheck) -> tuple[int, list[str]]:
        bonus = self.skills.values[check.skill]
        labels: list[str] = [f"{check.skill} {self.skills.values[check.skill]:+d}"]
        for label, value, required_flag in check.modifiers:
            if required_flag is None or required_flag in self.flags:
                bonus += value
                labels.append(f"{label} {value:+d}")
        return bonus, labels

    def _chance_percent(self, check: ActiveCheck) -> int:
        bonus, _ = self._active_bonus(check)
        successes = 0
        for d1 in range(1, 7):
            for d2 in range(1, 7):
                if d1 == 1 and d2 == 1:
                    pass
                elif d1 == 6 and d2 == 6:
                    successes += 1
                else:
                    if d1 + d2 + bonus >= check.dc:
                        successes += 1
        return round((successes / 36.0) * 100)

    def _is_option_enabled(self, option: DialogueOption) -> tuple[bool, str]:
        if option.condition_flag and option.condition_flag not in self.flags:
            return False, ""
        if option.check is None:
            return True, ""

        check = option.check
        if check.kind == "red" and check.check_id in self.red_used:
            return False, "red check already used"

        if check.kind == "white" and check.check_id in self.white_locks:
            skill, need = self.white_locks[check.check_id]
            if self.skills.values[skill] < need:
                return False, f"raise {skill} to {need}"
        return True, ""

    def _resolve_immediate(self, option: DialogueOption) -> None:
        self.money += option.success_money
        for flag in option.success_flags:
            self.flags.add(flag)
        if option.success_log:
            self.status_log = option.success_log
            self.final_line = option.success_log
            self.pending_status_voice = option.success_log
        target = option.target
        if target is None:
            if self.pending_status_voice:
                self._queue_narrator_line(self.pending_status_voice)
                self.pending_status_voice = None
            self.is_active = False
            self.finished = True
            return
        self._enter_node(target)

    def _start_roll(self, option: DialogueOption) -> None:
        check = option.check
        assert check is not None

        bonus, labels = self._active_bonus(check)
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)

        if d1 == 1 and d2 == 1:
            success = False
        elif d1 == 6 and d2 == 6:
            success = True
        else:
            success = d1 + d2 + bonus >= check.dc

        if check.kind == "red":
            self.red_used.add(check.check_id)

        self.roll_state = {
            "option": option,
            "check": check,
            "d1": d1,
            "d2": d2,
            "bonus": bonus,
            "mod_labels": labels,
            "total": d1 + d2 + bonus,
            "success": success,
            "started": pygame.time.get_ticks(),
            "done": False,
            "reveal_flash_emitted": False,
        }
        self.audio.play("roll")

    def _resolve_roll(self) -> None:
        assert self.roll_state is not None
        if self.roll_state["done"]:
            return

        option: DialogueOption = self.roll_state["option"]
        check: ActiveCheck = self.roll_state["check"]
        passed = bool(self.roll_state["success"])

        if passed:
            self.money += option.success_money
            for flag in option.success_flags:
                self.flags.add(flag)
            if option.success_log:
                self.status_log = option.success_log
                self.final_line = option.success_log
                self.pending_status_voice = option.success_log
            target = option.success_target
            self.audio.play("success")
        else:
            self.money += option.fail_money
            for flag in option.fail_flags:
                self.flags.add(flag)
            if option.fail_log:
                self.status_log = option.fail_log
                self.final_line = option.fail_log
                self.pending_status_voice = option.fail_log
            target = option.fail_target
            self.audio.play("fail")

            if check.kind == "white":
                needed = self.skills.values[check.skill] + 1
                self.white_locks[check.check_id] = (check.skill, needed)

        self.roll_state["done"] = True

        if target is None:
            if self.pending_status_voice:
                self._queue_narrator_line(self.pending_status_voice)
                self.pending_status_voice = None
            self.is_active = False
            self.finished = True
            return
        self._enter_node(target)

    def update(self) -> None:
        self.refresh_locks()
        if self.roll_state is None:
            return
        elapsed = pygame.time.get_ticks() - int(self.roll_state["started"])

        if elapsed >= 700 and not self.roll_state["reveal_flash_emitted"]:
            passed = bool(self.roll_state["success"])
            self.roll_flash_color = (96, 224, 148) if passed else (236, 88, 108)
            self.roll_flash_started = pygame.time.get_ticks()
            self.roll_state["reveal_flash_emitted"] = True

        if elapsed >= 1500:
            self._resolve_roll()
            self.roll_state = None

    def handle_key(self, event: pygame.event.Event) -> None:
        if not self.is_active or self.roll_state is not None:
            return
        if event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
            idx = event.key - pygame.K_1
            if idx < len(self.rendered_options):
                entry = self.rendered_options[idx]
                if entry.enabled:
                    if entry.option.check:
                        self._start_roll(entry.option)
                    else:
                        self._resolve_immediate(entry.option)

    def handle_click(self, pos: tuple[int, int]) -> None:
        if not self.is_active or self.roll_state is not None:
            return
        for entry in self.rendered_options:
            if entry.rect.collidepoint(pos) and entry.enabled:
                if entry.option.check:
                    self._start_roll(entry.option)
                else:
                    self._resolve_immediate(entry.option)
                break

    def draw(self, surf: pygame.Surface, fonts: dict[str, pygame.font.Font]) -> None:
        if not self.is_active:
            return

        panel = pygame.Rect(8, INTERNAL_SIZE[1] - 154, INTERNAL_SIZE[0] - 16, 146)
        pygame.draw.rect(surf, (23, 25, 39), panel, border_radius=8)
        pygame.draw.rect(surf, (100, 107, 148), panel, 2, border_radius=8)

        node = self.current_node
        title = fonts["body"].render(node.speaker, False, (246, 219, 164))
        surf.blit(title, (panel.x + 10, panel.y + 8))

        text_lines = wrapped_lines(node.text, fonts["small"], panel.width - 20)[:3]
        for i, line in enumerate(text_lines):
            txt = fonts["small"].render(line, False, (228, 232, 248))
            surf.blit(txt, (panel.x + 10, panel.y + 28 + i * 14))

        # Green narrator line appears directly after the current character reply.
        y_cursor = panel.y + 28 + len(text_lines) * 14 + 2
        if self.status_log:
            status_lines = wrapped_lines(
                self.status_log, fonts["small"], panel.width - 20
            )[:2]
            for line in status_lines:
                status = fonts["small"].render(line, False, (145, 236, 168))
                surf.blit(status, (panel.x + 10, y_cursor))
                y_cursor += 14
            y_cursor += 2

        for line in self.current_passive_lines[:2]:
            ptxt = fonts["small"].render(line, False, (141, 210, 255))
            surf.blit(ptxt, (panel.x + 10, y_cursor))
            y_cursor += 14

        self.rendered_options.clear()
        # Keep options 100px higher than the original placement.
        opt_y = panel.y + 70
        visible_options: list[DialogueOption] = []
        for opt in node.options:
            if opt.condition_flag and opt.condition_flag not in self.flags:
                continue
            visible_options.append(opt)

        for idx, option in enumerate(visible_options[:5]):
            enabled, reason = self._is_option_enabled(option)

            label = option.text
            if option.check is not None:
                chance = self._chance_percent(option.check)
                prefix = "W" if option.check.kind == "white" else "R"
                label = f"[{prefix}:{option.check.skill} {chance}%] {label}"
            if not enabled and reason:
                label = f"{label} ({reason})"

            color = (220, 225, 245) if enabled else (132, 136, 157)
            if option.check and option.check.kind == "red":
                color = (240, 168, 176) if enabled else (129, 98, 103)
            if option.check and option.check.kind == "white":
                color = (168, 214, 255) if enabled else (103, 125, 144)

            rendered = fonts["small"].render(f"{idx + 1}. {label}", False, color)
            rect = rendered.get_rect(topleft=(panel.x + 10, opt_y + idx * 14))
            hover_rect = pygame.Rect(
                panel.x + 8, opt_y + idx * 14 - 1, panel.width - 16, 13
            )
            if enabled:
                pygame.draw.rect(surf, (44, 48, 68), hover_rect, border_radius=3)
            surf.blit(rendered, rect.topleft)

            self.rendered_options.append(
                OptionRenderState(
                    option=option, rect=hover_rect, enabled=enabled, reason=reason
                )
            )

        if self.roll_state is not None:
            self._draw_roll_popup(surf, fonts)

    def _draw_roll_popup(
        self, surf: pygame.Surface, fonts: dict[str, pygame.font.Font]
    ) -> None:
        assert self.roll_state is not None
        check: ActiveCheck = self.roll_state["check"]
        elapsed = pygame.time.get_ticks() - int(self.roll_state["started"])

        box = pygame.Rect(168, 76, 304, 188)
        pygame.draw.rect(surf, (16, 18, 29), box, border_radius=8)
        pygame.draw.rect(surf, (125, 131, 179), box, 2, border_radius=8)

        ttl = fonts["title"].render(f"{check.skill} check", False, (236, 240, 255))
        surf.blit(ttl, (box.x + 12, box.y + 10))
        kind_col = (151, 221, 255) if check.kind == "white" else (255, 170, 181)
        kind = fonts["small"].render(check.kind.upper(), False, kind_col)
        surf.blit(kind, (box.right - 66, box.y + 14))

        rolling = elapsed < 700
        if rolling:
            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            total = d1 + d2 + self.roll_state["bonus"]
            passed: bool | None = None
        else:
            d1 = int(self.roll_state["d1"])
            d2 = int(self.roll_state["d2"])
            total = int(self.roll_state["total"])
            passed = bool(self.roll_state["success"])

        die_glow = 0.0 if rolling else max(0.0, 1.0 - (elapsed - 700) / 220.0)
        if passed is True:
            die_border = (110, 214, 142)
            die_glow_col = (98, 234, 142)
        elif passed is False:
            die_border = (234, 114, 132)
            die_glow_col = (244, 94, 118)
        else:
            die_border = (164, 171, 203)
            die_glow_col = (172, 183, 222)

        die1_rect = pygame.Rect(box.x + 74, box.y + 42, 50, 50)
        die2_rect = pygame.Rect(box.x + 180, box.y + 42, 50, 50)
        self._draw_die(
            surf,
            die1_rect,
            d1,
            border_color=die_border,
            pip_color=(43, 47, 62),
            flash_color=die_glow_col,
            flash_strength=die_glow,
        )
        self._draw_die(
            surf,
            die2_rect,
            d2,
            border_color=die_border,
            pip_color=(43, 47, 62),
            flash_color=die_glow_col,
            flash_strength=die_glow,
        )

        if elapsed < 700:
            text = fonts["body"].render(
                f"Rolling... {d1} + {d2}", False, (232, 236, 255)
            )
            surf.blit(text, (box.x + 12, box.y + 102))
            sub = fonts["small"].render(
                f"total preview: {total} vs dc {check.dc}", False, (143, 153, 190)
            )
            surf.blit(sub, (box.x + 12, box.y + 118))
        else:
            text = fonts["body"].render(
                f"{d1} + {d2} + {self.roll_state['bonus']} = {total}",
                False,
                (236, 240, 255),
            )
            surf.blit(text, (box.x + 12, box.y + 102))

            verdict_col = (130, 235, 159) if passed else (255, 138, 151)
            verdict = fonts["title"].render(
                "PASS" if passed else "FAIL", False, verdict_col
            )
            surf.blit(verdict, (box.x + 12, box.y + 122))

            dc_text = fonts["small"].render(
                f"Difficulty: {check.dc}", False, (160, 170, 207)
            )
            surf.blit(dc_text, (box.x + 12, box.y + 142))

        mods = self.roll_state["mod_labels"]
        for i, label in enumerate(mods[:3]):
            mtxt = fonts["small"].render(label, False, (167, 178, 224))
            surf.blit(mtxt, (box.x + 148, box.y + 104 + i * 12))

    @staticmethod
    def _draw_die(
        surf: pygame.Surface,
        rect: pygame.Rect,
        value: int,
        border_color: tuple[int, int, int],
        pip_color: tuple[int, int, int],
        flash_color: tuple[int, int, int],
        flash_strength: float,
    ) -> None:
        if flash_strength > 0.0:
            glow_pad = 14
            glow = pygame.Surface(
                (rect.width + glow_pad * 2, rect.height + glow_pad * 2), pygame.SRCALPHA
            )
            alpha = int(110 * flash_strength)
            pygame.draw.rect(
                glow,
                (*flash_color, alpha),
                pygame.Rect(5, 5, glow.get_width() - 10, glow.get_height() - 10),
                border_radius=10,
                width=7,
            )
            surf.blit(glow, (rect.x - glow_pad, rect.y - glow_pad))

        pygame.draw.rect(surf, (244, 247, 255), rect, border_radius=6)
        pygame.draw.rect(surf, border_color, rect, 2, border_radius=6)

        points = {
            1: [(0.5, 0.5)],
            2: [(0.3, 0.3), (0.7, 0.7)],
            3: [(0.3, 0.3), (0.5, 0.5), (0.7, 0.7)],
            4: [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)],
            5: [(0.3, 0.3), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.7, 0.7)],
            6: [
                (0.3, 0.3),
                (0.3, 0.5),
                (0.3, 0.7),
                (0.7, 0.3),
                (0.7, 0.5),
                (0.7, 0.7),
            ],
        }
        radius = 3
        for px, py in points.get(value, points[1]):
            cx = rect.x + int(rect.width * px)
            cy = rect.y + int(rect.height * py)
            pygame.draw.circle(surf, pip_color, (cx, cy), radius)

    def _build_nodes(self) -> dict[str, DialogueNode]:
        return {
            "intro": DialogueNode(
                node_id="intro",
                speaker="Miro, the man under the stall light",
                text=(
                    '"Detective. If you\'re here for money, everyone is. Make it fast before my luck turns."'
                ),
                passives=[
                    PassiveCheck(
                        check_id="p_empathy_intro",
                        skill="Empathy",
                        dc=8,
                        line="His hand trembles on the cigarette. He is scared, not smug.",
                        set_flag="fear_seen",
                    ),
                    PassiveCheck(
                        check_id="p_logic_intro",
                        skill="Logic",
                        dc=9,
                        line="A debt ledger peeks from his coat. He has numbers to hide.",
                        set_flag="ledger_seen",
                    ),
                    PassiveCheck(
                        check_id="p_instinct_intro",
                        skill="Instinct",
                        dc=10,
                        line="Push too hard and he will shout for dockers. Keep it precise.",
                    ),
                ],
                options=[
                    DialogueOption(
                        text='"I only need twenty reals. Quietly."',
                        check=ActiveCheck(
                            check_id="ask_polite",
                            skill="Charm",
                            dc=12,
                            kind="white",
                            modifiers=[("read his fear", 1, "fear_seen")],
                        ),
                        success_target="charm_success",
                        fail_target="charm_fail",
                        success_log="You soften your tone and he listens.",
                        fail_log="Your request sounds like a script he's heard before.",
                    ),
                    DialogueOption(
                        text='"You look cornered. Help me now, I help you later."',
                        check=ActiveCheck(
                            check_id="empathy_appeal",
                            skill="Empathy",
                            dc=11,
                            kind="white",
                            modifiers=[("fear in his voice", 1, "fear_seen")],
                        ),
                        success_target="empathy_success",
                        fail_target="empathy_fail",
                        success_log="You mirror his panic and the wall cracks.",
                        fail_log="He tightens up. Wrong note.",
                    ),
                    DialogueOption(
                        text='"I can bury one page of that ledger. You pay for that."',
                        condition_flag="ledger_seen",
                        check=ActiveCheck(
                            check_id="logic_offer",
                            skill="Logic",
                            dc=13,
                            kind="white",
                            modifiers=[("saw the ledger", 2, "ledger_seen")],
                        ),
                        success_target="logic_success",
                        fail_target="logic_fail",
                        success_log="His eyes cut to your badge, then to his coat pocket.",
                        fail_log="He calls your bluff on paper and ink.",
                    ),
                    DialogueOption(
                        text='"Pay me now, or I read your name out loud to the square."',
                        check=ActiveCheck(
                            check_id="intimidate_once",
                            skill="Intimidation",
                            dc=13,
                            kind="red",
                            modifiers=[("you read his fear", 1, "fear_seen")],
                        ),
                        success_target=None,
                        fail_target=None,
                        success_money=10,
                        fail_money=0,
                        success_log="He drops ten reals with a curse and tells you to vanish.",
                        fail_log="He shouts for backup and you walk before this turns into a scene.",
                    ),
                    DialogueOption(
                        text='"Coin toss. Heads: you pay thirty. Tails: I disappear."',
                        check=ActiveCheck(
                            check_id="coin_toss_once",
                            skill="Luck",
                            dc=14,
                            kind="red",
                        ),
                        success_target=None,
                        fail_target=None,
                        success_money=30,
                        fail_money=0,
                        success_log="Heads. He pays with shaking hands and bitter respect.",
                        fail_log="Tails. The city laughs softly behind you.",
                    ),
                    DialogueOption(
                        text='"Not today." (walk away)',
                        target=None,
                        success_log="You step back from the stall with empty pockets.",
                    ),
                ],
            ),
            "charm_success": DialogueNode(
                node_id="charm_success",
                speaker="Miro",
                text='"Fine. Twelve now. You get kindness, not miracles."',
                options=[
                    DialogueOption(
                        text="Take twelve reals and leave.",
                        target=None,
                        success_money=12,
                        success_log="You pocket twelve reals. Not victory, but rent breathes.",
                    ),
                    DialogueOption(
                        text='"Twelve is smoke. Make it twenty."',
                        check=ActiveCheck(
                            check_id="push_after_charm",
                            skill="Deception",
                            dc=12,
                            kind="white",
                            modifiers=[("momentum", 1, None)],
                        ),
                        success_target=None,
                        fail_target=None,
                        success_money=20,
                        fail_money=6,
                        success_log="You lean in and he folds. Twenty reals, counted twice.",
                        fail_log="He snorts and flicks six reals at your shoes.",
                    ),
                    DialogueOption(
                        text="Try another approach instead.", target="intro"
                    ),
                ],
            ),
            "charm_fail": DialogueNode(
                node_id="charm_fail",
                speaker="Miro",
                text='"That voice works on tourists, not me."',
                options=[
                    DialogueOption(text="Reset and pick a new angle.", target="intro"),
                ],
            ),
            "empathy_success": DialogueNode(
                node_id="empathy_success",
                speaker="Miro",
                text=(
                    '"My kid needs medicine. I\'m drowning already. Fifteen and we are strangers, yes?"'
                ),
                options=[
                    DialogueOption(
                        text="Take the fifteen and promise silence.",
                        target=None,
                        success_money=15,
                        success_flags=("trust_built",),
                        success_log="You leave with fifteen and a promise you might keep.",
                    ),
                    DialogueOption(
                        text='"Eighteen and I forget your face."',
                        check=ActiveCheck(
                            check_id="empathy_push",
                            skill="Charm",
                            dc=13,
                            kind="white",
                            modifiers=[("already opened up", 1, None)],
                        ),
                        success_target=None,
                        fail_target=None,
                        success_money=18,
                        fail_money=10,
                        success_log="You squeeze a little harder: eighteen reals.",
                        fail_log="He recoils. Ten reals and the door shuts.",
                    ),
                    DialogueOption(text="Back out and rethink.", target="intro"),
                ],
            ),
            "empathy_fail": DialogueNode(
                node_id="empathy_fail",
                speaker="Miro",
                text='"Don\'t pretend you know me."',
                options=[
                    DialogueOption(text="Try a different tactic.", target="intro"),
                ],
            ),
            "logic_success": DialogueNode(
                node_id="logic_success",
                speaker="Miro",
                text=(
                    '"You read too much, detective. Eighteen for your silence, then we are done."'
                ),
                options=[
                    DialogueOption(
                        text="Accept the eighteen.",
                        target=None,
                        success_money=18,
                        success_log="You trade quiet for eighteen clean notes.",
                    ),
                    DialogueOption(
                        text='"Twenty-five, and I burn the page in my head."',
                        check=ActiveCheck(
                            check_id="logic_overreach",
                            skill="Deception",
                            dc=14,
                            kind="red",
                        ),
                        success_target=None,
                        fail_target=None,
                        success_money=25,
                        fail_money=8,
                        success_log="He caves under pressure. Twenty-five bought in fear.",
                        fail_log="You overplay it. He throws eight and spits on your shoes.",
                    ),
                    DialogueOption(text="Withdraw and regroup.", target="intro"),
                ],
            ),
            "logic_fail": DialogueNode(
                node_id="logic_fail",
                speaker="Miro",
                text='"You bluff like a bookkeeper."',
                options=[
                    DialogueOption(text="Return to the conversation.", target="intro")
                ],
            ),
        }


# ---------------------------------------------------------------------------
# World state
# ---------------------------------------------------------------------------


@dataclass
class PropInstance:
    key: str
    x: int
    y: int
    block: bool = False


class World:
    def __init__(self, assets: PixelAssets) -> None:
        self.assets = assets
        self.tiles = [["grass" for _ in range(MAP_W)] for _ in range(MAP_H)]
        self.blocked: set[tuple[int, int]] = set()
        self.props: list[PropInstance] = []
        self._scaled_cache: dict[tuple[int, int], pygame.Surface] = {}

        self.player_x = 9.0
        self.player_y = 13.0
        self.player_facing = "NE"
        self.player_anim_clock = 0.0
        self.player_is_moving = False

        self.npc_x = 10.5
        self.npc_y = 9.3
        self.npc_rect = pygame.Rect(0, 0, 1, 1)

        self._build_map()
        self._place_props()

    def reset(self) -> None:
        self.player_x = 9.0
        self.player_y = 13.0
        self.player_facing = "NE"
        self.player_anim_clock = 0.0
        self.player_is_moving = False

    def _build_map(self) -> None:
        for y in range(MAP_H):
            for x in range(MAP_W):
                if abs(x - 10) <= 1 or abs(y - 10) <= 1:
                    self.tiles[y][x] = "road"
                if 8 <= x <= 12 and 8 <= y <= 12:
                    self.tiles[y][x] = "stone"

        # water edges for atmosphere
        for y in range(0, 4):
            for x in range(0, 5):
                if x + y < 5:
                    self.tiles[y][x] = "water"
                    self.blocked.add((x, y))
        for y in range(MAP_H - 4, MAP_H):
            for x in range(MAP_W - 5, MAP_W):
                if (MAP_W - x - 1) + (MAP_H - y - 1) < 5:
                    self.tiles[y][x] = "water"
                    self.blocked.add((x, y))

    def _add_prop(self, key: str, x: int, y: int, block: bool = False) -> None:
        self.props.append(PropInstance(key=key, x=x, y=y, block=block))
        if block:
            self.blocked.add((x, y))

    def _place_props(self) -> None:
        random.seed(6)
        for x in (6, 8, 12, 14):
            self._add_prop("lamp", x, 10)
        for y in (7, 9, 11, 13):
            self._add_prop("lamp", 10, y)

        # central market detail near NPC
        self._add_prop("stall", 11, 9, block=True)
        self._add_prop("crate", 12, 9, block=True)
        self._add_prop("barrel", 10, 8, block=True)
        self._add_prop("post", 9, 9)
        self._add_prop("sign", 9, 10)
        self._add_prop("bench", 12, 11)

        # street dressing
        decoration = ["crate", "barrel", "bench", "trash", "bush", "sign", "post"]
        points = [
            (5, 7),
            (6, 12),
            (7, 14),
            (13, 6),
            (14, 8),
            (15, 10),
            (4, 11),
            (5, 13),
            (16, 12),
            (3, 9),
            (8, 5),
            (12, 15),
            (9, 15),
            (15, 14),
            (4, 6),
            (6, 5),
            (14, 5),
            (16, 8),
            (2, 12),
            (17, 11),
            (3, 14),
            (11, 16),
            (8, 16),
        ]
        for i, (x, y) in enumerate(points):
            key = decoration[i % len(decoration)]
            self._add_prop(
                key, x, y, block=key in {"crate", "barrel", "bench", "stall"}
            )

        # fluffy greenery patches
        for x, y in [(2, 5), (3, 6), (17, 6), (16, 5), (5, 16), (14, 16)]:
            self._add_prop("bush", x, y)

    def can_walk(self, x: float, y: float) -> bool:
        tx = int(round(x))
        ty = int(round(y))
        if tx < 0 or ty < 0 or tx >= MAP_W or ty >= MAP_H:
            return False
        if (tx, ty) in self.blocked:
            return False
        if self.tiles[ty][tx] == "water":
            return False
        return True

    def update_player(self, dt: float, move_vec: tuple[float, float]) -> None:
        vx, vy = move_vec
        speed = 2.8
        if vx == 0 and vy == 0:
            self.player_is_moving = False
            return

        self.player_is_moving = True

        # normalize
        mag = math.hypot(vx, vy)
        if mag > 0:
            vx /= mag
            vy /= mag

        nx = self.player_x + vx * speed * dt
        ny = self.player_y + vy * speed * dt

        if self.can_walk(nx, self.player_y):
            self.player_x = nx
        if self.can_walk(self.player_x, ny):
            self.player_y = ny

        self.player_x = clamp(self.player_x, 0.5, MAP_W - 1.5)
        self.player_y = clamp(self.player_y, 0.5, MAP_H - 1.5)

        self.player_anim_clock += dt * 9.0

        if abs(vx) >= abs(vy):
            self.player_facing = "SE" if vx > 0 else "NW"
        else:
            self.player_facing = "SW" if vy > 0 else "NE"

    def player_near_npc(self) -> bool:
        return math.hypot(self.player_x - self.npc_x, self.player_y - self.npc_y) < 1.6

    def _zoomed_surface(self, src: pygame.Surface, zoom: float) -> pygame.Surface:
        if abs(zoom - 1.0) < 0.001:
            return src

        zoom_key = int(round(zoom * 100))
        key = (id(src), zoom_key)
        cached = self._scaled_cache.get(key)
        if cached is not None:
            return cached

        width = max(1, int(round(src.get_width() * zoom)))
        height = max(1, int(round(src.get_height() * zoom)))
        scaled = pygame.transform.scale(src, (width, height))
        self._scaled_cache[key] = scaled
        return scaled

    def _camera_origin(self, zoom: float, tile_w: int, tile_h: int) -> tuple[int, int]:
        # Keep player centered to make zoom feel like camera movement.
        center_x = INTERNAL_SIZE[0] // 2
        center_y = INTERNAL_SIZE[1] // 2 + int(22 * zoom)
        px = int((self.player_x - self.player_y) * (tile_w / 2))
        py = int((self.player_x + self.player_y) * (tile_h / 2))
        return center_x - px, center_y - py

    def draw(
        self,
        surf: pygame.Surface,
        time_s: float,
        zoom: float = 1.0,
        npc_talking: bool = False,
    ) -> None:
        tile_w = max(4, int(round(TILE_W * zoom)))
        tile_h = max(2, int(round(TILE_H * zoom)))
        origin = self._camera_origin(zoom, tile_w, tile_h)

        # ground pass
        for y in range(MAP_H):
            for x in range(MAP_W):
                tile = self._zoomed_surface(self.assets.tiles[self.tiles[y][x]], zoom)
                sx, sy = iso_to_screen(x, y, origin, tile_w, tile_h)
                surf.blit(
                    tile, (sx - tile.get_width() // 2, sy - tile.get_height() // 2)
                )

        # renderables sorted by world y for depth
        renderables: list[tuple[float, pygame.Surface, tuple[int, int], str]] = []

        for prop in self.props:
            sprite = self._zoomed_surface(self.assets.props[prop.key], zoom)
            sx, sy = iso_to_screen(prop.x, prop.y, origin, tile_w, tile_h)
            px = sx - sprite.get_width() // 2
            py = sy - sprite.get_height() + tile_h // 2
            renderables.append((prop.y + 0.1, sprite, (px, py), "prop"))

        # npc
        npc_dir = "SW"
        npc_set = self.assets.characters["man"][npc_dir]
        if npc_talking:
            npc_cycle = npc_set["talk"]
            npc_src = npc_cycle[int(time_s * 10) % len(npc_cycle)]
        else:
            npc_cycle = npc_set["idle"]
            npc_src = npc_cycle[int(time_s * 7) % len(npc_cycle)]
        npc_sprite = self._zoomed_surface(npc_src, zoom)
        nsx, nsy = iso_to_screen(self.npc_x, self.npc_y, origin, tile_w, tile_h)
        npx = nsx - npc_sprite.get_width() // 2
        npy = nsy - npc_sprite.get_height() + tile_h // 2
        renderables.append((self.npc_y + 0.2, npc_sprite, (npx, npy), "npc"))
        self.npc_rect = pygame.Rect(
            npx, npy, npc_sprite.get_width(), npc_sprite.get_height()
        )

        # player
        player_set = self.assets.characters["player"][self.player_facing]
        if self.player_is_moving:
            walk_cycle = player_set["walk"]
            player_src = walk_cycle[int(self.player_anim_clock) % len(walk_cycle)]
        else:
            idle_cycle = player_set["idle"]
            player_src = idle_cycle[int(time_s * 7) % len(idle_cycle)]
        player_sprite = self._zoomed_surface(player_src, zoom)
        psx, psy = iso_to_screen(self.player_x, self.player_y, origin, tile_w, tile_h)
        ppx = psx - player_sprite.get_width() // 2
        ppy = psy - player_sprite.get_height() + tile_h // 2
        renderables.append((self.player_y + 0.2, player_sprite, (ppx, ppy), "player"))

        renderables.sort(key=lambda r: r[0])
        for _depth, sprite, pos, _kind in renderables:
            surf.blit(sprite, pos)


# ---------------------------------------------------------------------------
# Game shell
# ---------------------------------------------------------------------------


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Kawaii Horror Money Check Demo")

        self.window = pygame.display.set_mode(WINDOW_SIZE)
        self.canvas = pygame.Surface(INTERNAL_SIZE)
        self.clock = pygame.time.Clock()

        self.fonts = {
            "title": load_pixel_font(16, bold=True),
            "body": load_pixel_font(12),
            "small": load_pixel_font(10),
        }

        self.audio = AudioBank()
        self.narration = NarrationEngine(
            api_key=ELEVENLABS_API_KEY,
            character_voice_id=CHARACTER_VOICE_ID,
            narrator_voice_id=NARRATOR_VOICE_ID,
        )
        self.assets = PixelAssets()
        self.skills = SkillState()
        self.skill_menu = SkillMenuUI()
        self.dialogue = DialogueSystem(self.skills, self.audio, self.narration)
        self.world = World(self.assets)

        self.running = True
        self.has_opened_skills_once = False
        self.start_ticks = pygame.time.get_ticks()
        self.skill_button = pygame.Rect(INTERNAL_SIZE[0] - 132, 8, 120, 24)
        self.camera_zoom = 1.0
        self.camera_zoom_min = 0.75
        self.camera_zoom_max = 2.0
        self.camera_zoom_step = 0.1
        self.final_outcome_announced = False

    def reset_story(self) -> None:
        self.narration.clear()
        self.skills = SkillState()
        self.skill_menu = SkillMenuUI()
        self.dialogue = DialogueSystem(self.skills, self.audio, self.narration)
        self.world.reset()
        self.has_opened_skills_once = False
        self.start_ticks = pygame.time.get_ticks()
        self.final_outcome_announced = False

    def mouse_to_internal(self, pos: tuple[int, int]) -> tuple[int, int]:
        return pos[0] // SCALE, pos[1] // SCALE

    def _toggle_skill_menu(self) -> None:
        self.skill_menu.toggle()
        if self.skill_menu.is_open:
            self.has_opened_skills_once = True
        self.audio.play("click")

    def _change_zoom(self, direction: int) -> None:
        target = self.camera_zoom + direction * self.camera_zoom_step
        clamped = clamp(target, self.camera_zoom_min, self.camera_zoom_max)
        if abs(clamped - self.camera_zoom) > 0.0001:
            self.camera_zoom = clamped
            self.audio.play("click")

    def _npc_is_talking(self) -> bool:
        if not self.dialogue.is_active:
            return False
        speaker = self.dialogue.current_node.speaker
        return speaker.startswith("Miro")

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return

        if event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                self._change_zoom(1)
            elif event.y < 0:
                self._change_zoom(-1)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mpos = self.mouse_to_internal(event.pos)
            if self.skill_button.collidepoint(mpos):
                self._toggle_skill_menu()
                return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
                return
            if event.key == pygame.K_r and self.dialogue.finished:
                self.reset_story()
                return
            if event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                self._change_zoom(1)
                return
            if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                self._change_zoom(-1)
                return
            if event.key == pygame.K_o:
                self._toggle_skill_menu()
                return

        # Skill menu has top priority when open
        if self.skill_menu.is_open:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = self.skill_menu.handle_click(
                    self.mouse_to_internal(event.pos), self.skills
                )
                if clicked:
                    self.audio.play("click")
                    self.dialogue.refresh_locks()
            return

        # Dialogue input
        if self.dialogue.is_active:
            self.dialogue.handle_key(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.dialogue.handle_click(self.mouse_to_internal(event.pos))
            return

        if event.type == pygame.KEYDOWN:
            if (
                event.key in (pygame.K_e, pygame.K_SPACE)
                and self.world.player_near_npc()
                and not self.dialogue.finished
            ):
                self.dialogue.start()
                self.audio.play("click")

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mpos = self.mouse_to_internal(event.pos)
            if self.world.npc_rect.collidepoint(mpos) and not self.dialogue.finished:
                self.dialogue.start()
                self.audio.play("click")

    def update(self, dt: float) -> None:
        self.dialogue.update()
        self.narration.update()

        if self.dialogue.finished and not self.final_outcome_announced:
            mood, _mood_col = self._outcome_mood_line()
            self.narration.queue_narrator(mood)
            final_line = self.dialogue.final_line or "The conversation is over."
            self.narration.queue_narrator(final_line)
            self.final_outcome_announced = True

        move = (0.0, 0.0)
        if not self.skill_menu.is_open and not self.dialogue.is_active:
            keys = pygame.key.get_pressed()
            left = keys[pygame.K_LEFT] or keys[pygame.K_a]
            right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
            up = keys[pygame.K_UP] or keys[pygame.K_w]
            down = keys[pygame.K_DOWN] or keys[pygame.K_s]
            move = (float(right) - float(left), float(down) - float(up))

        self.world.update_player(dt, move)

    def _prefetch_voiceover_audio(self) -> None:
        character_lines, narrator_lines = self.dialogue.voiceover_manifest()
        narrator_lines.extend(
            [
                "Big score. Dirty victory.",
                "Enough to breathe for a night.",
                "Loose change and bruised pride.",
                "Empty pockets. The city wins this round.",
                "The conversation is over.",
            ]
        )
        self.narration.write_manifest(character_lines, narrator_lines)
        self.narration.prefetch_lines(character_lines, narrator_lines)

    def _outcome_mood_line(self) -> tuple[str, tuple[int, int, int]]:
        money = self.dialogue.money
        if money >= 20:
            return "Big score. Dirty victory.", (132, 235, 157)
        if money >= 12:
            return "Enough to breathe for a night.", (237, 220, 146)
        if money > 0:
            return "Loose change and bruised pride.", (242, 183, 140)
        return "Empty pockets. The city wins this round.", (247, 144, 157)

    def draw(self) -> None:
        t = (pygame.time.get_ticks() - self.start_ticks) / 1000.0

        # atmospheric gradient
        self.canvas.fill((16, 20, 32))
        for i in range(0, INTERNAL_SIZE[1], 2):
            blend = i / INTERNAL_SIZE[1]
            col = (
                int(18 + 20 * blend),
                int(22 + 15 * blend),
                int(33 + 14 * blend),
            )
            pygame.draw.line(self.canvas, col, (0, i), (INTERNAL_SIZE[0], i))

        self.world.draw(
            self.canvas,
            t,
            self.camera_zoom,
            npc_talking=self._npc_is_talking(),
        )
        self._draw_hud(t)
        self.dialogue.draw(self.canvas, self.fonts)
        self._draw_roll_outcome_vignette()
        self.skill_menu.draw(self.canvas, self.fonts, self.skills)

        if self.dialogue.finished:
            self._draw_end_overlay()

        scaled = pygame.transform.scale(self.canvas, WINDOW_SIZE)
        self.window.blit(scaled, (0, 0))
        pygame.display.flip()

    def _draw_roll_outcome_vignette(self) -> None:
        flash = self.dialogue.get_roll_vignette()
        if flash is None:
            return

        color, intensity = flash
        overlay = pygame.Surface(INTERNAL_SIZE, pygame.SRCALPHA)

        center_alpha = int(22 * intensity)
        edge_alpha = int(128 * intensity)
        overlay.fill((*color, center_alpha))

        layers = 7
        for i in range(layers):
            inset = i * 12
            rect = pygame.Rect(
                inset,
                inset,
                INTERNAL_SIZE[0] - inset * 2,
                INTERNAL_SIZE[1] - inset * 2,
            )
            if rect.width <= 0 or rect.height <= 0:
                break
            alpha = int(edge_alpha * (1.0 - i / layers))
            pygame.draw.rect(
                overlay,
                (*color, alpha),
                rect,
                width=10,
                border_radius=16,
            )

        self.canvas.blit(overlay, (0, 0))

    def _draw_hud(self, t: float) -> None:
        # top bar
        pygame.draw.rect(
            self.canvas, (11, 13, 22), pygame.Rect(0, 0, INTERNAL_SIZE[0], 32)
        )
        pygame.draw.line(self.canvas, (60, 66, 94), (0, 31), (INTERNAL_SIZE[0], 31), 1)

        objective = self.fonts["small"].render(
            "Objective: get money from Miro", False, (228, 233, 250)
        )
        self.canvas.blit(objective, (10, 10))

        money_text = self.fonts["body"].render(
            f"Money: {self.dialogue.money} reals", False, (248, 229, 140)
        )
        self.canvas.blit(money_text, (235, 9))

        zoom_text = self.fonts["small"].render(
            f"Zoom {self.camera_zoom:.2f}x  [+/-]", False, (196, 210, 248)
        )
        self.canvas.blit(zoom_text, (396, 11))

        # skill button
        pulse = int(30 * (0.5 + 0.5 * math.sin(t * 3.0)))
        btn_col = (80 + pulse // 3, 96 + pulse // 3, 132 + pulse // 2)
        pygame.draw.rect(self.canvas, btn_col, self.skill_button, border_radius=5)
        pygame.draw.rect(
            self.canvas, (34, 40, 61), self.skill_button, 1, border_radius=5
        )
        btn = self.fonts["body"].render("Skills [O]", False, (244, 246, 255))
        self.canvas.blit(btn, (self.skill_button.x + 18, self.skill_button.y + 5))

        # tutorial hint for opening skill menu
        if not self.has_opened_skills_once:
            alpha = int(140 + 100 * (0.5 + 0.5 * math.sin(t * 4.3)))
            hint = pygame.Surface((250, 32), pygame.SRCALPHA)
            hint.fill((20, 23, 35, alpha))
            pygame.draw.rect(
                hint, (120, 143, 205, alpha), hint.get_rect(), 1, border_radius=5
            )
            line1 = self.fonts["small"].render(
                "Press O or click Skills", False, (220, 232, 255)
            )
            line2 = self.fonts["small"].render(
                "to spend points and unlock white checks", False, (174, 196, 242)
            )
            hint.blit(line1, (8, 4))
            hint.blit(line2, (8, 16))
            centered_x = self.skill_button.centerx - hint.get_width() // 2
            hx = max(2, min(centered_x, INTERNAL_SIZE[0] - hint.get_width() - 2))
            hy = self.skill_button.bottom + 4
            self.canvas.blit(hint, (hx, hy))

        if (
            self.world.player_near_npc()
            and not self.dialogue.is_active
            and not self.dialogue.finished
        ):
            prompt = self.fonts["small"].render(
                "Press E or click Miro to talk", False, (239, 242, 255)
            )
            box = pygame.Rect(206, INTERNAL_SIZE[1] - 28, 228, 20)
            pygame.draw.rect(self.canvas, (19, 21, 33), box, border_radius=4)
            pygame.draw.rect(self.canvas, (90, 97, 133), box, 1, border_radius=4)
            self.canvas.blit(prompt, (box.x + 8, box.y + 4))

    def _draw_end_overlay(self) -> None:
        overlay = pygame.Surface(INTERNAL_SIZE, pygame.SRCALPHA)
        overlay.fill((8, 9, 16, 180))
        self.canvas.blit(overlay, (0, 0))

        panel = pygame.Rect(120, 98, 400, 168)
        pygame.draw.rect(self.canvas, (25, 29, 43), panel, border_radius=8)
        pygame.draw.rect(self.canvas, (111, 120, 162), panel, 2, border_radius=8)

        title = self.fonts["title"].render("Demo Outcome", False, (238, 242, 255))
        self.canvas.blit(title, (panel.x + 14, panel.y + 12))

        money = self.dialogue.money
        mood, mood_col = self._outcome_mood_line()

        info = self.fonts["body"].render(
            f"Money collected: {money} reals", False, (244, 231, 156)
        )
        self.canvas.blit(info, (panel.x + 14, panel.y + 40))
        mood_text = self.fonts["body"].render(mood, False, mood_col)
        self.canvas.blit(mood_text, (panel.x + 14, panel.y + 61))

        final_line = self.dialogue.final_line or "The conversation is over."
        for i, line in enumerate(
            wrapped_lines(final_line, self.fonts["small"], panel.width - 28)[:4]
        ):
            txt = self.fonts["small"].render(line, False, (211, 219, 244))
            self.canvas.blit(txt, (panel.x + 14, panel.y + 87 + i * 14))

        restart = self.fonts["small"].render(
            "Press R to restart the demo", False, (168, 191, 246)
        )
        self.canvas.blit(restart, (panel.x + 14, panel.bottom - 22))

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()

        pygame.quit()


def main() -> None:
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
