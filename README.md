# Isometric Kawaii-Horror Dialogue Demo (Pygame)

A polished vertical slice inspired by Disco-like checks, built as a small narrative RPG prototype.
<img width="1280" height="720" alt="image" src="https://github.com/user-attachments/assets/bdef78a1-8126-466d-aeff-9581ad707fef" />
<img width="2166" height="1214" alt="image" src="https://github.com/user-attachments/assets/c892846e-dd39-44ac-90dd-1def16d13d68" />
<img width="2162" height="1220" alt="image" src="https://github.com/user-attachments/assets/55261e6f-bf15-45f2-b3e1-a7b7ebb4f014" />

## Features

- Isometric pixel-art world with one playable character and one conversation target
- Facial animation states (idle blink + talking mouth poses)
- Dialogue checks: passive (`skill + 6`) and active (`2d6 + skill + modifiers`)
- White/red check behavior with retry gating through skill investment
- Dice popup with rendered dice faces and success/failure vignette flash
- Skill menu (`3x3` grid, point cap, spendable pool)
- Camera zoom controls
- ElevenLabs voice-over pipeline with static MP3 cache playback
- No main menu; boots directly into the playable scene

## Run

```bash
python -m pip install -r requirements.txt
python main.py
```

## Voice-over Setup (ElevenLabs)

1. Copy `.env.example` to `.env` (or export the env var in your shell).
2. Set `ELEVENLABS_API_KEY`.
3. (Optional) pre-generate static MP3 lines once:

```bash
python scripts/prefetch_tts.py
```

The runtime uses cached files in `assets/audio/tts_static/` and avoids on-demand generation by default.

## Controls

- `WASD` / arrows: move
- `E` or `Space`: talk (when near NPC)
- `O`: open/close skill menu
- `+` / `-` (or `]` / `[`) : camera zoom in/out
- mouse wheel: camera zoom in/out
- click `Skills [O]`: open skill menu
- dialogue options: click or press `1..9`
- `R`: restart after ending
- `Esc`: quit

## Notes

- Background music is a premade CC0 track: `assets/audio/at_the_end_of_hope_loop.wav`.
- Music source/license details are in `assets/audio/MUSIC_SOURCE.txt`.
- UI/check sound effects are generated automatically if missing in `assets/audio/`.
- Voice-over files are stored in `assets/audio/tts_static/`.
- Visual assets are pixel surfaces generated in code to keep the demo self-contained.
- Font files are in `assets/fonts/` (`Silkscreen-Regular.ttf`, `Silkscreen-Bold.ttf`).
- Font license text is included as `assets/fonts/OFL-Silkscreen.txt`.
