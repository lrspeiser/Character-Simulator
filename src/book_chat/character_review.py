"""Character review UI for voice preview and regeneration.

This module provides a GUI that displays generated characters one at a time,
allows the user to preview their voice, regenerate it if needed, and accept
it before moving to the next character.
"""

import tkinter as tk
from tkinter import scrolledtext
import logging
import threading

from .gui import BG_BLACK, BG_DARK, BG_DARK_ACTIVE, FG_GREEN_BRIGHT, FG_GREEN_DIM, FG_GREEN_ALT1, FONT_MAIN, FONT_SMALL

logger = logging.getLogger(__name__)


class CharacterReviewWindow:
    """GUI window for reviewing and accepting character voices."""
    
    def __init__(self, characters_data: list, tts_client, on_complete):
        """Initialize the character review window.
        
        Args:
            characters_data: List of dicts with 'name', 'backstory', 'voice_description', 'voice_id'
            tts_client: ElevenLabsTTS instance for voice preview/regeneration
            on_complete: Callback function(character_voice_map) called when all accepted
        """
        self.characters_data = characters_data
        self.tts_client = tts_client
        self.on_complete = on_complete
        self.current_index = 0
        self.accepted_voices = {}  # character_name -> voice_id
        self.is_generating = False
        
        self.root = tk.Tk()
        self.root.title("Review Characters")
        self.root.geometry("800x700")
        self.root.configure(bg=BG_BLACK)
        
        # Apply global palette
        self.root.tk_setPalette(
            background=BG_BLACK,
            foreground=FG_GREEN_BRIGHT,
            activeBackground=BG_DARK,
            activeForeground=FG_GREEN_BRIGHT,
        )
        
        self._setup_ui()
        self._show_current_character()
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Title
        title_label = tk.Label(
            self.root,
            text="CHARACTER REVIEW",
            font=("Courier New", 18, "bold"),
            bg=BG_BLACK,
            fg=FG_GREEN_BRIGHT,
        )
        title_label.pack(pady=(20, 10))
        
        # Progress label
        self.progress_label = tk.Label(
            self.root,
            text="",
            font=FONT_SMALL,
            bg=BG_BLACK,
            fg=FG_GREEN_DIM,
        )
        self.progress_label.pack(pady=(0, 20))
        
        # Character info frame
        info_frame = tk.Frame(self.root, bg=BG_BLACK)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=10)
        
        # Character name
        self.name_label = tk.Label(
            info_frame,
            text="",
            font=("Courier New", 16, "bold"),
            bg=BG_BLACK,
            fg=FG_GREEN_BRIGHT,
        )
        self.name_label.pack(pady=(0, 15))
        
        # Voice description
        voice_desc_title = tk.Label(
            info_frame,
            text="Voice Description:",
            font=("Courier New", 12, "bold"),
            bg=BG_BLACK,
            fg=FG_GREEN_ALT1,
        )
        voice_desc_title.pack(anchor='w', pady=(0, 5))
        
        self.voice_desc_label = tk.Label(
            info_frame,
            text="",
            font=FONT_SMALL,
            bg=BG_BLACK,
            fg=FG_GREEN_BRIGHT,
            wraplength=700,
            justify=tk.LEFT,
        )
        self.voice_desc_label.pack(anchor='w', pady=(0, 15))
        
        # Backstory
        backstory_title = tk.Label(
            info_frame,
            text="Backstory:",
            font=("Courier New", 12, "bold"),
            bg=BG_BLACK,
            fg=FG_GREEN_ALT1,
        )
        backstory_title.pack(anchor='w', pady=(0, 5))
        
        self.backstory_text = scrolledtext.ScrolledText(
            info_frame,
            wrap=tk.WORD,
            width=80,
            height=10,
            font=FONT_SMALL,
            bg=BG_BLACK,
            fg=FG_GREEN_BRIGHT,
            insertbackground=FG_GREEN_BRIGHT,
            relief=tk.SUNKEN,
            bd=1,
            highlightthickness=1,
            highlightbackground=FG_GREEN_BRIGHT,
            highlightcolor=FG_GREEN_BRIGHT,
            state=tk.DISABLED,
        )
        self.backstory_text.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Button frame
        button_frame = tk.Frame(self.root, bg=BG_BLACK)
        button_frame.pack(pady=20)
        
        # Preview voice button
        self.preview_button = self._create_button(
            button_frame,
            text="Preview Voice",
            command=self._on_preview,
        )
        self.preview_button.pack(side=tk.LEFT, padx=10)
        
        # Regenerate voice button
        self.regenerate_button = self._create_button(
            button_frame,
            text="Regenerate Voice",
            command=self._on_regenerate,
        )
        self.regenerate_button.pack(side=tk.LEFT, padx=10)
        
        # Accept button
        self.accept_button = self._create_button(
            button_frame,
            text="Accept & Continue",
            command=self._on_accept,
        )
        self.accept_button.pack(side=tk.LEFT, padx=10)
        
        # Status label
        self.status_label = tk.Label(
            self.root,
            text="",
            font=FONT_SMALL,
            bg=BG_BLACK,
            fg=FG_GREEN_ALT1,
        )
        self.status_label.pack(pady=10)
    
    def _create_button(self, parent, text, command):
        """Create a styled button."""
        btn = tk.Label(
            parent,
            text=text,
            bg=BG_DARK,
            fg=FG_GREEN_BRIGHT,
            font=FONT_SMALL,
            bd=1,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=FG_GREEN_BRIGHT,
            highlightcolor=FG_GREEN_BRIGHT,
            padx=15,
            pady=8,
            cursor="hand2",
        )
        
        def on_enter(_event):
            if btn['state'] != tk.DISABLED:
                btn.config(bg=BG_DARK_ACTIVE)
        
        def on_leave(_event):
            if btn['state'] != tk.DISABLED:
                btn.config(bg=BG_DARK)
        
        def on_click(_event):
            if btn['state'] != tk.DISABLED:
                command()
        
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<Button-1>", on_click)
        
        return btn
    
    def _show_current_character(self):
        """Display the current character's information."""
        if self.current_index >= len(self.characters_data):
            # All characters reviewed
            self._finish()
            return
        
        char = self.characters_data[self.current_index]
        
        # Update progress
        self.progress_label.config(
            text=f"Character {self.current_index + 1} of {len(self.characters_data)}"
        )
        
        # Update character info
        self.name_label.config(text=char['name'])
        self.voice_desc_label.config(text=char['voice_description'])
        
        # Update backstory
        self.backstory_text.config(state=tk.NORMAL)
        self.backstory_text.delete('1.0', tk.END)
        self.backstory_text.insert('1.0', char['backstory'])
        self.backstory_text.config(state=tk.DISABLED)
        
        # Clear status
        self.status_label.config(text="Preview the voice or accept to continue")
    
    def _on_preview(self):
        """Handle preview voice button click."""
        if self.is_generating:
            return
        
        char = self.characters_data[self.current_index]

        # If no ElevenLabs voice_id is available, fail visibly instead of silently
        voice_id = char.get('voice_id')
        if not voice_id:
            msg = (
                f"No ElevenLabs voice available for {char['name']} yet. "
                f"Voice creation may have failed (e.g., custom voice limit reached). "
                f"Check the logs and your ElevenLabs account."
            )
            logger.error(msg)
            self.status_label.config(text=msg)
            return

        self.status_label.config(text=f"Playing preview for {char['name']}...")
        self.root.update()
        
        # Run preview in background thread so UI doesn't freeze
        def preview_thread():
            try:
                self.tts_client.preview_voice(voice_id, char['name'])

                # UI updates must run on the main Tk thread
                def mark_complete():
                    self.status_label.config(text="Preview complete")
                self.root.after(0, mark_complete)

            except Exception as e:
                logger.error(f"Error previewing voice: {e}")

                def mark_error():
                    self.status_label.config(text=f"Error: {str(e)}")
                self.root.after(0, mark_error)
        
        threading.Thread(target=preview_thread, daemon=True).start()
    
    def _on_regenerate(self):
        """Handle regenerate voice button click."""
        if self.is_generating:
            return
        
        char = self.characters_data[self.current_index]
        self.is_generating = True
        
        # Disable buttons during generation
        self.preview_button['state'] = tk.DISABLED
        self.regenerate_button['state'] = tk.DISABLED
        self.accept_button['state'] = tk.DISABLED
        
        self.status_label.config(text=f"Generating new voice for {char['name']}...")
        self.root.update()
        
        # Generate in background thread
        def regenerate_thread():
            try:
                logger.info(f"Regenerating voice for {char['name']}")
                # Call design_and_create_voice with slightly varied parameters
                new_voice_id = self.tts_client.design_and_create_voice(
                    voice_name=f"{char['name']} (v2)",
                    voice_description=char['voice_description']
                )

                if new_voice_id:
                    char['voice_id'] = new_voice_id

                    def on_success():
                        self.status_label.config(text="Voice regenerated! Preview or accept.")
                    logger.info(f"New voice_id for {char['name']}: {new_voice_id}")
                    self.root.after(0, on_success)
                else:
                    def on_fail():
                        self.status_label.config(text="Failed to generate new voice")
                    logger.error(f"Voice regeneration failed for {char['name']}")
                    self.root.after(0, on_fail)

            except Exception as e:
                logger.error(f"Error regenerating voice: {e}")

                def on_error():
                    self.status_label.config(text=f"Error: {str(e)}")
                self.root.after(0, on_error)

            finally:
                # Re-enable buttons and reset state on the main thread
                def on_done():
                    self.preview_button['state'] = tk.NORMAL
                    self.regenerate_button['state'] = tk.NORMAL
                    self.accept_button['state'] = tk.NORMAL
                    self.is_generating = False
                self.root.after(0, on_done)
        
        threading.Thread(target=regenerate_thread, daemon=True).start()
    
    def _on_accept(self):
        """Handle accept button click."""
        if self.is_generating:
            return
        
        char = self.characters_data[self.current_index]
        
        # Store accepted voice
        self.accepted_voices[char['name']] = char['voice_id']
        logger.info(f"Accepted voice for {char['name']}: {char['voice_id']}")
        
        # Move to next character
        self.current_index += 1
        self._show_current_character()
    
    def _finish(self):
        """All characters reviewed - call completion callback."""
        logger.info(f"All {len(self.accepted_voices)} characters accepted")
        self.root.destroy()
        self.on_complete(self.accepted_voices)
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
