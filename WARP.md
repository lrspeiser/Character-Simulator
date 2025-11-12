# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

A conversational simulator where book characters engage in dynamic conversations. Each character is powered by its own Claude LLM instance with unique backstory and personality. A narrator LLM manages turn-taking when multiple characters want to respond.

## Essential Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Then edit .env and add your ANTHROPIC_API_KEY
```

### Running
```bash
# Run the Nexus Labs scenario with GUI (default)
python -m src.book_chat.main

# Run with custom config
CONFIG_PATH=configs/my_scenario.yaml python -m src.book_chat.main

# Run in CLI mode (no GUI)
# Add use_gui: false to your config YAML
```

**GUI Mode** (default):
- Chat window with colored bubbles for each character
- Narrator descriptions in italic gray text
- Character dialogue in colored bubbles with names
- Streaming text appears in real-time
- **Press SPACE to advance** to the next turn (narrator + character)
- Click "Quit Conversation" button to exit
- Large, readable fonts (Arial 14pt)
- 1000x800 window with clean spacing

**CLI Mode**:
- Text streams to terminal
- Type 'Q' and press Enter to quit

## Architecture

### Three-Tier LLM System
- **Character LLMs**: Each character has its own Claude instance with a unique system prompt built from backstory + personality
- **Narrator LLM**: Separate Claude instance that chooses which character speaks next when multiple want to respond
- **Conversation Manager**: Orchestrates the flow, checks who wants to respond, gets narrator decisions, and maintains conversation history

### Key Files
- `src/book_chat/anthropic_client.py` - Claude API wrapper with streaming support and token counting
- `src/book_chat/core.py` - Character, Narrator, and Conversation classes with history management
- `src/book_chat/gui.py` - tkinter-based chat window with colored bubbles
- `src/book_chat/main.py` - Entry point, loads config and starts conversation
- `configs/nexus_labs.yaml` - Nexus Labs scenario configuration
- `configs/CHARACTER_*_BACKSTORY.txt` - Individual character backstory files
- `configs/NARRATOR_GUIDE.txt` - Narrator guide with story context and dramatic beats

### Message Flow
1. Opening scene added to conversation history and displayed (narrator)
2. Each turn:
   - Check for user quit (button click in GUI or 'Q' in CLI)
   - Trim history to 20k token limit (keeps most recent)
   - All characters check if they `wants_to_respond()` via LLM call
   - Narrator's `choose_next_speaker()` decides who speaks (using guide for dramatic tension)
3. **Narrator describes the scene** (body language, environment, tension) - streams in italic gray
4. **Character speaks their dialogue** (only words, no actions) - streams in colored bubble
5. Both responses added to history
6. Cycle continues until max_turns, no responses, or user quits

### API Integration
- **API Key**: Stored in `.env` as `ANTHROPIC_API_KEY` (see .env.example for setup)
- **Model**: Default is `claude-sonnet-4-20250514` (latest Claude Sonnet)
- **Streaming**: Character responses stream to CLI in real-time using `client.messages.stream()`
- **Token Management**: History limited to 20k tokens, automatically trims oldest messages
- **No Temperature**: Code intentionally omits temperature parameter from API calls
- **Error Handling**: Errors are logged verbosely and re-raised (never hidden with fallbacks)
- **Reference**: Comments point to https://docs.anthropic.com/claude/reference/messages_post

## Configuration

### Scenario Configuration (YAML)
Edit config files like `configs/nexus_labs.yaml`:
- `model`: Claude model to use
- `max_turns`: Maximum conversation turns (default: 50)
- `use_gui`: Whether to use GUI (default: true) or CLI mode
- `opening_scene`: Opening narration that sets the scene
- `narrator_guide`: Path to narrator guide file
- `characters`: List with `name` and `backstory_file` for each character

### Character Backstory Files
Create separate `.txt` files for each character containing:
- NAME and ROLE
- Current situation
- Who they are (background)
- What they know (information they have)
- What they don't know (meta-instructions)
- Personality traits
- Their secret (hidden motivation/conflict)

The entire backstory file becomes the character's system prompt.

### Narrator Guide Files
Create `.txt` files for narrator containing:
- Overall story setup
- The truth (what narrator knows but characters don't)
- Current situation context
- Role as narrator (pacing, tension, environmental descriptions)
- Scene settings available
- Dramatic beats to hit
- Narrative tension goals

## Logging

All logging is set to DEBUG level in anthropic_client.py. Every API call logs:
- System prompt
- Messages sent
- Response ID, model, stop_reason
- Token usage
- Full response text
- Any errors with exception type and details
