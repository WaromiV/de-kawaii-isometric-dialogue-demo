#!/usr/bin/env python3
"""Pre-generate static ElevenLabs MP3 files for all dialogue lines."""

from __future__ import annotations

import argparse
import os
from typing import cast

import main
from narration_engine import NarrationEngine


class _SilentAudio:
    def play(self, _name: str) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-key",
        default=os.getenv("ELEVENLABS_API_KEY", ""),
        help="ElevenLabs API key (or set ELEVENLABS_API_KEY).",
    )
    parser.add_argument(
        "--character-voice",
        default=main.CHARACTER_VOICE_ID,
        help="Voice ID for character lines.",
    )
    parser.add_argument(
        "--narrator-voice",
        default=main.NARRATOR_VOICE_ID,
        help="Voice ID for narrator/status lines.",
    )
    return parser.parse_args()


def main_cli() -> int:
    args = parse_args()
    if not args.api_key:
        print("Missing API key. Set ELEVENLABS_API_KEY or pass --api-key.")
        return 1

    engine = NarrationEngine(
        api_key=args.api_key,
        character_voice_id=args.character_voice,
        narrator_voice_id=args.narrator_voice,
    )

    dialogue = main.DialogueSystem(
        main.SkillState(),
        cast(main.AudioBank, _SilentAudio()),
        engine,
    )
    character_lines, narrator_lines = dialogue.voiceover_manifest()
    narrator_lines.extend(
        [
            "Big score. Dirty victory.",
            "Enough to breathe for a night.",
            "Loose change and bruised pride.",
            "Empty pockets. The city wins this round.",
            "The conversation is over.",
        ]
    )

    manifest_path = engine.write_manifest(character_lines, narrator_lines)
    engine.prefetch_lines(character_lines, narrator_lines)

    print(f"Manifest: {manifest_path}")
    print("Done: static MP3 prefetch complete.")
    if engine.last_error:
        print(f"Last API error: {engine.last_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
