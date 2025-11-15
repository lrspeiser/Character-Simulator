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
from .character_review import CharacterReviewWindow

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
        # Quit the event loop but keep the window alive for loading animation
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
    
    # Set up comprehensive file logging to capture all output including crashes
    log_file = Path.home() / "book_llm_chat_sim.log"
    
    # Configure root logger to write to both console and file
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handler - captures everything
    file_handler = logging.FileHandler(log_file, mode='w')  # Overwrite each run
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler - shows important info
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Redirect stdout and stderr to log file as well
    class TeeOutput:
        def __init__(self, file_handle, stream):
            self.file = file_handle
            self.stream = stream
        def write(self, data):
            self.file.write(data)
            self.file.flush()
            self.stream.write(data)
        def flush(self):
            self.file.flush()
            self.stream.flush()
    
    log_file_handle = open(log_file, 'a')
    sys.stdout = TeeOutput(log_file_handle, sys.stdout)
    sys.stderr = TeeOutput(log_file_handle, sys.stderr)
    
    logger.info("="*80)
    logger.info("APPLICATION STARTED")
    logger.info(f"Log file: {log_file}")
    logger.info("="*80)
    
    # Get story prompt from user (and keep the window alive so we can reuse it)
    logger.info(">>> Calling get_story_prompt_from_gui()")
    story_prompt, root = get_story_prompt_from_gui()
    logger.info("<<< Returned from get_story_prompt_from_gui()")
    
    if not story_prompt:
        logger.warning("No story prompt provided. Exiting.")
        print("No story prompt provided. Exiting.")
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)
    
    logger.info(f"Story prompt: {story_prompt[:100]}...")
    print(f"Generating story from prompt: {story_prompt}")
    
    # Clear the dialog content and show ASCII art loading animation
    import tkinter as tk
    from tkinter import scrolledtext
    
    # Clear all widgets from dialog
    for widget in root.winfo_children():
        widget.destroy()
    
    root.title("Generating Story...")
    root.configure(bg=BG_BLACK)
    
    # Create ASCII art display area
    ascii_canvas = scrolledtext.ScrolledText(
        root,
        wrap=tk.WORD,
        width=80,
        height=25,
        font=("Courier New", 10),
        bg=BG_BLACK,
        fg=FG_GREEN_BRIGHT,
        insertbackground=FG_GREEN_BRIGHT,
        relief=tk.FLAT,
        bd=0,
        state=tk.DISABLED,
    )
    ascii_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    # ASCII art to display character by character
    loading_art = r"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║              GENERATING YOUR STORY...                         ║
    ║                                                               ║
    ║    ███████╗████████╗ ██████╗ ██████╗ ██╗   ██╗               ║
    ║    ██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗╚██╗ ██╔╝               ║
    ║    ███████╗   ██║   ██║   ██║██████╔╝ ╚████╔╝                ║
    ║    ╚════██║   ██║   ██║   ██║██╔══██╗  ╚██╔╝                 ║
    ║    ███████║   ██║   ╚██████╔╝██║  ██║   ██║                  ║
    ║    ╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝   ╚═╝                  ║
    ║                                                               ║
    ║         Building Characters...                                ║
    ║         Crafting Dialogue...                                  ║
    ║         Designing Voices...                                   ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    
    status_text = tk.StringVar(value="")
    status_label = tk.Label(
        root,
        textvariable=status_text,
        font=FONT_SMALL,
        bg=BG_BLACK,
        fg=FG_GREEN_DIM,
    )
    status_label.pack(pady=10)
    
    # Animation state
    animation_state = {
        "index": 0,
        "running": True,
        "status_messages": [
            "Initializing narrator...",
            "Generating story structure...",
            "Creating characters...",
            "Building backstories...",
            "Designing character voices...",
            "Finalizing details...",
        ],
        "status_index": 0,
    }
    
    def animate_ascii():
        """Animate ASCII art character by character."""
        if not animation_state["running"]:
            return
        
        if animation_state["index"] < len(loading_art):
            # Add next character
            ascii_canvas.config(state=tk.NORMAL)
            char = loading_art[animation_state["index"]]
            ascii_canvas.insert(tk.END, char)
            ascii_canvas.config(state=tk.DISABLED)
            ascii_canvas.see(tk.END)
            animation_state["index"] += 1
            
            # Schedule next character (faster animation)
            root.after(5, animate_ascii)
        else:
            # Art is done, cycle through status messages
            idx = animation_state["status_index"] % len(animation_state["status_messages"])
            status_text.set(animation_state["status_messages"][idx])
            animation_state["status_index"] += 1
            root.after(800, animate_ascii)  # Update status every 800ms
    
    # Start animation in background
    root.after(50, animate_ascii)
    root.update()
    
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
    
    # Stop the loading animation
    animation_state["running"] = False
    status_text.set("Story generation complete!")
    root.update()

    # Prepare character data for review
    characters_for_review = []
    
    for char_data in character_data:
        name = char_data.get("name", "Unknown")
        backstory = char_data.get("backstory", "")
        voice_description = (char_data.get("voice_description") or "").strip()

        logger.info("Building character '%s' (has voice_description=%s)", name, bool(voice_description))

        # If TTS is enabled and a voice_description is provided, create a voice
        voice_id = None
        if tts_client and voice_description:
            logger.info("Resolving voice for '%s' using description: %s", name, voice_description[:100])
            # auto_create=True means it will design/create a new voice if search finds nothing
            voice_id = tts_client.find_or_create_voice(
                character_name=name,
                voice_description=voice_description,
                auto_create=True  # Automatically create voices in dynamic mode
            )
            if voice_id:
                logger.info("Mapped character '%s' to ElevenLabs voice_id=%s", name, voice_id)
            else:
                logger.warning("No ElevenLabs voice_id resolved for character '%s'", name)
        
        # Store all character info for review
        characters_for_review.append({
            'name': name,
            'backstory': backstory,
            'voice_description': voice_description or "No voice description",
            'voice_id': voice_id,
        })
    
    # If TTS is enabled, show character review window
    if tts_client and characters_for_review:
        # Close the prompt window
        root.destroy()
        
        # This will be set by the review window callback
        final_voice_map = {}
        review_complete_event = threading.Event()
        
        def on_review_complete(accepted_voices):
            """Called when user finishes reviewing all characters."""
            nonlocal final_voice_map
            final_voice_map = accepted_voices
            review_complete_event.set()
        
        # Show review window (blocks until all characters accepted)
        review_window = CharacterReviewWindow(
            characters_data=characters_for_review,
            tts_client=tts_client,
            on_complete=on_review_complete
        )
        review_window.run()
        
        # Wait for review to complete
        review_complete_event.wait()
        character_voice_map = final_voice_map
    else:
        # No TTS or no characters, skip review
        character_voice_map = {}
        root.destroy()
    
    # Create Character objects
    characters = []
    character_names = []
    character_backstories = {}
    
    for char_data in characters_for_review:
        name = char_data['name']
        backstory = char_data['backstory']
        
        character = Character(
            name=name,
            backstory=backstory,
            client=client
        )
        characters.append(character)
        character_names.append(name)
        character_backstories[name] = backstory
    
    # Create GUI window
    import tkinter as tk
    gui_root = tk.Tk()
    gui = ChatWindow(
        title=title,
        characters=character_names,
        character_backstories=character_backstories,
        root=gui_root,
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
        logger.info(">>> run_conversation() thread started")
        try:
            logger.info(">>> Calling conversation.start(max_turns=50)")
            conversation.start(max_turns=50)
            logger.info("<<< conversation.start() completed normally")
        except Exception as e:
            import traceback
            error_msg = f"FATAL ERROR in conversation: {e}\n{traceback.format_exc()}"
            print(error_msg)
            logger.critical(error_msg)
            logging.error(error_msg)
            try:
                gui.update_status(f"Error: {str(e)}")
            except:
                pass
        finally:
            logger.info(">>> run_conversation() finally block - closing GUI")
            try:
                gui.close()
            except Exception as e:
                logger.error(f"Error closing GUI: {e}")
            logger.info("<<< run_conversation() thread exiting")
    
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
