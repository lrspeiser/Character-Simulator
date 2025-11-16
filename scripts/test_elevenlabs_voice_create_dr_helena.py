"""One-off tester for ElevenLabs voice creation for Dr. Helena Sterling.

This script uses the real ElevenLabs API to:
- Load ELEVENLABS_API_KEY from .env
- Instantiate ElevenLabsTTS
- Call find_or_create_voice(...) with auto_create=True for Dr. Helena Sterling

It is intended to validate that our pipeline **creates** a custom voice
from the character's text description, without searching or falling back
to random existing voices.

See README.md section "ElevenLabs TTS" for API key setup and links to
official ElevenLabs Text-to-Voice documentation.
"""

import logging
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root (containing src/) is on sys.path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.book_chat.tts_elevenlabs import ElevenLabsTTS  # noqa: E402


def main() -> None:
    # Load environment variables (ELEVENLABS_API_KEY, etc.)
    load_dotenv()

    # Configure basic logging so we can see ElevenLabsTTS logs on stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # This is the exact description we saw in the logs for Dr. Helena Sterling
    voice_description = (
        "Female professional archaeologist, 40s, British Oxford accent, "
        "intellectual and intense"
    )

    # Instantiate ElevenLabs TTS client (reads ELEVENLABS_API_KEY from env)
    tts = ElevenLabsTTS()

    print("Creating ElevenLabs voice for Dr. Helena Sterling using real API calls...")
    voice_id = tts.find_or_create_voice(
        character_name="Dr. Helena Sterling",
        voice_description=voice_description,
        auto_create=True,
    )

    print(f"Resulting voice_id: {voice_id}")


if __name__ == "__main__":
    main()
