"""
Core logic for character-based conversation simulation.
"""

import logging
import sys
import select
from typing import List, Dict, Any, Optional
from pathlib import Path
from .anthropic_client import ClaudeClient

logger = logging.getLogger(__name__)

# Token limit for conversation history
MAX_HISTORY_TOKENS = 20000


class Character:
    """Represents a character in the conversation with its own LLM instance."""
    
    def __init__(self, name: str, backstory_file: str, client: ClaudeClient):
        """
        Initialize a character.
        
        Args:
            name: Character's name
            backstory_file: Path to character's backstory file
            client: Claude API client
        """
        self.name = name
        self.backstory_file = backstory_file
        self.client = client
        
        # Load backstory from file
        with open(backstory_file, 'r') as f:
            self.backstory = f.read()
        
        logger.info(f"Character created: {name}")
        logger.debug(f"  Backstory loaded from: {backstory_file}")
    
    def get_system_prompt(self) -> str:
        """Build the system prompt for this character."""
        return (
            f"{self.backstory}\n\n"
            f"CRITICAL RULES:\n"
            f"1. You may ONLY speak dialogue - the actual words {self.name} says out loud\n"
            f"2. NO action descriptions, NO body language, NO scene setting\n"
            f"3. NO asterisks, NO parentheticals, NO stage directions\n"
            f"4. Do NOT describe what you're doing, thinking, or feeling - just speak\n"
            f"5. The narrator handles all descriptions - you only handle spoken words\n\n"
            f"Respond as {self.name} would say it, using 1-3 sentences of pure dialogue.\n"
            f"Example: \"I need answers, Marcus. What exactly happened on Level 3?\"\n"
            f"NOT: *crosses arms* \"I need answers.\" or I say firmly, \"I need answers.\""
        )
    
    def wants_to_respond(self, conversation_history: List[Dict[str, str]]) -> bool:
        """
        Determine if this character wants to respond to the current conversation state.
        
        Args:
            conversation_history: List of conversation messages
            
        Returns:
            True if character wants to respond
        """
        logger.debug(f"Checking if {self.name} wants to respond...")
        
        system_prompt = (
            f"You are {self.name}.\n\n"
            f"Given the conversation so far, do you want to respond? "
            f"Answer with ONLY 'YES' or 'NO' based on whether you have something meaningful to say."
        )
        
        try:
            response = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=10,
                stream=False
            )
            
            wants_to = response.strip().upper().startswith("YES")
            logger.info(f"{self.name} wants to respond: {wants_to}")
            return wants_to
            
        except Exception as e:
            logger.error(f"Error checking if {self.name} wants to respond: {e}")
            return False
    
    def respond(self, conversation_history: List[Dict[str, str]], stream_callback: Optional[callable] = None) -> str:
        """
        Generate a response from this character (streamed to CLI or GUI).
        
        Args:
            conversation_history: List of conversation messages
            stream_callback: Optional callback for streaming to GUI
            
        Returns:
            Character's response
        """
        logger.info(f"{self.name} is responding...")
        
        system_prompt = self.get_system_prompt()
        
        response = self.client.send_message(
            system_prompt=system_prompt,
            messages=conversation_history,
            max_tokens=300,
            stream=True,
            prefix=f"\n{self.name}: " if not stream_callback else None,
            stream_callback=stream_callback
        )
        
        logger.info(f"{self.name} responded: {response}")
        return response


