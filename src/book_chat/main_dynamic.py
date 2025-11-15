"""
Main entry point for dynamic story generation mode.
User provides a story prompt, narrator generates everything.
"""

import os
import sys
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv

from .anthropic_client import ClaudeClient
from .core import Character, Narrator, Conversation
from .gui import ChatWindow, BG_BLACK, BG_DARK, BG_DARK_ACTIVE, FG_GREEN_BRIGHT, FG_GREEN_DIM, FONT_MAIN, FONT_SMALL
from .tts_elevenlabs import ElevenLabsTTS

logger = logging.getLogger(__name__)


def get_story_prompt_from_gui():
    """Show a simple dialog to get story prompt from user.

    Returns:
        Tuple of (story_prompt, root_window). The root window stays alive so
        we can reuse it for the main chat UI, avoiding window flicker.
    """
    import tkinter as tk
    from tkinter import scrolledtext
    
    prompt_result = {"value": None}
    
    def on_submit():
        # Capture prompt text
        prompt_result["value"] = text_area.get("1.0", tk.END).strip()
        # Update UI to indicate processing while we generate the story
        status_label.config(text="Creating your story...")
        text_area.config(state=tk.DISABLED)
        cancel_btn.config(cursor="watch")
        submit_btn.config(cursor="watch")
        dialog.update_idletasks()
        # Quit the event loop but keep the window alive so it stays visible
        dialog.quit()
    
    def on_cancel():
        dialog.destroy()
        sys.exit(0)
    
    dialog = tk.Tk()
    dialog.title("Describe Your Story")
    dialog.geometry("600x400")
    # Apply global green-screen palette so buttons and other widgets use black background
    dialog.tk_setPalette(
        background=BG_BLACK,
        foreground=FG_GREEN_BRIGHT,
        activeBackground=BG_DARK,
        activeForeground=FG_GREEN_BRIGHT,
    )
    dialog.configure(bg=BG_BLACK)
    
    # Title
    title_label = tk.Label(
        dialog,
        text="What story would you like to experience?",
        font=("Courier New", 14, 'bold'),
        pady=10,
        bg=BG_BLACK,
        fg=FG_GREEN_BRIGHT,
    )
    title_label.pack()
    
    # Instructions
    instruction_label = tk.Label(
        dialog,
        text="Describe the story concept, setting, or scenario.\nThe narrator will create characters and the opening scene.",
        font=FONT_SMALL,
        pady=5,
        bg=BG_BLACK,
        fg=FG_GREEN_DIM,
    )
    instruction_label.pack()
    
    # Text area
    text_area = scrolledtext.ScrolledText(
        dialog,
        wrap=tk.WORD,
        width=60,
        height=12,
        font=FONT_MAIN,
        bg=BG_BLACK,
        fg=FG_GREEN_BRIGHT,
        insertbackground=FG_GREEN_BRIGHT,
        relief=tk.SUNKEN,
        bd=1,
        highlightthickness=1,
        highlightbackground=FG_GREEN_BRIGHT,
        highlightcolor=FG_GREEN_BRIGHT,
        padx=10,
        pady=10
    )
    text_area.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert("1.0", "Example: A murder mystery on a space station where three crew members are trapped during a lockdown...")
    text_area.focus()
    
    # Status label (updated when submitting)
    status_label = tk.Label(
        dialog,
        text="",
        font=FONT_SMALL,
        pady=5,
        bg=BG_BLACK,
        fg=FG_GREEN_DIM,
    )
    status_label.pack()
    
    # Buttons
    button_frame = tk.Frame(dialog, bg=BG_BLACK)
    button_frame.pack(pady=10)

    def make_green_button(parent, text, command, width=None):
        """Create a label-based button that respects custom colors on all platforms."""
        btn = tk.Label(
            parent,
            text=text,
            bg=BG_BLACK,
            fg=FG_GREEN_BRIGHT,
            font=FONT_SMALL,
            bd=1,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=FG_GREEN_BRIGHT,
            highlightcolor=FG_GREEN_BRIGHT,
            padx=10,
            pady=5,
            cursor="hand2",
        )
        if width is not None:
            btn.config(width=width)

        def on_enter(_event):
            btn.config(bg=BG_DARK)

        def on_leave(_event):
            btn.config(bg=BG_BLACK)

        def on_click(_event):
            command()

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<Button-1>", on_click)
        return btn

    cancel_btn = make_green_button(
        button_frame,
        text="Cancel",
        command=on_cancel,
        width=10,
    )
    cancel_btn.pack(side=tk.LEFT, padx=5)

    submit_btn = make_green_button(
        button_frame,
        text="Create Story",
        command=on_submit,
        width=15,
    )
    submit_btn.pack(side=tk.LEFT, padx=5)
    
    dialog.mainloop()
    
    return prompt_result["value"], dialog


