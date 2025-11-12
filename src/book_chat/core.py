"""
Core logic for character-based conversation simulation.
"""

import logging
import sys
import select
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from .anthropic_client import ClaudeClient

logger = logging.getLogger(__name__)

# Token limit for conversation history
MAX_HISTORY_TOKENS = 20000


def parse_json_response(response: str, fallback_key: str = None) -> dict:
    """Parse JSON response with fallback to plain text."""
    try:
        # Try to parse as JSON
        data = json.loads(response.strip())
        return data
    except json.JSONDecodeError:
        # If not JSON, return as fallback key
        if fallback_key:
            return {fallback_key: response.strip()}
        return {"text": response.strip()}


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
            f"You are {self.name}.\n\n"
            f"YOUR BACKSTORY (for context - you don't know what others know):\n"
            f"{self.backstory}\n\n"
            f"HOW TO PLAY THIS CHARACTER:\n"
            f"- React naturally to what you just heard in the conversation\n"
            f"- Stay in character (personality, speaking style, concerns)\n"
            f"- Your backstory informs WHO you are, not WHAT you must say\n"
            f"- Like improv: respond authentically to the moment\n"
            f"- You DON'T know what's in other characters' backstories\n"
            f"- You ONLY know what's been said aloud in the conversation\n\n"
            f"DIALOGUE RULES:\n"
            f"1. Only write the WORDS you speak out loud\n"
            f"2. NO actions: 'I pause', 'I stand up', 'I say', 'my voice'\n"
            f"3. NO asterisks, parentheticals, or stage directions\n"
            f"4. The narrator handles all actions/descriptions\n\n"
            f"CORRECT (pure dialogue):\n"
            f"✓ \"What triggered the lockdown? My daughter is expecting my call.\"\n"
            f"✓ \"Wait - someone accessed my files at 9:23 PM.\"\n\n"
            f"WRONG (includes actions):\n"
            f"✗ I pause, then say \"What triggered the lockdown?\"\n"
            f"✗ *crosses arms* \"Are you suggesting this?\"\n\n"
            f"Respond with 1-3 sentences as {self.name} would naturally say.\n\n"
            f"FORMAT: Respond with JSON:\n"
            f'{{"dialogue": "your spoken words"}}'
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
    
    def respond(self, conversation_history: List[Dict[str, str]], stream_callback: Optional[callable] = None, gui_window=None) -> str:
        """
        Generate a response from this character (streamed to CLI or GUI, or from human player).
        
        Args:
            conversation_history: List of conversation messages
            stream_callback: Optional callback for streaming to GUI
            gui_window: GUI window to check if this character is player-controlled
            
        Returns:
            Character's response
        """
        logger.info(f"{self.name} is responding...")
        
        # Check if this character is controlled by a human player
        if gui_window and gui_window.get_selected_character() == self.name:
            logger.info(f"{self.name} is player-controlled, waiting for input...")
            gui_window.enable_player_input(self.name)
            response = gui_window.wait_for_player_input()
            
            if response is None:  # Player quit
                return ""
            
            logger.info(f"{self.name} (player) responded: {response}")
            return response
        
        # AI-controlled character
        system_prompt = self.get_system_prompt()
        
        response = self.client.send_message(
            system_prompt=system_prompt,
            messages=conversation_history,
            max_tokens=300,
            stream=True,
            prefix=f"\n{self.name}: " if not stream_callback else None,
            stream_callback=stream_callback
        )
        
        # Parse JSON response
        parsed = parse_json_response(response, fallback_key="dialogue")
        dialogue = parsed.get("dialogue", response)
        
        logger.info(f"{self.name} responded: {dialogue}")
        return dialogue


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
        character_names = [c.name for c in characters]
        system_prompt = (
            f"The following characters want to speak: {', '.join(character_names)}\n\n"
            f"Who should speak next based on dramatic tension and story flow?\n\n"
            f"FORMAT: Respond with JSON in this exact format:\n"
            f'{{"next_speaker": "Character Name"}}\n\n'
            f"CORRECT examples:\n"
            f'{{"next_speaker": "Dr. Sarah Chen"}}\n'
            f'{{"next_speaker": "Marcus Webb"}}\n'
            f'{{"next_speaker": "Victoria Reeves"}}\n\n'
            f"The next_speaker value must be EXACTLY one of: {', '.join(character_names)}"
        )
        
        try:
            choice = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=50,
                stream=False
            )
            
            # Parse JSON response
            parsed = parse_json_response(choice, fallback_key="next_speaker")
            choice_name = parsed.get("next_speaker", choice).strip()
            
            # Find matching character (exact match first)
            for character in characters:
                if character.name.lower() == choice_name.lower():
                    logger.info(f"Narrator chose (exact): {character.name}")
                    return character
            
            # Try partial match
            for character in characters:
                if character.name.lower() in choice_name.lower() or choice_name.lower() in character.name.lower():
                    logger.info(f"Narrator chose (partial): {character.name}")
                    return character
            
            # Default to first if no match
            logger.warning(f"Narrator choice '{choice_name}' didn't match any character, defaulting to {characters[0].name}")
            return characters[0]
            
        except Exception as e:
            logger.error(f"Error in narrator choice: {e}")
            logger.info(f"Defaulting to first character: {characters[0].name}")
            return characters[0]
    
    def narrate_scene(self, conversation_history: List[Dict[str, str]], last_speaker: str, stream_callback: Optional[callable] = None) -> str:
        """
        Decide if scene description is needed, and generate if so.
        
        Args:
            conversation_history: Conversation so far
            last_speaker: Name of character who just spoke
            stream_callback: Optional callback for streaming to GUI
            
        Returns:
            Scene description (or empty string if none needed)
        """
        logger.info("Checking if scene description needed...")
        
        # First, ask if narration is needed
        decision_prompt = (
            f"{self.guide}\n\n"
            f"{last_speaker} just spoke.\n\n"
            f"Does the scene need narration right now? Answer YES only if:\n"
            f"- Something important happens physically (actions, reactions, movement)\n"
            f"- The environment changes (sounds, lights, atmosphere shifts)\n"
            f"- There's a dramatic moment that needs description\n\n"
            f"Answer NO if the dialogue flows naturally to the next speaker without needing description.\n\n"
            f"Answer ONLY with YES or NO."
        )
        
        try:
            decision = self.client.send_message(
                system_prompt=decision_prompt,
                messages=conversation_history,
                max_tokens=10,
                stream=False
            )
            
            needs_narration = decision.strip().upper().startswith("YES")
            logger.info(f"Narration needed: {needs_narration}")
            
            if not needs_narration:
                return ""
            
        except Exception as e:
            logger.error(f"Error checking narration need: {e}")
            return ""
        
        # Generate scene description
        logger.info("Narrator generating scene description...")
        
        system_prompt = (
            f"{self.guide}\n\n"
            f"You are the narrator. {last_speaker} just spoke.\n\n"
            f"CRITICAL RULES:\n"
            f"1. You may ONLY provide scene description and narration\n"
            f"2. NO dialogue in quotes - characters speak for themselves\n"
            f"3. NO \"he said\" or \"she replied\" - just describe the scene\n"
            f"4. NO character names followed by colons (e.g. NO 'Marcus Webb:')\n\n"
            f"Describe what happens next (1-2 sentences):\n"
            f"- Body language, facial expressions, physical actions\n"
            f"- Environmental details (sounds, lighting, atmosphere)\n"
            f"- Tension, mood shifts, or dramatic moments\n\n"
            f"Example: \"Webb's hand moves to his holster. The lights flicker, and Chen's eyes dart to the door.\"\n"
            f"NOT: Webb says, \"We need to talk.\" or Marcus Webb: or Webb thinks about the situation.\n\n"
            f"Keep it vivid, cinematic, and concise. Only narrate - never speak as any character.\n\n"
            f"FORMAT: Respond with JSON in this exact format:\n"
            f'{{"scene": "your scene description here"}}'
        )
        
        try:
            description = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=200,
                stream=True,
                stream_callback=stream_callback
            )
            
            # Parse JSON response
            parsed = parse_json_response(description, fallback_key="scene")
            scene_text = parsed.get("scene", description)
            
            logger.info(f"Narrator description: {scene_text}")
            return scene_text
            
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
            
            # Narrator decides if scene description is needed
            if turn > 0 and self.last_speaker_name:  # Skip scene description on first turn
                scene_desc = self.narrator.narrate_scene(
                    self.history, 
                    self.last_speaker_name,  # Who spoke LAST time
                    stream_callback=None  # Don't stream decision-making
                )
                
                # Only display and add to history if narrator provided description
                if scene_desc:
                    if self.gui:
                        self.gui.start_streaming_message('narrator', is_narrator=True)
                        # Stream the scene description
                        for char in scene_desc:
                            self.gui.stream_text(char)
                        self.gui.end_streaming_message()
                    else:
                        print(f"\n[{scene_desc}]\n")
                    
                    # Add scene description to history
                    self.history.append({
                        "role": "user",
                        "content": f"[Scene: {scene_desc}]"
                    })
            
            # Character responds
            if self.gui:
                # Check if player is controlling this character
                if self.gui.get_selected_character() == speaker.name:
                    # Player-controlled - no streaming bubble, wait for input
                    response = speaker.respond(self.history, stream_callback=None, gui_window=self.gui)
                    # Display player's dialogue in bubble
                    if response:
                        self.gui.add_message(speaker.name, response, is_narrator=False)
                else:
                    # AI-controlled - stream as normal
                    self.gui.start_streaming_message(speaker.name, is_narrator=False)
                    response = speaker.respond(self.history, stream_callback=self.gui.stream_text, gui_window=self.gui)
                    self.gui.end_streaming_message()
            else:
                response = speaker.respond(self.history, gui_window=None)
            
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
