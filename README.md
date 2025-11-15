# Book LLM Chat Simulator

A conversational simulator for book characters powered by Claude. Each character is an LLM with its own backstory that responds to the conversation dynamically. A narrator manages turn-taking when multiple characters want to respond.

## Features

- **Character-based LLMs**: Each character has its own backstory and personality
- **Dynamic conversation flow**: Characters respond based on what they hear from others
- **Narrator control**: Manages which character speaks next when multiple want to respond
- **Verbose logging**: Full visibility into API calls, responses, and decision-making

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure your API keys:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add:
   - `ANTHROPIC_API_KEY` – your Claude API key (see `.env.example` for instructions).
   - `ELEVENLABS_API_KEY` – your ElevenLabs Text-to-Speech API key (see `.env.example`).

3. Edit scenario configuration in `configs/nexus_labs.yaml` (or your own config) to define characters, their backstory files, narrator guide, opening scene, and optional `title`.

## Usage

Run the simulation:
```bash
python src/book_chat/main.py
```

The simulator will:
- Load characters from the config file
- Present the opening scene
- Allow characters to respond in turn based on the narrator's decisions
- Log all interactions and API calls verbosely

## Configuration

Edit `configs/nexus_labs.yaml` (or your own scenario YAML) to:
- Define character names and backstory files
- Set the opening scene or situation
- Configure narrator guide file
- Optionally set a human-readable `title` for the window

## ElevenLabs TTS

This project can optionally read the story aloud using ElevenLabs Text-to-Speech.

- API key:
  - Set `ELEVENLABS_API_KEY` in your `.env` file.
  - See `.env.example` for details.
- Narrator voice:
  - The narrator uses a fixed ElevenLabs voice ID configured in `tts_elevenlabs.py`.
- Character voices (dynamic mode):
  - When using `main_dynamic.py`, the narrator LLM is instructed to add a `voice_search` tag per character with a simple value like `male`, `female`, `young male`, `young female`, or `child female`.
  - The app calls `GET /v2/voices` with that tag to pick a matching ElevenLabs voice for each character, and falls back to the best available voice based on metadata if the search yields no direct matches.
- Playback:
  - Audio is requested via ElevenLabs' WebSocket streaming endpoint `wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input` and played locally (using `afplay` on macOS by default).
  - See `src/book_chat/tts_elevenlabs.py` for implementation details.

If TTS is misconfigured (e.g. missing or invalid API key), errors are logged and audio will not play; fix the configuration rather than hiding the issue.

## API Reference

See:
- [Claude API Documentation](https://docs.anthropic.com/claude/reference/messages_post) for LLM usage.
- [ElevenLabs API Documentation](https://docs.elevenlabs.io/) for Text-to-Speech and voice search.
