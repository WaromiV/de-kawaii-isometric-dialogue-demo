"""ElevenLabs narration queue for in-game voice-over playback."""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from urllib import error, request

import pygame


class NarrationEngine:
    def __init__(
        self,
        api_key: str | None,
        character_voice_id: str,
        narrator_voice_id: str,
        cache_dir: str = "assets/audio/tts_static",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.character_voice_id = character_voice_id
        self.narrator_voice_id = narrator_voice_id
        self.cache_dir = cache_dir

        self.enabled = pygame.mixer.get_init() is not None
        self.channel = pygame.mixer.Channel(6) if self.enabled else None
        self.queue: deque[tuple[str, str]] = deque()
        self.sound_cache: dict[str, pygame.mixer.Sound] = {}
        self.allow_runtime_generation = False
        self.last_error = ""

        os.makedirs(self.cache_dir, exist_ok=True)

    def clear(self) -> None:
        self.queue.clear()
        if self.channel is not None:
            self.channel.stop()

    def queue_character(self, text: str) -> None:
        self._queue_text(text, self.character_voice_id, interrupt=True)

    def queue_narrator(self, text: str) -> None:
        self._queue_text(text, self.narrator_voice_id, interrupt=False)

    def prefetch_lines(
        self,
        character_lines: list[str],
        narrator_lines: list[str],
    ) -> None:
        if not self.api_key:
            return

        jobs = self._collect_jobs(character_lines, narrator_lines)

        for voice_id, text in jobs:
            self._ensure_audio_file(text, voice_id, allow_generate=True)

    def write_manifest(
        self,
        character_lines: list[str],
        narrator_lines: list[str],
        manifest_path: str | None = None,
    ) -> str:
        jobs = self._collect_jobs(character_lines, narrator_lines)
        path = manifest_path or os.path.join(self.cache_dir, "MANIFEST.txt")

        lines = [
            "Voice-over static file manifest",
            "Format: <voice_id> <filename> <text>",
            "",
        ]
        for voice_id, text in jobs:
            digest = hashlib.sha1(f"{voice_id}|{text}".encode("utf-8")).hexdigest()
            lines.append(f"{voice_id} {digest}.mp3 {text}")

        with open(path, "w", encoding="utf-8") as manifest:
            manifest.write("\n".join(lines))
        return path

    def update(self) -> None:
        self._play_next_from_queue(force_interrupt=False)

    def _queue_text(self, text: str, voice_id: str, interrupt: bool) -> None:
        normalized = self._normalize(text)
        if not normalized:
            return

        if interrupt:
            # Latest character line wins: cut current playback and pending queue.
            self.queue.clear()
            if self.channel is not None and self.channel.get_busy():
                self.channel.stop()

        self.queue.append((normalized, voice_id))
        self._play_next_from_queue(force_interrupt=False)

    def _play_next_from_queue(self, force_interrupt: bool) -> None:
        if not self.enabled or self.channel is None:
            return
        if force_interrupt and self.channel.get_busy():
            self.channel.stop()
        if self.channel.get_busy():
            return

        while self.queue:
            text, voice_id = self.queue.popleft()
            audio_path = self._ensure_audio_file(
                text,
                voice_id,
                allow_generate=self.allow_runtime_generation,
            )
            if not audio_path:
                continue

            sound = self.sound_cache.get(audio_path)
            if sound is None:
                try:
                    sound = pygame.mixer.Sound(audio_path)
                except pygame.error:
                    continue
                sound.set_volume(0.95)
                self.sound_cache[audio_path] = sound

            self.channel.play(sound)
            break

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.replace("\n", " ").split()).strip()

    def _collect_jobs(
        self,
        character_lines: list[str],
        narrator_lines: list[str],
    ) -> list[tuple[str, str]]:
        seen: set[tuple[str, str]] = set()
        jobs: list[tuple[str, str]] = []

        for line in character_lines:
            normalized = self._normalize(line)
            if not normalized:
                continue
            key = (self.character_voice_id, normalized)
            if key in seen:
                continue
            seen.add(key)
            jobs.append(key)

        for line in narrator_lines:
            normalized = self._normalize(line)
            if not normalized:
                continue
            key = (self.narrator_voice_id, normalized)
            if key in seen:
                continue
            seen.add(key)
            jobs.append(key)

        return jobs

    def _ensure_audio_file(
        self,
        text: str,
        voice_id: str,
        allow_generate: bool,
    ) -> str | None:
        digest = hashlib.sha1(f"{voice_id}|{text}".encode("utf-8")).hexdigest()
        path = os.path.join(self.cache_dir, f"{digest}.mp3")
        failed_path = os.path.join(self.cache_dir, f"{digest}.failed")

        if os.path.exists(path):
            return path
        if os.path.exists(failed_path):
            return None
        if not self.api_key:
            return None
        if not allow_generate:
            return None

        if self._synthesize_to_mp3(path, text, voice_id):
            return path

        try:
            with open(failed_path, "w", encoding="utf-8") as failed_file:
                failed_file.write(self.last_error or "generation failed")
        except OSError:
            pass
        return None

    def _synthesize_to_mp3(self, path: str, text: str, voice_id: str) -> bool:
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            "?output_format=mp3_22050_32"
        )
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.75,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        req = request.Request(url=url, data=body, headers=headers, method="POST")
        self.last_error = ""
        try:
            with request.urlopen(req, timeout=45) as resp:
                audio_data = resp.read()
        except error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except OSError:
                detail = str(exc)
            self.last_error = f"HTTP {exc.code}: {detail}"
            return False
        except (error.URLError, TimeoutError, ValueError) as exc:
            self.last_error = str(exc)
            return False

        if not audio_data:
            return False

        try:
            with open(path, "wb") as out_file:
                out_file.write(audio_data)
        except OSError as exc:
            self.last_error = str(exc)
            return False
        return True
