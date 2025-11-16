"""Minimal test of Narrator.choose_next_speaker using real Claude API.

This script:
- Loads ANTHROPIC_API_KEY from .env
- Creates a ClaudeClient and Narrator
- Builds a tiny fake conversation_history
- Calls choose_next_speaker on two dummy Characters

The goal is to verify that:
- anthropic_client no longer passes `output_format` to messages.create()
- choose_next_speaker runs without raising `Messages.create() got an unexpected keyword` errors
- We get a sensible next_speaker name instead of always defaulting to first character due to errors.
"""

import logging
from pathlib import Path

from dotenv import load_dotenv

import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.book_chat.anthropic_client import ClaudeClient  # noqa: E402
from src.book_chat.core import Character, Narrator        # noqa: E402


def main() -> None:
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    client = ClaudeClient()
    narrator = Narrator(client=client)

    # Minimal fake conversation context
    history = [
        {"role": "user", "content": "Commander Sarah Chen accuses Dr. Marcus Webb of hiding something."},
    ]

    # Two simple characters that "want" to respond
    c1 = Character(name="Commander Sarah Chen", backstory="Test backstory for Sarah", client=client)
    c2 = Character(name="Dr. Marcus Webb", backstory="Test backstory for Marcus", client=client)

    speaker = narrator.choose_next_speaker([c1, c2], history)
    print(f"Chosen next speaker: {speaker.name if speaker else None}")


if __name__ == "__main__":
    main()