class Narrator:
    """Controls turn-taking when multiple characters want to respond."""
    
    def __init__(self, guide_file: str, client: ClaudeClient):
        """
        Initialize the narrator.
        
        Args:
            guide_file: Path to narrator guide file
            client: Claude API client
        """
        self.client = client
        self.guide_file = guide_file
        
        # Load narrator guide
        with open(guide_file, 'r') as f:
            self.guide = f.read()
        
        logger.info("Narrator initialized")
        logger.debug(f"  Guide loaded from: {guide_file}")
    
    def choose_next_speaker(
        self,
        characters: List[Character],
        conversation_history: List[Dict[str, str]]
    ) -> Character:
        """
        Choose which character should speak next.
        
        Args:
            characters: List of characters who want to respond
            conversation_history: Conversation so far
            
        Returns:
            The chosen character
        """
        if len(characters) == 0:
            logger.warning("No characters want to respond")
            return None
        
        if len(characters) == 1:
            logger.info(f"Only one character wants to respond: {characters[0].name}")
            return characters[0]
        
        logger.info(f"Multiple characters want to respond: {[c.name for c in characters]}")
        
        # Ask narrator to choose
        character_names = ", ".join([c.name for c in characters])
        system_prompt = (
            f"{self.guide}\n\n"
            f"The following characters want to speak: {character_names}\n"
            f"Based on the conversation flow and dramatic tension, who should speak next?\n"
            f"Respond with ONLY the name of the character who should speak."
        )
        
        try:
            choice = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=20,
                stream=False
            )
            
            # Find matching character
            choice_name = choice.strip()
            for character in characters:
                if character.name.lower() in choice_name.lower():
                    logger.info(f"Narrator chose: {character.name}")
                    return character
            
            # Default to first if no match
            logger.warning(f"Narrator choice '{choice_name}' didn't match, defaulting to {characters[0].name}")
            return characters[0]
            
        except Exception as e:
            logger.error(f"Error in narrator choice: {e}")
            logger.info(f"Defaulting to first character: {characters[0].name}")
            return characters[0]
    
    def narrate_scene(self, conversation_history: List[Dict[str, str]], last_speaker: str, stream_callback: Optional[callable] = None) -> str:
        """
        Generate a brief scene description showing what's happening.
        
        Args:
            conversation_history: Conversation so far
            last_speaker: Name of character who just spoke
            stream_callback: Optional callback for streaming to GUI
            
        Returns:
            Scene description
        """
        logger.info("Narrator generating scene description...")
        
        system_prompt = (
            f"{self.guide}\n\n"
            f"You are the narrator. {last_speaker} just spoke.\n\n"
            f"CRITICAL RULES:\n"
            f"1. You may ONLY provide scene description and narration\n"
            f"2. NO dialogue in quotes - characters speak for themselves\n"
            f"3. NO \"he said\" or \"she replied\" - just describe the scene\n\n"
            f"Describe what happens next (1-2 sentences):\n"
            f"- Body language, facial expressions, physical actions\n"
            f"- Environmental details (sounds, lighting, atmosphere)\n"
            f"- Tension, mood shifts, or dramatic moments\n\n"
            f"Example: \"Webb's hand moves to his holster. The lights flicker, and Chen's eyes dart to the door.\"\n"
            f"NOT: Webb says, \"We need to talk.\" or Webb thinks about the situation.\n\n"
            f"Keep it vivid, cinematic, and concise. Only narrate - never speak as any character."
        )
        
        try:
            description = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=150,
                stream=True,
                stream_callback=stream_callback
            )
            
            logger.info(f"Narrator description: {description}")
            return description
            
        except Exception as e:
            logger.error(f"Error generating scene description: {e}")
            return ""


