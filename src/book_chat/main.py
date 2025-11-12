"""
Main entry point for the book character chat simulation.
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

from .anthropic_client import ClaudeClient
from .core import Character, Narrator, Conversation

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    logger.info(f"Loading config from: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.debug(f"Config loaded: {config}")
    return config


def main():
    """Main entry point."""
    # Load environment variables from .env
    load_dotenv()
    
    # Get config path
    config_path = os.getenv("CONFIG_PATH", "configs/characters.yaml")
    
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        print("Create a config file at configs/characters.yaml or set CONFIG_PATH environment variable.")
        sys.exit(1)
    
    # Load configuration
    config = load_config(config_path)
    
    # Initialize Claude client
    model = config.get("model", "claude-sonnet-4-5")
    client = ClaudeClient(model=model)
    
    # Create characters
    characters = []
    for char_config in config["characters"]:
        character = Character(
            name=char_config["name"],
            backstory=char_config["backstory"],
            personality=char_config["personality"],
            client=client
        )
        characters.append(character)
    
    # Create narrator
    narrator = Narrator(client=client)
    
    # Get opening scene
    opening_scene = config["opening_scene"]
    
    # Get max turns
    max_turns = config.get("max_turns", 10)
    
    # Start conversation
    conversation = Conversation(
        characters=characters,
        narrator=narrator,
        opening_scene=opening_scene
    )
    
    conversation.start(max_turns=max_turns)


if __name__ == "__main__":
    main()