def main():
    """Main entry point for dynamic story mode."""
    # Load environment variables from .env
    load_dotenv()
    
    # Set logging level (INFO so TTS / voice mapping logs are visible during GUI runs)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers:
        handler.setLevel(logging.INFO)
    
    # Get story prompt from user (and keep the window alive so we can reuse it)
    story_prompt, root = get_story_prompt_from_gui()
    
    if not story_prompt:
        print("No story prompt provided. Exiting.")
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)
    
    print(f"Generating story from prompt: {story_prompt}")
    
    # Initialize Claude client
    model = os.getenv("MODEL", "claude-sonnet-4-20250514")
    client = ClaudeClient(model=model)

    # Initialize ElevenLabs TTS (optional - requires ELEVENLABS_API_KEY)
    tts_client = None
    try:
        if os.getenv("ELEVENLABS_API_KEY"):
            # See README.md ("ElevenLabs TTS") for setup details
            logger.info("ELEVENLABS_API_KEY detected; initializing ElevenLabs TTS client")
            tts_client = ElevenLabsTTS()
            logger.info("ElevenLabs TTS client initialized successfully in dynamic mode")
        else:
            logger.warning("ELEVENLABS_API_KEY not set; ElevenLabs TTS will be disabled for this run.")
    except Exception as e:
        logger.error(f"Failed to initialize ElevenLabs TTS: {e}")
        tts_client = None

    # Create narrator (no guide file - dynamic mode)
    narrator = Narrator(client=client)

    # Generate story setup
    print("Narrator is creating your story...")
    try:
        setup = narrator.generate_story_setup(story_prompt)
    except Exception as e:
        print(f"Error generating story: {e}")
        sys.exit(1)

    title = (setup.get("title") or "").strip()
    opening_scene = setup.get("opening_scene", "")
    character_data = setup.get("characters", [])

    if not title or not opening_scene or not character_data:
        print("Narrator failed to generate a complete story (missing title, opening scene, or characters). Please try again.")
        logger.error(f"Invalid story setup returned from narrator: {setup}")
        sys.exit(1)

    print(f"Story created: '{title}' with {len(character_data)} characters!")

    # Create Character objects and optional ElevenLabs voice mapping
    characters = []
    character_names = []
    character_backstories = {}
    character_voice_map = {}
    
    for char_data in character_data:
        name = char_data.get("name", "Unknown")
        backstory = char_data.get("backstory", "")
        voice_search = (char_data.get("voice_search") or "").strip().lower()

        logger.info("Building character '%s' (has voice_search=%s)", name, bool(voice_search))

        character = Character(
            name=name,
            backstory=backstory,
            client=client
        )
        characters.append(character)
        character_names.append(name)
        character_backstories[name] = backstory

        # If TTS is enabled and a voice_search hint is provided, try to resolve a voice ID
        if tts_client and voice_search:
            logger.info("Resolving ElevenLabs voice for character '%s' using search '%s'", name, voice_search)
            voice_id = tts_client.find_voice_id(voice_search)
            if voice_id:
                logger.info("Mapped character '%s' to ElevenLabs voice_id=%s", name, voice_id)
                character_voice_map[name] = voice_id
            else:
                logger.warning("No ElevenLabs voice_id found for character '%s' (search='%s')", name, voice_search)
    
    # Create GUI window, reusing the original prompt window so the UI
    # stays in a single window instead of flashing multiple windows.
    gui = ChatWindow(
        title=title,
        characters=character_names,
        character_backstories=character_backstories,
        root=root,
    )
    
    # Create conversation
    conversation = Conversation(
        characters=characters,
        narrator=narrator,
        opening_scene=opening_scene,
        client=client,
        gui_window=gui,
        tts_client=tts_client,
        character_voice_map=character_voice_map,
    )
    
    # Run conversation in separate thread with error handling
    def run_conversation():
        try:
            conversation.start(max_turns=50)
        except Exception as e:
            import traceback
            error_msg = f"Error in conversation: {e}\n{traceback.format_exc()}"
            print(error_msg)
            logging.error(error_msg)
            gui.update_status(f"Error: {str(e)}")
        finally:
            gui.close()
    
    conversation_thread = threading.Thread(target=run_conversation, daemon=True)
    conversation_thread.start()
    
    # Run GUI main loop (blocks until window closes)
    try:
        gui.run()
    except Exception as e:
        import traceback
        print(f"GUI Error: {e}\n{traceback.format_exc()}")
        logging.error(f"GUI Error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
