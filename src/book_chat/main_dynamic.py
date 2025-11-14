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
from .gui import ChatWindow

logger = logging.getLogger(__name__)


def get_story_prompt_from_gui() -> str:
    """Show a simple dialog to get story prompt from user."""
    import tkinter as tk
    from tkinter import scrolledtext
    
    prompt_result = {"value": None}
    
    def on_submit():
        prompt_result["value"] = text_area.get("1.0", tk.END).strip()
        dialog.destroy()
    
    def on_cancel():
        dialog.destroy()
        sys.exit(0)
    
    dialog = tk.Tk()
    dialog.title("Describe Your Story")
    dialog.geometry("600x400")
    
    # Title
    title_label = tk.Label(
        dialog,
        text="What story would you like to experience?",
        font=('Helvetica', 14, 'bold'),
        pady=10
    )
    title_label.pack()
    
    # Instructions
    instruction_label = tk.Label(
        dialog,
        text="Describe the story concept, setting, or scenario.\nThe narrator will create characters and the opening scene.",
        font=('Helvetica', 10),
        pady=5,
        fg='#666666'
    )
    instruction_label.pack()
    
    # Text area
    text_area = scrolledtext.ScrolledText(
        dialog,
        wrap=tk.WORD,
        width=60,
        height=12,
        font=('Arial', 11),
        padx=10,
        pady=10
    )
    text_area.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert("1.0", "Example: A murder mystery on a space station where three crew members are trapped during a lockdown...")
    text_area.focus()
    
    # Buttons
    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=10)
    
    cancel_btn = tk.Button(
        button_frame,
        text="Cancel",
        command=on_cancel,
        width=10,
        bg='#E57373',
        fg='white',
        font=('Helvetica', 10, 'bold')
    )
    cancel_btn.pack(side=tk.LEFT, padx=5)
    
    submit_btn = tk.Button(
        button_frame,
        text="Create Story",
        command=on_submit,
        width=15,
        bg='#4CAF50',
        fg='white',
        font=('Helvetica', 10, 'bold')
    )
    submit_btn.pack(side=tk.LEFT, padx=5)
    
    dialog.mainloop()
    
    return prompt_result["value"]


def main():
    """Main entry point for dynamic story mode."""
    # Load environment variables from .env
    load_dotenv()
    
    # Set logging level
    logging.getLogger().setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.WARNING)
    
    # Get story prompt from user
    story_prompt = get_story_prompt_from_gui()
    
    if not story_prompt:
        print("No story prompt provided. Exiting.")
        sys.exit(0)
    
    print(f"Generating story from prompt: {story_prompt}")
    
    # Initialize Claude client
    model = os.getenv("MODEL", "claude-sonnet-4-20250514")
    client = ClaudeClient(model=model)
    
    # Create narrator (no guide file - dynamic mode)
    narrator = Narrator(client=client)
    
    # Generate story setup
    print("Narrator is creating your story...")
    try:
        setup = narrator.generate_story_setup(story_prompt)
    except Exception as e:
        print(f"Error generating story: {e}")
        sys.exit(1)
    
    opening_scene = setup.get("opening_scene", "")
    character_data = setup.get("characters", [])
    
    if not opening_scene or not character_data:
        print("Narrator failed to generate complete story. Please try again.")
        sys.exit(1)
    
    print(f"Story created with {len(character_data)} characters!")
    
    # Create Character objects
    characters = []
    character_names = []
    character_backstories = {}
    
    for char_data in character_data:
        name = char_data.get("name", "Unknown")
        backstory = char_data.get("backstory", "")
        
        character = Character(
            name=name,
            backstory=backstory,
            client=client
        )
        characters.append(character)
        character_names.append(name)
        character_backstories[name] = backstory
    
    # Create GUI window
    gui = ChatWindow(
        title="Interactive Story",
        characters=character_names,
        character_backstories=character_backstories
    )
    
    # Create conversation
    conversation = Conversation(
        characters=characters,
        narrator=narrator,
        opening_scene=opening_scene,
        client=client,
        gui_window=gui
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
