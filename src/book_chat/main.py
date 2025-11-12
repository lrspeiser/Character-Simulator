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
from .gui import ChatWindow
import threading

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    logger.info(f"Loading config from: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.debug(f"Config loaded")
    return config


def main():
    """Main entry point."""
    # Load environment variables from .env
    load_dotenv()
    
    # Get config path
    config_path = os.getenv("CONFIG_PATH", "configs/nexus_labs.yaml")
    
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        print("Create a config file or set CONFIG_PATH environment variable.")
        sys.exit(1)
    
    # Load configuration
    config = load_config(config_path)
    
    # Initialize Claude client
    model = config.get("model", "claude-sonnet-4-20250514")
    client = ClaudeClient(model=model)
    
    # Create characters from backstory files
    characters = []
    for char_config in config["characters"]:
        backstory_file = char_config["backstory_file"]
        # Make path relative to config directory if not absolute
        if not os.path.isabs(backstory_file):
            config_dir = os.path.dirname(config_path)
            backstory_file = os.path.join(config_dir, backstory_file)
        
        character = Character(
            name=char_config["name"],
            backstory_file=backstory_file,
            client=client
        )
        characters.append(character)
    
    # Create narrator with guide file
    narrator_guide = config["narrator_guide"]
    if not os.path.isabs(narrator_guide):
        config_dir = os.path.dirname(config_path)
        narrator_guide = os.path.join(config_dir, narrator_guide)
    
    narrator = Narrator(
        guide_file=narrator_guide,
        client=client
    )
    
    # Get opening scene
    opening_scene = config["opening_scene"]
    
    # Get max turns
    max_turns = config.get("max_turns", 50)
    
    # Check if GUI mode is enabled (default: true)
    use_gui = config.get("use_gui", True)
    
    if use_gui:
        # Create GUI window
        gui = ChatWindow()
        
        # Create conversation with GUI
        conversation = Conversation(
            characters=characters,
            narrator=narrator,
            opening_scene=opening_scene,
            client=client,
            gui_window=gui
        )
        
        # Run conversation in separate thread
        def run_conversation():
            conversation.start(max_turns=max_turns)
            gui.close()
        
        conversation_thread = threading.Thread(target=run_conversation, daemon=True)
        conversation_thread.start()
        
        # Run GUI main loop (blocks until window closes)
        gui.run()
    else:
        # CLI mode
        conversation = Conversation(
            characters=characters,
            narrator=narrator,
            opening_scene=opening_scene,
            client=client
        )
        
        conversation.start(max_turns=max_turns)


if __name__ == "__main__":
    main()
