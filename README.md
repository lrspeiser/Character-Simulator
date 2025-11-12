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

2. Configure your Claude API key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your Claude API key. See `.env.example` for instructions on how to obtain one.

3. Edit character configurations in `configs/characters.yaml` to define your characters and opening scene.

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

Edit `configs/characters.yaml` to:
- Define character names, backstories, and personalities
- Set the opening scene or situation
- Adjust narrator behavior

## API Reference

See [Claude API Documentation](https://docs.anthropic.com/claude/reference/messages_post) for the latest API structure.
