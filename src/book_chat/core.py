"""
Core logic for character-based conversation simulation.
"""

import logging
from typing import List, Dict, Any
from .anthropic_client import ClaudeClient

logger = logging.getLogger(__name__)


class Character:
    """Represents a character in the conversation with its own LLM instance."""
    
    def __init__(self, name: str, backstory: str, personality: str, client: ClaudeClient):
        """
        Initialize a character.
        
        Args:
            name: Character's name
            backstory: Character's background and history
            personality: Character's personality traits and speaking style
            client: Claude API client
        """
        self.name = name
        self.backstory = backstory
        self.personality = personality
        self.client = client
        
        logger.info(f"Character created: {name}")
        logger.debug(f"  Backstory: {backstory}")
        logger.debug(f"  Personality: {personality}")
    
    def get_system_prompt(self) -> str:
        """Build the system prompt for this character."""
        return (
            f"You are {self.name}.\n\n"
            f"Backstory: {self.backstory}\n\n"
            f"Personality: {self.personality}\n\n"
            f"Respond as {self.name} would, based on your backstory and personality. "
            f"Keep responses concise and in character. "
            f"Only speak as {self.name} - do not narrate or speak for other characters."
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
            f"You are {self.name}. {self.backstory}\n\n"
            f"Given the conversation so far, do you want to respond? "
            f"Answer with ONLY 'YES' or 'NO' based on whether you have something meaningful to say."
        )
        
        try:
            response = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=10
            )
            
            wants_to = response.strip().upper().startswith("YES")
            logger.info(f"{self.name} wants to respond: {wants_to}")
            return wants_to
            
        except Exception as e:
            logger.error(f"Error checking if {self.name} wants to respond: {e}")
            return False
    
    def respond(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Generate a response from this character.
        
        Args:
            conversation_history: List of conversation messages
            
        Returns:
            Character's response
        """
        logger.info(f"{self.name} is responding...")
        
        system_prompt = self.get_system_prompt()
        
        response = self.client.send_message(
            system_prompt=system_prompt,
            messages=conversation_history,
            max_tokens=500
        )
        
        logger.info(f"{self.name} responded: {response}")
        return response


class Narrator:
    """Controls turn-taking when multiple characters want to respond."""
    
    def __init__(self, client: ClaudeClient):
        """
        Initialize the narrator.
        
        Args:
            client: Claude API client
        """
        self.client = client
        logger.info("Narrator initialized")
    
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
            f"You are a narrator managing a conversation between characters: {character_names}.\n"
            f"Based on the conversation flow and context, who should speak next?\n"
            f"Respond with ONLY the name of the character who should speak."
        )
        
        try:
            choice = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=20
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


class Conversation:
    """Manages the overall conversation simulation."""
    
    def __init__(self, characters: List[Character], narrator: Narrator, opening_scene: str):
        """
        Initialize conversation.
        
        Args:
            characters: List of all characters
            narrator: Narrator instance
            opening_scene: Opening situation/prompt
        """
        self.characters = characters
        self.narrator = narrator
        self.opening_scene = opening_scene
        self.history: List[Dict[str, str]] = []
        
        logger.info("Conversation initialized")
        logger.info(f"Characters: {[c.name for c in characters]}")
        logger.info(f"Opening scene: {opening_scene}")
    
    def start(self, max_turns: int = 10):
        """
        Start the conversation simulation.
        
        Args:
            max_turns: Maximum number of conversation turns
        """
        print("\n" + "=" * 80)
        print("CONVERSATION START")
        print("=" * 80)
        print(f"\n{self.opening_scene}\n")
        
        # Add opening scene to history
        self.history.append({
            "role": "user",
            "content": self.opening_scene
        })
        
        for turn in range(max_turns):
            logger.info(f"\n--- TURN {turn + 1} ---")
            print(f"\n--- Turn {turn + 1} ---\n")
            
            # Check which characters want to respond
            interested_characters = []
            for character in self.characters:
                if character.wants_to_respond(self.history):
                    interested_characters.append(character)
            
            if not interested_characters:
                logger.info("No characters want to respond. Conversation ended.")
                print("\n[No one has anything more to say. Conversation ended.]\n")
                break
            
            # Narrator chooses who speaks
            speaker = self.narrator.choose_next_speaker(interested_characters, self.history)
            
            if not speaker:
                logger.warning("Narrator couldn't choose a speaker. Ending conversation.")
                break
            
            # Character responds
            response = speaker.respond(self.history)
            
            # Display response
            print(f"{speaker.name}: {response}\n")
            
            # Add to history
            self.history.append({
                "role": "assistant",
                "content": f"{speaker.name}: {response}"
            })
            
            # Add user acknowledgment to continue conversation
            self.history.append({
                "role": "user",
                "content": "Continue the conversation."
            })
        
        print("=" * 80)
        print("CONVERSATION END")
        print("=" * 80)
        logger.info("Conversation simulation completed")
