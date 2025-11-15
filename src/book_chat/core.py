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
    
    def __init__(self, name: str, backstory: str, client: ClaudeClient, backstory_file: str = None):
        """
        Initialize a character.
        
        Args:
            name: Character's name
            backstory: Character's backstory text (or None to load from file)
            client: Claude API client
            backstory_file: Optional path to backstory file (legacy mode)
        """
        self.name = name
        self.backstory_file = backstory_file
        self.client = client
        
        # Load backstory from file if provided, otherwise use text directly
        if backstory_file:
            with open(backstory_file, 'r') as f:
                self.backstory = f.read()
            logger.info(f"Character created: {name} (from file: {backstory_file})")
        else:
            self.backstory = backstory
            logger.info(f"Character created: {name} (dynamic backstory)")
    
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
            f"RESPONSE FORMAT (JSON with dialogue + optional behavior):\n\n"
            f"Required field:\n"
            f"- dialogue: The words you speak out loud (NO actions mixed in)\n\n"
            f"Optional field:\n"
            f"- behavior: How you act/move/react (body language, tone, physical actions)\n"
            f"  This helps the narrator describe the scene\n\n"
            f"CORRECT examples:\n"
            f'✓ {{"dialogue": "What triggered the lockdown?", "behavior": "voice cracks, glances nervously at phone"}}\n'
            f'✓ {{"dialogue": "Someone accessed my files at 9:23 PM.", "behavior": "stands up abruptly, voice tight with anger"}}\n'
            f'✓ {{"dialogue": "Are you seriously suggesting I did this?"}}\n\n'
            f"WRONG examples (actions mixed into dialogue):\n"
            f'✗ {{"dialogue": "I pause, then say what triggered the lockdown?"}}\n'
            f'✗ {{"dialogue": "*crosses arms* Are you suggesting this?"}}\n'
            f'✗ I pause, then say "What triggered the lockdown?"\n\n'
            f"Respond with 1-3 sentences of dialogue as {self.name} would naturally say."
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
        
        # Get full response with JSON prefill to enforce strict JSON format
        # Per Anthropic docs: prefilling bypasses preamble and enforces structure
        response = self.client.send_message(
            system_prompt=system_prompt,
            messages=conversation_history,
            max_tokens=300,
            stream=False,
            assistant_prefill='{"dialogue": "'
        )
        
        # Parse JSON response
        # Response includes prefill: {"dialogue": "... so we need to complete and parse it
        # The response should be valid JSON now due to prefill
        try:
            # Response is already prefilled with {"dialogue": " so it should be valid JSON
            parsed = json.loads(response)
            dialogue = parsed.get("dialogue", "")
            behavior = parsed.get("behavior", None)
        except json.JSONDecodeError as e:
            # Fallback: try to extract dialogue from malformed response
            logger.warning(f"JSON parse error: {e}. Response: {response[:200]}")
            # Try to extract dialogue between quotes
            if '"dialogue":' in response:
                try:
                    # Extract dialogue value
                    start = response.find('"dialogue":') + len('"dialogue":')
                    rest = response[start:].strip()
                    if rest.startswith('"'):
                        end = rest.find('"', 1)
                        dialogue = rest[1:end] if end != -1 else rest[1:]
                    else:
                        dialogue = response
                    behavior = None
                except Exception:
                    dialogue = response
                    behavior = None
            else:
                dialogue = response
                behavior = None
        
        if behavior:
            logger.info(f"{self.name} responded: {dialogue} [behavior: {behavior}]")
        else:
            logger.info(f"{self.name} responded: {dialogue}")
        
        # Now stream just the dialogue to GUI/CLI if callback provided
        if stream_callback:
            # Stream dialogue character by character to GUI
            for char in dialogue:
                stream_callback(char)
        else:
            # CLI mode - print dialogue with character name prefix
            print(f"\n{self.name}: {dialogue}")
        
        # Return both dialogue and behavior as tuple
        return (dialogue, behavior)