class Conversation:
    """Manages the overall conversation simulation."""
    
    def __init__(self, characters: List[Character], narrator: Narrator, opening_scene: str, client: ClaudeClient, gui_window=None):
        """
        Initialize conversation.
        
        Args:
            characters: List of all characters
            narrator: Narrator instance
            opening_scene: Opening situation/prompt
            client: Claude API client for token counting
            gui_window: Optional GUI window for display
        """
        self.characters = characters
        self.narrator = narrator
        self.opening_scene = opening_scene
        self.history: List[Dict[str, str]] = []
        self.client = client
        self.quit_requested = False
        self.gui = gui_window
        self.last_speaker_name = None  # Track who spoke last
        
        logger.info("Conversation initialized")
        logger.info(f"Characters: {[c.name for c in characters]}")
        logger.info(f"Opening scene: {opening_scene}")
    
    def trim_history_to_token_limit(self):
        """
        Trim conversation history to stay under MAX_HISTORY_TOKENS.
        Keeps the most recent messages.
        """
        # Calculate total tokens in history
        total_tokens = 0
        for msg in self.history:
            total_tokens += self.client.count_tokens(msg['content'])
        
        # Remove oldest messages until under limit
        while total_tokens > MAX_HISTORY_TOKENS and len(self.history) > 1:
            removed = self.history.pop(0)
            total_tokens -= self.client.count_tokens(removed['content'])
            logger.info(f"Trimmed message from history (tokens: {total_tokens}/{MAX_HISTORY_TOKENS})")
    
    def start(self, max_turns: int = 10):
        """
        Start the conversation simulation.
        
        Args:
            max_turns: Maximum number of conversation turns
        """
        # Display opening scene
        if self.gui:
            self.gui.add_message('narrator', self.opening_scene, is_narrator=True)
        else:
            print("\n" + "=" * 80)
            print("LOCKDOWN AT NEXUS LABS")
            print("=" * 80)
            print(f"\n{self.opening_scene}\n")
            print("\n[Type 'Q' and press Enter at any time to quit]\n")
        
        # Add opening scene to history
        self.history.append({
            "role": "user",
            "content": self.opening_scene
        })
        
        for turn in range(max_turns):
            # Check for quit command
            if self._check_for_quit():
                if self.gui:
                    self.gui.update_status("Conversation ended")
                else:
                    print("\n[Quitting conversation...]\n")
                break
            
            logger.info(f"\n--- TURN {turn + 1} ---")
            
            # Trim history to token limit
            self.trim_history_to_token_limit()
            
            # Check which characters want to respond
            interested_characters = []
            for character in self.characters:
                if character.wants_to_respond(self.history):
                    interested_characters.append(character)
            
            if not interested_characters:
                logger.info("No characters want to respond. Conversation ended.")
                if self.gui:
                    self.gui.update_status("Conversation ended - no more responses")
                else:
                    print("\n[The room falls silent. No one has anything more to say.]\n")
                break
            
            # Narrator chooses who speaks
            speaker = self.narrator.choose_next_speaker(interested_characters, self.history)
            
            if not speaker:
                logger.warning("Narrator couldn't choose a speaker. Ending conversation.")
                break
            
            # Wait for user to press space before continuing
            if self.gui and turn > 0:
                self.gui.wait_for_space()
                if self.gui.is_quit_requested():
                    break
            
            # Narrator describes the scene before character speaks
            if turn > 0 and self.last_speaker_name:  # Skip scene description on first turn
                if self.gui:
                    self.gui.start_streaming_message('narrator', is_narrator=True)
                    scene_desc = self.narrator.narrate_scene(
                        self.history, 
                        self.last_speaker_name,  # Who spoke LAST time
                        stream_callback=self.gui.stream_text if self.gui else None
                    )
                    self.gui.end_streaming_message()
                else:
                    scene_desc = self.narrator.narrate_scene(self.history, self.last_speaker_name)
                    print(f"\n[{scene_desc}]\n")
                
                # Add scene description to history
                if scene_desc:
                    self.history.append({
                        "role": "user",
                        "content": f"[Scene: {scene_desc}]"
                    })
            
            # Character responds
            if self.gui:
                self.gui.start_streaming_message(speaker.name, is_narrator=False)
                response = speaker.respond(self.history, stream_callback=self.gui.stream_text)
                self.gui.end_streaming_message()
            else:
                response = speaker.respond(self.history)
            
            # Add to history
            self.history.append({
                "role": "assistant",
                "content": f"{speaker.name}: {response}"
            })
            
            # Track who spoke for next scene description
            self.last_speaker_name = speaker.name
            
            # Add user acknowledgment to continue conversation
            self.history.append({
                "role": "user",
                "content": "Continue the conversation."
            })
        
        if not self.gui:
            print("\n" + "=" * 80)
            print("CONVERSATION END")
            print("=" * 80)
        logger.info("Conversation simulation completed")
    
    def _check_for_quit(self) -> bool:
        """
        Check if user has typed 'Q' to quit (CLI) or clicked Quit button (GUI).
        """
        # Check GUI quit button if using GUI
        if self.gui:
            return self.gui.is_quit_requested()
        
        # Check keyboard input for CLI
        if sys.platform != 'win32':
            # Unix-like systems
            if select.select([sys.stdin], [], [], 0.0)[0]:
                user_input = sys.stdin.readline().strip().upper()
                if user_input == 'Q':
                    return True
        return False
