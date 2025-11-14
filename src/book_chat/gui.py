"""
GUI chat window for book character conversations.
"""

import tkinter as tk
from tkinter import scrolledtext, font
import threading
import queue
from typing import Optional


class ChatWindow:
    """GUI window displaying conversation as chat bubbles."""
    
    def __init__(self, title: str = "Book Character Conversation", characters: list = None, character_backstories: dict = None):
        """
        Initialize the chat window.
        
        Args:
            title: Window title
            characters: List of character names for selection panel
            character_backstories: Dict mapping character names to their backstory text
        """
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("1200x800")
        
        # Set minimum window size
        self.root.minsize(1000, 600)
        
        # Message queue for thread-safe updates
        self.message_queue = queue.Queue()
        self.quit_requested = False
        self.paused = True  # Start paused, waiting for first spacebar press
        self.space_pressed = False
        
        # Player character selection
        self.characters = characters or []
        self.character_backstories = character_backstories or {}
        self.selected_character = None
        self.player_input = None
        self.waiting_for_player = False
        self.character_panel_frame = None  # Store reference for dynamic updates
        
        # Color scheme for different speakers (with dynamic allocation)
        self.colors = {
            'narrator': '#E8E8E8',  # Light gray
            'Dr. Sarah Chen': '#BBDEFB',  # Light blue
            'Marcus Webb': '#C8E6C9',  # Light green
            'Victoria Reeves': '#FFE0B2',  # Light orange
            'system': '#F5F5F5'  # Very light gray
        }
        
        self._setup_ui()
        self._setup_keybindings()
        self._start_message_processor()
    
    def _setup_character_panel(self, parent):
        """Set up the character selection panel."""
        panel_frame = tk.Frame(parent, bg='#f0f0f0', width=200)
        panel_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        panel_frame.pack_propagate(False)
        
        # Store reference for dynamic updates
        self.character_panel_frame = panel_frame
        self.character_buttons_container = tk.Frame(panel_frame, bg='#f0f0f0')
        self.character_buttons_container.pack(fill=tk.X)
        
        # Panel title
        title_label = tk.Label(
            panel_frame,
            text="Play as Character",
            bg='#f0f0f0',
            fg='#333333',
            font=('Helvetica', 12, 'bold')
        )
        title_label.pack(pady=(10, 5))
        
        subtitle_label = tk.Label(
            panel_frame,
            text="Click to select:",
            bg='#f0f0f0',
            fg='#666666',
            font=('Helvetica', 9)
        )
        subtitle_label.pack(pady=(0, 10))
        
        # Character buttons (will be populated dynamically)
        self.character_buttons = {}
        self._rebuild_character_buttons()
        
        # Observer mode button
        observer_btn = tk.Button(
            self.character_buttons_container,
            text="Watch Only\n(AI plays all)",
            command=lambda: self._select_character(None),
            bg='#E0E0E0',
            fg='#333333',
            font=('Helvetica', 9),
            relief=tk.RAISED,
            padx=10,
            pady=8,
            cursor='hand2'
        )
        observer_btn.pack(fill=tk.X, padx=10, pady=(20, 5))
        self.character_buttons[None] = observer_btn
        
        # Status display
        self.player_status_label = tk.Label(
            panel_frame,
            text="No character selected",
            bg='#f0f0f0',
            fg='#999999',
            font=('Helvetica', 9, 'italic'),
            wraplength=180
        )
        self.player_status_label.pack(pady=(20, 10))
        
        # Backstory display area
        backstory_title = tk.Label(
            panel_frame,
            text="Character Backstory",
            bg='#f0f0f0',
            fg='#333333',
            font=('Helvetica', 10, 'bold')
        )
        backstory_title.pack(pady=(10, 5), padx=10, anchor='w')
        
        backstory_subtitle = tk.Label(
            panel_frame,
            text="(How to play this character)",
            bg='#f0f0f0',
            fg='#666666',
            font=('Helvetica', 8, 'italic')
        )
        backstory_subtitle.pack(pady=(0, 5), padx=10, anchor='w')
        
        # Scrollable text widget for backstory
        self.backstory_text = scrolledtext.ScrolledText(
            panel_frame,
            wrap=tk.WORD,
            height=10,
            font=('Helvetica', 9),
            bg='white',
            fg='#333333',
            relief=tk.SUNKEN,
            borderwidth=1,
            state=tk.DISABLED,
            padx=5,
            pady=5
        )
        self.backstory_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
    
    def _rebuild_character_buttons(self):
        """Rebuild character buttons from current character list."""
        # Remove old character buttons (but keep observer button)
        for char_name in list(self.character_buttons.keys()):
            if char_name is not None:  # Don't remove observer button
                self.character_buttons[char_name].destroy()
                del self.character_buttons[char_name]
        
        # Add buttons for all current characters
        for char_name in self.characters:
            if char_name not in self.character_buttons:
                btn = tk.Button(
                    self.character_buttons_container,
                    text=char_name,
                    command=lambda name=char_name: self._select_character(name),
                    bg='white',
                    fg='#333333',
                    font=('Helvetica', 10),
                    relief=tk.RAISED,
                    padx=10,
                    pady=8,
                    cursor='hand2',
                    wraplength=160
                )
                btn.pack(fill=tk.X, padx=10, pady=5)
                self.character_buttons[char_name] = btn
    
    def add_character(self, name: str, backstory: str, color: str = None):
        """Add a new character dynamically during the conversation."""
        if name not in self.characters:
            self.characters.append(name)
            self.character_backstories[name] = backstory
            
            # Assign color if not already assigned
            if name not in self.colors:
                # Generate a color or use default colors cyclically
                default_colors = ['#BBDEFB', '#C8E6C9', '#FFE0B2', '#F8BBD0', '#E1BEE7', '#FFCCBC']
                color_index = (len(self.characters) - 1) % len(default_colors)
                self.colors[name] = color or default_colors[color_index]
                
                # Configure chat bubble tag for new character
                tag_name = f"bubble_{name}"
                self.chat_display.tag_config(
                    tag_name,
                    background=self.colors[name],
                    spacing1=8,
                    spacing3=8,
                    lmargin1=15,
                    lmargin2=15,
                    rmargin=15,
                    borderwidth=0
                )
            
            # Rebuild button panel
            self._rebuild_character_buttons()
    
    def _setup_keybindings(self):
        """Set up keyboard shortcuts."""
        self.root.bind('<space>', self._on_space_pressed)
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Main container - horizontal split
        main_container = tk.Frame(self.root, bg='white')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left side - chat area
        main_frame = tk.Frame(main_container, bg='white')
        main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right side - character selection panel
        self._setup_character_panel(main_container)
        
        # Title
        title_font = font.Font(family="Helvetica", size=16, weight="bold")
        title_label = tk.Label(
            main_frame,
            text="LOCKDOWN AT NEXUS LABS",
            font=title_font,
            bg='white',
            fg='#333333'
        )
        title_label.pack(pady=(0, 10))
        
        # Chat display area (scrollable)
        self.chat_display = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg='white',
            font=('Arial', 14),
            relief=tk.FLAT,
            padx=10,
            pady=10
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        # Configure tags for different speaker colors
        for speaker, color in self.colors.items():
            tag_name = f"bubble_{speaker}"
            self.chat_display.tag_config(
                tag_name,
                background=color,
                spacing1=8,
                spacing3=8,
                lmargin1=15,
                lmargin2=15,
                rmargin=15,
                borderwidth=0
            )
        
        # Speaker name tag (bold)
        self.chat_display.tag_config(
            'speaker_name',
            font=('Arial', 14, 'bold'),
            foreground='#1a1a1a'
        )
        
        # Narrator text style (italic)
        self.chat_display.tag_config(
            'narrator_text',
            font=('Arial', 13, 'italic'),
            foreground='#444444'
        )
        
        # Bottom button frame
        button_frame = tk.Frame(main_frame, bg='white')
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Quit button
        self.quit_button = tk.Button(
            button_frame,
            text="Quit Conversation",
            command=self._on_quit,
            bg='#E57373',
            fg='white',
            font=('Helvetica', 11, 'bold'),
            relief=tk.FLAT,
            padx=20,
            pady=10,
            cursor='hand2'
        )
        self.quit_button.pack(side=tk.RIGHT)
        
        # Input frame for player dialogue
        input_frame = tk.Frame(main_frame, bg='white')
        input_frame.pack(fill=tk.X, pady=(10, 0))
        
        input_label = tk.Label(
            input_frame,
            text="Your dialogue:",
            bg='white',
            fg='#666666',
            font=('Helvetica', 10)
        )
        input_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.dialogue_entry = tk.Entry(
            input_frame,
            font=('Arial', 12),
            state=tk.DISABLED,
            bg='#f5f5f5'
        )
        self.dialogue_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.dialogue_entry.bind('<Return>', self._on_dialogue_submit)
        
        self.submit_button = tk.Button(
            input_frame,
            text="Speak",
            command=self._on_dialogue_submit,
            bg='#4CAF50',
            fg='white',
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=15,
            cursor='hand2'
        )
        self.submit_button.pack(side=tk.LEFT)
        
        # Status label
        self.status_label = tk.Label(
            button_frame,
            text="AI conversation running...",
            bg='white',
            fg='#2196F3',
            font=('Helvetica', 11, 'bold')
        )
        self.status_label.pack(side=tk.LEFT)
    
    def _start_message_processor(self):
        """Start processing messages from the queue."""
        self._process_queue()
    
    def _process_queue(self):
        """Process messages from the queue and update UI."""
        try:
            while True:
                message_type, data = self.message_queue.get_nowait()
                
                if message_type == 'start_bubble':
                    self._start_bubble(data['speaker'])
                elif message_type == 'append_text':
                    self._append_to_current_bubble(data['text'], data.get('is_narrator', False))
                elif message_type == 'end_bubble':
                    self._end_bubble()
                elif message_type == 'status':
                    self.status_label.config(text=data['text'])
                elif message_type == 'quit':
                    self.root.quit()
                    return
                    
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(10, self._process_queue)
    
    def _start_bubble(self, speaker: str):
        """Start a new chat bubble for a speaker."""
        self.current_speaker = speaker
        self.current_bubble_start = None
        
        self.chat_display.config(state=tk.NORMAL)
        
        # Add spacing between bubbles
        if self.chat_display.index('end-1c') != '1.0':
            self.chat_display.insert(tk.END, '\n\n')
        
        # Store starting position
        self.current_bubble_start = self.chat_display.index('end-1c')
        
        # Add speaker name (if not narrator)
        if speaker != 'narrator':
            self.chat_display.insert(tk.END, f"{speaker}:\n", 'speaker_name')
        
        self.chat_display.config(state=tk.DISABLED)
    
    def _append_to_current_bubble(self, text: str, is_narrator: bool = False):
        """Append text to the current bubble."""
        self.chat_display.config(state=tk.NORMAL)
        
        if is_narrator:
            self.chat_display.insert(tk.END, text, 'narrator_text')
        else:
            self.chat_display.insert(tk.END, text)
        
        # Auto-scroll to bottom
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def _end_bubble(self):
        """Finalize the current bubble with background color."""
        if self.current_bubble_start is None:
            return
        
        self.chat_display.config(state=tk.NORMAL)
        
        # Add newline at end
        self.chat_display.insert(tk.END, '\n')
        
        # Apply bubble background color
        bubble_tag = f"bubble_{self.current_speaker}"
        end_pos = self.chat_display.index('end-1c')
        self.chat_display.tag_add(bubble_tag, self.current_bubble_start, end_pos)
        
        self.chat_display.config(state=tk.DISABLED)
        self.current_bubble_start = None
    
    def add_message(self, speaker: str, text: str, is_narrator: bool = False):
        """
        Add a complete message to the chat.
        
        Args:
            speaker: Name of the speaker
            text: Message text
            is_narrator: Whether this is narrator text (affects styling)
        """
        self.message_queue.put(('start_bubble', {'speaker': speaker}))
        self.message_queue.put(('append_text', {'text': text, 'is_narrator': is_narrator}))
        self.message_queue.put(('end_bubble', {}))
    
    def start_streaming_message(self, speaker: str, is_narrator: bool = False):
        """
        Start a new streaming message.
        
        Args:
            speaker: Name of the speaker
            is_narrator: Whether this is narrator text
        """
        self.message_queue.put(('start_bubble', {'speaker': speaker}))
        self.current_is_narrator = is_narrator
    
    def stream_text(self, text: str):
        """Stream text to the current message."""
        self.message_queue.put(('append_text', {
            'text': text,
            'is_narrator': getattr(self, 'current_is_narrator', False)
        }))
    
    def end_streaming_message(self):
        """End the current streaming message."""
        self.message_queue.put(('end_bubble', {}))
    
    def update_status(self, text: str):
        """Update the status label."""
        self.message_queue.put(('status', {'text': text}))
    
    def _select_character(self, character_name):
        """Handle character selection."""
        self.selected_character = character_name
        
        # Update button styles
        for name, btn in self.character_buttons.items():
            if name == character_name:
                btn.config(bg='#2196F3', fg='white', relief=tk.SUNKEN)
            else:
                if name is None:
                    btn.config(bg='#E0E0E0', fg='#333333', relief=tk.RAISED)
                else:
                    btn.config(bg='white', fg='#333333', relief=tk.RAISED)
        
        # Update status
        if character_name:
            self.player_status_label.config(
                text=f"Playing as:\n{character_name}",
                fg='#2196F3'
            )
        else:
            self.player_status_label.config(
                text="Observer mode\n(AI plays all)",
                fg='#999999'
            )
        
        # Update backstory display
        self.backstory_text.config(state=tk.NORMAL)
        self.backstory_text.delete('1.0', tk.END)
        
        if character_name and character_name in self.character_backstories:
            backstory = self.character_backstories[character_name]
            self.backstory_text.insert('1.0', backstory)
        elif character_name is None:
            self.backstory_text.insert('1.0', "Observer mode - You are watching the AI characters interact. No backstory needed.")
        else:
            self.backstory_text.insert('1.0', "No backstory available for this character.")
        
        self.backstory_text.config(state=tk.DISABLED)
    
    def _on_dialogue_submit(self, event=None):
        """Handle player dialogue submission."""
        if not self.waiting_for_player:
            return
        
        dialogue = self.dialogue_entry.get().strip()
        if not dialogue:
            return
        
        # Store player input
        self.player_input = dialogue
        self.waiting_for_player = False
        
        # Clear and disable input
        self.dialogue_entry.delete(0, tk.END)
        self.dialogue_entry.config(state=tk.DISABLED, bg='#f5f5f5')
        self.submit_button.config(state=tk.DISABLED)
        self.update_status("Processing...")
    
    def _on_space_pressed(self, event=None):
        """Handle spacebar press to advance conversation."""
        self.space_pressed = True
        self.paused = False
        self.update_status("Processing...")
    
    def _on_quit(self):
        """Handle quit button click."""
        self.quit_requested = True
        self.update_status("Quitting conversation...")
    
    def is_quit_requested(self) -> bool:
        """Check if user requested to quit."""
        return self.quit_requested
    
    def wait_for_space(self):
        """Block until user presses space (deprecated - kept for backward compatibility)."""
        # This method is no longer used in the main flow
        # AI turns auto-advance; only player turns wait for input
        pass
    
    def is_paused(self) -> bool:
        """Check if conversation is paused."""
        return self.paused
    
    def get_selected_character(self) -> Optional[str]:
        """Get the name of the character the player is controlling."""
        return self.selected_character
    
    def enable_player_input(self, character_name: str):
        """Enable the dialogue input for player's turn."""
        self.waiting_for_player = True
        self.player_input = None
        
        self.dialogue_entry.config(state=tk.NORMAL, bg='white')
        self.submit_button.config(state=tk.NORMAL)
        self.dialogue_entry.focus()
        self.update_status(f"Your turn as {character_name}! Type your dialogue...")
    
    def wait_for_player_input(self) -> str:
        """Wait for player to submit their dialogue."""
        # Wait for player input
        while self.waiting_for_player and not self.quit_requested:
            self.root.update()
            import time
            time.sleep(0.05)
        
        if self.quit_requested:
            return None
        
        return self.player_input
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
    
    def close(self):
        """Close the window."""
        self.message_queue.put(('quit', {}))