class Narrator:
    """Controls turn-taking and story generation."""
    
    def __init__(self, client: ClaudeClient, guide_file: str = None):
        """
        Initialize the narrator.
        
        Args:
            client: Claude API client
            guide_file: Optional path to narrator guide file (for pre-defined stories)
        """
        self.client = client
        self.guide_file = guide_file
        self.guide = None
        
        # Load narrator guide if provided (for legacy mode)
        if guide_file:
            with open(guide_file, 'r') as f:
                self.guide = f.read()
            logger.info(f"Narrator initialized with guide: {guide_file}")
        else:
            logger.info("Narrator initialized in dynamic story mode")
    def generate_story_setup(self, story_prompt: str) -> dict:
        """Generate initial story setup from a user prompt.

        Args:
            story_prompt: User's description of the story they want

        Returns:
            Dict with 'title', 'opening_scene', 'characters' list (each with 'name' and 'backstory')
        """
        logger.info(f"Generating story setup from prompt: {story_prompt}")

        system_prompt = (
            "You are a master storyteller and narrator. Given a story concept, create an evocative story title, "
            "an engaging opening scene, and 2-4 initial characters with detailed backstories.\n\n"
            "CRITICAL: Each character's backstory is ONLY what THAT character knows. NEVER include information "
            "about other characters' secrets, hidden motivations, or things this character doesn't know. "
            "The backstory is the character's internal knowledge and perspective ONLY.\n\n"
            "RESPOND WITH JSON in this exact format (no extra fields, no prose):\n"
            '{"title": "Short, evocative story title (e.g. \\"Lockdown at Nexus Labs\\")",\n'
            ' "opening_scene": "A vivid 2-3 paragraph opening that sets the scene, introduces the situation, '
            'and creates tension or intrigue.",\n'
            ' "characters": [\n'
            '   {"name": "Character Name", "backstory": "WHO THIS CHARACTER IS: their role, personality, '
            'speaking style, background.\\n\\nWHAT THIS CHARACTER KNOWS: facts, observations, suspicions they have. '
            'ONLY information this specific character would know.\\n\\nWHAT THIS CHARACTER WANTS: their goals, '
            'motivations, desires.\\n\\nTHIS CHARACTER\'S SECRET: something they\'re hiding, if any. '
            '3-5 paragraphs total.", "voice_description": "Detailed voice description for ElevenLabs Text-to-Speech, 20-200 chars"},\n'
            '   {"name": "Character Name 2", "backstory": "...", "voice_description": "..."}\n'
            ' ]}\n\n'
            "Guidelines for backstories:\n"
            "- Write each backstory from THAT character's perspective only\n"
            "- NEVER write \"what they don't know is...\" followed by plot secrets\n"
            "- NEVER reveal other characters' hidden information\n"
            "- DO include: their own secrets, observations, beliefs, suspicions\n"
            "- DO include: what they've personally witnessed or been told\n"
            "- DON'T include: omniscient narrator knowledge or other characters' secrets\n"
            "- Make each character's knowledge asymmetric - they know different things\n\n"
            "Guidelines for voice_description (for ElevenLabs Text-to-Speech):\n"
            "- Provide a DETAILED description (20-200 characters) suitable for voice generation\n"
            "- CRITICAL: Start with gender (male/female) as the FIRST word for accurate voice generation\n"
            "- Include: gender (FIRST), age range, accent/nationality, tone/mood, speaking style\n"
            "- Examples:\n"
            "  * \"Female professional scientist, mid-30s, American accent, anxious but controlled tone\"\n"
            "  * \"Male authoritative security chief, deep gravelly voice, mid-40s, commanding tone\"\n"
            "  * \"Female young curious child, 8-10 years old, British accent, energetic and playful\"\n"
            "  * \"Male gruff detective, 50s, Brooklyn accent, tired but determined\"\n"
            "- This description will be used by ElevenLabs to design a custom voice if needed\n"
            "- Be specific but concise (20-200 chars)\n"
            "- ALWAYS start with 'Male' or 'Female' as the very first word\n\n"
            "Guidelines for opening scene:\n"
            "- Opening scene should be vivid, cinematic, and create immediate engagement\n"
            "- Create natural conflict or tension between characters\n"
            "- Make characters distinct in personality and speaking style\n\n"
            "WRONG backstory example (information leak):\n"
            '"Detective Marsh is investigating the murder. What he doesn\'t know is that Dr. Chen is the killer." ❌\n\n'
            "CORRECT backstory example (character perspective only):\n"
            '"Detective Marsh is investigating the murder. He suspects the victim knew their killer. '
            'He noticed Dr. Chen seemed nervous during questioning." ✓'
        )

        try:
            response = self.client.send_message(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": f"Story concept: {story_prompt}"}],
                max_tokens=3000,
                stream=False,
                assistant_prefill='{"title": "'
            )

            # Parse JSON response
            try:
                setup = json.loads(response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse story setup JSON: {e}")
                logger.error(f"Response: {response[:500]}")
                raise ValueError("Narrator failed to generate valid story setup")

            title = (setup.get("title") or "").strip()
            if not title:
                logger.error(f"Story setup JSON missing non-empty 'title'. Raw response: {str(setup)[:500]}")
                raise ValueError("Narrator failed to generate story title")

            logger.info(
                "Generated story '%s' with %d characters",
                title,
                len(setup.get("characters", [])),
            )
            return setup

        except Exception as e:
            logger.error(f"Error generating story setup: {e}")
            raise
    
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
            f"FORMAT: Respond with JSON in this exact format:\n\n"
            f"CORRECT examples:\n"
            f'✓ {{"next_speaker": "Dr. Sarah Chen"}}\n'
            f'✓ {{"next_speaker": "Marcus Webb"}}\n'
            f'✓ {{"next_speaker": "Victoria Reeves"}}\n\n'
            f"WRONG examples:\n"
            f'✗ {{"next_speaker": "Marcus Webb: He should go next"}}\n'
            f'✗ {{"next_speaker": "I think Dr. Sarah Chen"}}\n'
            f'✗ Dr. Sarah Chen\n\n'
            f"The next_speaker value must be EXACTLY one of: {', '.join(character_names)}"
        )
        
        try:
            choice = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=50,
                stream=False,
                assistant_prefill='{"next_speaker": "'
            )
            
            logger.info(f"Narrator choice raw response: {choice}")
            
            # Parse JSON response (prefilled with {"next_speaker": ")
            try:
                parsed = json.loads(choice)
                choice_name = parsed.get("next_speaker", "").strip()
                logger.info(f"Parsed next_speaker: '{choice_name}'")
            except json.JSONDecodeError as e:
                # Fallback: extract name from response
                logger.error(f"JSON parse error in narrator choice: {e}")
                logger.error(f"Raw choice response: {choice}")
                choice_name = choice.strip().strip('"}')
                logger.info(f"Fallback extracted name: '{choice_name}'")
            
            # Find matching character (exact match first)
            logger.info(f"Attempting to match choice_name='{choice_name}' against characters: {[c.name for c in characters]}")
            
            for character in characters:
                if character.name.lower() == choice_name.lower():
                    logger.info(f"✓ Narrator chose (exact match): {character.name}")
                    return character
            
            # Try partial match
            logger.warning(f"No exact match for '{choice_name}', trying partial match")
            for character in characters:
                if character.name.lower() in choice_name.lower() or choice_name.lower() in character.name.lower():
                    logger.warning(f"✓ Narrator chose (partial match): {character.name} (from choice '{choice_name}')")
                    return character
            
            # Default to first if no match
            logger.error(f"✗ FALLBACK: Narrator choice '{choice_name}' didn't match any character!")
            logger.error(f"Available characters were: {[c.name for c in characters]}")
            logger.error(f"Defaulting to first character: {characters[0].name}")
            return characters[0]
            
        except Exception as e:
            logger.error(f"Error in narrator choice: {e}")
            logger.info(f"Defaulting to first character: {characters[0].name}")
            return characters[0]
    
    def generate_player_suggestions(self, conversation_history: List[Dict[str, str]], character_name: str) -> list:
        """
        Generate director-style suggestions for the player's next line.
        See WARP.md for API key setup and model configuration.
        
        Args:
            conversation_history: Conversation so far
            character_name: Name of the character the player is controlling
            
        Returns:
            List of suggestion strings (3-5 items), or empty list if generation fails
        """
        logger.info(f"Generating player suggestions for {character_name}...")
        
        # Build system prompt for director suggestions
        guide_context = f"{self.guide}\n\n" if self.guide else ""
        system_prompt = (
            f"{guide_context}"
            f"You are the Narrator-Director. Generate 3-5 concise bullet suggestions to guide "
            f"the next line for {character_name}.\n\n"
            f"Cover:\n"
            f"- Emotional state or feeling right now\n"
            f"- Intent or goal for this moment\n"
            f"- Optional sample dialogue angles or questions they might ask\n\n"
            f"Base suggestions on:\n"
            f"- Current conversation context\n"
            f"- What was just said by other characters\n"
            f"- The character's personality and situation\n"
            f"- Dramatic tension and story flow\n\n"
            f"FORMAT: Respond with strict JSON only (no prose, no markdown, no code fences):\n\n"
            f"CORRECT examples:\n"
            f'✓ {{"suggestions": ["Feeling: Anxious about the lockdown implications", '
            f'"Intent: Press for more details about what triggered this", '
            f'"Angle: Ask who has access to the system logs"]}}\n'
            f'✓ {{"suggestions": ["Emotional state: Defensive and suspicious", '
            f'"Goal: Shift focus away from yourself", '
            f'"Sample: Challenge their authority or question their timeline"]}}\n\n'
            f"WRONG examples:\n"
            f'✗ Here are some suggestions: {{"suggestions": [...]}}\n'
            f'✗ ```json\\n{{"suggestions": [...]}}```\n'
            f'✗ {{"suggestions": "feeling anxious"}}\n\n'
            f"Provide 3-5 brief, actionable suggestions that help the player embody {character_name}."
        )
        
        try:
            logger.debug(f"Director suggestions system prompt: {system_prompt[:300]}...")
            
            # Call Claude with JSON prefill to enforce format
            # Per project rules: no temperature parameter
            # See https://docs.anthropic.com/claude/reference/messages_post
            response = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=300,
                stream=False,
                assistant_prefill='{"suggestions": ["'
            )
            
            logger.debug(f"Director suggestions raw response: {response}")
            
            # Parse JSON response (prefilled with {"suggestions": [")
            try:
                parsed = json.loads(response)
                suggestions = parsed.get("suggestions", [])
                
                if not isinstance(suggestions, list):
                    logger.error(f"Suggestions field is not a list: {suggestions}")
                    return []
                
                logger.info(f"Generated {len(suggestions)} suggestions for {character_name}")
                logger.debug(f"Suggestions: {suggestions}")
                return suggestions
                
            except json.JSONDecodeError as e:
                # Log the error verbosely but don't crash
                logger.error(f"Failed to parse director suggestions JSON: {e}")
                logger.error(f"Raw response was: {response[:500]}")
                import traceback
                logger.error(traceback.format_exc())
                return []  # Return empty list - caller will skip display
                
        except Exception as e:
            # Log all errors verbosely per project rules
            logger.error(f"Error generating player suggestions: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []  # Return empty list - visible failure with logs
    
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
        
        # Get the last message to check for character behavior hints
        last_message_content = ""
        if conversation_history:
            last_msg = conversation_history[-1].get('content', '')
            if last_speaker in last_msg:
                last_message_content = last_msg
        
        system_prompt = (
            f"{self.guide}\n\n"
            f"You are the narrator. {last_speaker} just spoke.\n\n"
            f"Note: Characters may provide behavior hints (body language, tone, actions) to help you describe the scene.\n"
            f"Use these hints to create vivid descriptions, but expand and elaborate on them cinematically.\n\n"
            f"CRITICAL RULES:\n"
            f"1. You may ONLY provide scene description and narration\n"
            f"2. NO dialogue in quotes - characters speak for themselves\n"
            f"3. NO \"he said\" or \"she replied\" - just describe the scene\n"
            f"4. NO character names followed by colons (e.g. NO 'Marcus Webb:')\n\n"
            f"Describe what happens next (1-2 sentences):\n"
            f"- Body language, facial expressions, physical actions\n"
            f"- Environmental details (sounds, lighting, atmosphere)\n"
            f"- Tension, mood shifts, or dramatic moments\n"
            f"- Reactions from other characters\n\n"
            f"FORMAT: Respond with JSON in this exact format:\n\n"
            f"CORRECT examples:\n"
            f'✓ {{"scene": "Webb\'s hand moves to his holster. The lights flicker."}}\n'
            f'✓ {{"scene": "The ventilation system groans overhead. Chen\'s eyes dart upward nervously."}}\n'
            f'✓ {{"scene": "Chen\'s voice cracks as she speaks, her fingers tightening around her phone. Reeves leans forward slightly."}}\n\n'
            f"WRONG examples:\n"
            f'✗ {{"scene": "Webb says, We need to talk."}}\n'
            f'✗ {{"scene": "Marcus Webb: thinking about the situation"}}\n'
            f'✗ Webb\'s hand moves to his holster.\n\n'
            f"Keep it vivid, cinematic, and concise. Only narrate - never speak as any character."
        )
        
        try:
            description = self.client.send_message(
                system_prompt=system_prompt,
                messages=conversation_history,
                max_tokens=200,
                stream=False,  # Get full response to parse JSON first
                assistant_prefill='{"scene": "'
            )
            
            # Parse JSON response (prefilled with {"scene": ")
            try:
                parsed = json.loads(description)
                scene_text = parsed.get("scene", "")
            except json.JSONDecodeError:
                # Fallback: extract scene from response
                logger.warning(f"JSON parse error in narrator scene: {description[:200]}")
                # Try to extract text between quotes
                if '"scene":' in description:
                    try:
                        start = description.find('"scene":') + len('"scene":')
                        rest = description[start:].strip()
                        if rest.startswith('"'):
                            end = rest.find('"', 1)
                            scene_text = rest[1:end] if end != -1 else rest[1:]
                        else:
                            scene_text = description
                    except Exception:
                        scene_text = description
                else:
                    scene_text = description
            
            logger.info(f"Narrator description: {scene_text}")
            return scene_text
            
        except Exception as e:
            logger.error(f"Error generating scene description: {e}")
            return ""


class Conversation:
    """Manages the overall conversation simulation."""
    
    def __init__(
        self,
        characters: List[Character],
        narrator: Narrator,
        opening_scene: str,
        client: ClaudeClient,
        gui_window=None,
        tts_client=None,
        character_voice_map: Optional[Dict[str, str]] = None,
    ):
        """Initialize conversation.

        Args:
            characters: List of all characters
            narrator: Narrator instance
            opening_scene: Opening situation/prompt
            client: Claude API client for token counting
            gui_window: Optional GUI window for display
            tts_client: Optional ElevenLabsTTS instance for audio playback
            character_voice_map: Optional mapping of character name -> ElevenLabs voice_id
        """
        self.characters = characters
        self.narrator = narrator
        self.opening_scene = opening_scene
        self.history: List[Dict[str, str]] = []
        self.client = client
        self.quit_requested = False
        self.gui = gui_window
        self.tts = tts_client
        self.character_voice_map = character_voice_map or {}
        self.last_speaker_name = None  # Track who spoke last
        self.last_turn_was_player = False  # Track if previous turn was player-controlled
        
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
        # Send opening scene to TTS narrator if enabled, with callback to display text
        if self.tts:
            try:
                logger.info("Sending opening scene to TTS narrator (%d chars)", len(self.opening_scene))
                # Display text when audio starts playing
                def display_opening():
                    if self.gui:
                        self.gui.add_message('narrator', self.opening_scene, is_narrator=True)
                    else:
                        print("\n" + "=" * 80)
                        print("LOCKDOWN AT NEXUS LABS")
                        print("=" * 80)
                        print(f"\n{self.opening_scene}\n")
                        print("\n[Type 'Q' and press Enter at any time to quit]\n")
                
                self.tts.speak_narrator(self.opening_scene, display_callback=lambda text: display_opening())
            except Exception as e:
                logger.error(f"Error sending opening scene to TTS: {e}")
        else:
            # No TTS - display immediately
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
                logger.error("CRITICAL: Narrator couldn't choose a speaker. Ending conversation.")
                logger.error(f"Interested characters were: {[c.name for c in interested_characters]}")
                if self.gui:
                    self.gui.update_status("Error: Narrator failed to choose speaker")
                break
            
            logger.info(f"Speaker selected: {speaker.name}")
            
            # Narrator decides if scene description is needed
            if turn > 0 and self.last_speaker_name:  # Skip scene description on first turn
                scene_desc = self.narrator.narrate_scene(
                    self.history, 
                    self.last_speaker_name,  # Who spoke LAST time
                    stream_callback=None  # Don't stream decision-making
                )
                
                # Only display and add to history if narrator provided description
                if scene_desc:
                    # Send scene description to TTS narrator if enabled, with callback to display text
                    if self.tts:
                        try:
                            logger.info("Sending scene description to TTS narrator (%d chars)", len(scene_desc))
                            # Display text when audio starts playing
                            def display_scene():
                                if self.gui:
                                    self.gui.start_streaming_message('narrator', is_narrator=True)
                                    # Stream the scene description
                                    for char in scene_desc:
                                        self.gui.stream_text(char)
                                    self.gui.end_streaming_message()
                                else:
                                    print(f"\n[{scene_desc}]\n")
                            
                            self.tts.speak_narrator(scene_desc, display_callback=lambda text: display_scene())
                        except Exception as e:
                            logger.error(f"Error sending scene description to TTS: {e}")
                    else:
                        # No TTS - display immediately
                        if self.gui:
                            self.gui.start_streaming_message('narrator', is_narrator=True)
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
            
            # Track if this is a player turn
            is_player_turn = False
            
            # Check if this is player's turn and generate director suggestions
            selected_character = self.gui.get_selected_character() if self.gui else None
            if selected_character and speaker.name == selected_character:
                is_player_turn = True
                
                # Generate director suggestions for the player
                suggestions = self.narrator.generate_player_suggestions(self.history, speaker.name)
                
                if suggestions:
                    # Pick the first/best suggestion as the hint
                    hint_text = suggestions[0] if suggestions else "Continue the conversation naturally."
                    
                    # Display collapsible hint link in GUI
                    if self.gui:
                        self.gui.show_hint_link(speaker.name, hint_text)
                    else:
                        # CLI mode: print hint with clear prefix
                        print(f"\n[Hint for {speaker.name}: {hint_text}]\n")

                    # NOTE: We intentionally do NOT send hints to TTS.
                    # These are tips for the human player, not part of the story audio.
                    
                    # Add hint to history so other LLMs can use it
                    self.history.append({
                        "role": "user",
                        "content": f"[Hint for {speaker.name}: {hint_text}]"
                    })
            
            # Character responds
            if self.gui:
                # Check if player is controlling this character
                if is_player_turn:
                    # Player-controlled - no streaming bubble, wait for input
                    result = speaker.respond(self.history, stream_callback=None, gui_window=self.gui)
                    # Player input returns plain string, not tuple
                    if isinstance(result, tuple):
                        dialogue, behavior = result
                    else:
                        dialogue, behavior = result, None
                    # Display player's dialogue in bubble (no TTS for player input)
                    if dialogue:
                        self.gui.add_message(speaker.name, dialogue, is_narrator=False)
                else:
                    # AI-controlled
                    if self.tts:
                        # With TTS: Generate dialogue WITHOUT displaying, display via TTS callback
                        result = speaker.respond(self.history, stream_callback=None, gui_window=self.gui)
                        if isinstance(result, tuple):
                            dialogue, behavior = result
                        else:
                            dialogue, behavior = result, None
                        # Text will be displayed when TTS plays (see below)
                    else:
                        # No TTS: Stream as normal
                        self.gui.start_streaming_message(speaker.name, is_narrator=False)
                        result = speaker.respond(self.history, stream_callback=self.gui.stream_text, gui_window=self.gui)
                        if isinstance(result, tuple):
                            dialogue, behavior = result
                        else:
                            dialogue, behavior = result, None
                        self.gui.end_streaming_message()
            else:
                result = speaker.respond(self.history, gui_window=None)
                if isinstance(result, tuple):
                    dialogue, behavior = result
                else:
                    dialogue, behavior = result, None
            
            # Add to history with behavior if provided
            if behavior:
                content = f"{speaker.name}: {dialogue} [behavior: {behavior}]"
            else:
                content = f"{speaker.name}: {dialogue}"

            # Send character dialogue to TTS if enabled
            if self.tts and dialogue:
                try:
                    voice_id = self.character_voice_map.get(speaker.name)
                    if not voice_id:
                        # Visible fallback: log and use narrator voice so the character is still audible.
                        logger.warning(
                            "No ElevenLabs voice_id for character '%s'; using narrator voice for TTS",
                            speaker.name,
                        )
                        voice_id = getattr(self.tts, "narrator_voice_id", None)
                    else:
                        logger.info(
                            "Using ElevenLabs voice_id=%s for character '%s'",
                            voice_id,
                            speaker.name,
                        )

                    if voice_id:
                        logger.info("Sending character '%s' dialogue to TTS (%d chars)", speaker.name, len(dialogue))
                        
                        # Display text when audio starts playing (if not player turn)
                        if not is_player_turn and self.gui:
                            def display_dialogue():
                                self.gui.add_message(speaker.name, dialogue, is_narrator=False)
                            
                            self.tts.speak_character(speaker.name, voice_id, dialogue, display_callback=lambda text: display_dialogue())
                        else:
                            # Player turn or CLI mode - no callback needed (already displayed)
                            self.tts.speak_character(speaker.name, voice_id, dialogue)
                except Exception as e:
                    logger.error(f"Error sending character dialogue to TTS for {speaker.name}: {e}")
            
            self.history.append({
                "role": "assistant",
                "content": content
            })
            
            # Track who spoke for next scene description
            self.last_speaker_name = speaker.name
            
            # Track if this was a player turn (to skip space-wait on next iteration)
            self.last_turn_was_player = is_player_turn
            
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
