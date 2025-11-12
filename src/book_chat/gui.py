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
    
    def __init__(self, title: str = "Book Character Conversation"):
        """
        Initialize the chat window.
        
        Args:
            title: Window title
        """
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("1000x800")
        
        # Set minimum window size
        self.root.minsize(800, 600)
        
        # Message queue for thread-safe updates
        self.message_queue = queue.Queue()
        self.quit_requested = False
        self.paused = True  # Start paused, waiting for first spacebar press
        self.space_pressed = False
        
        # Color scheme for different speakers
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
    
    def _setup_keybindings(self):
        """Set up keyboard shortcuts."""
        self.root.bind('<space>', self._on_space_pressed)
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Main container
        main_frame = tk.Frame(self.root, bg='white')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
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
        
        # Status label
        self.status_label = tk.Label(
            button_frame,
            text="Press SPACE to continue...",
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
        """Block until user presses space."""
        self.space_pressed = False
        self.paused = True
        self.update_status("Press SPACE to continue...")
        
        # Wait for space press
        while not self.space_pressed and not self.quit_requested:
            self.root.update()
            import time
            time.sleep(0.05)
    
    def is_paused(self) -> bool:
        """Check if conversation is paused."""
        return self.paused
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
    
    def close(self):
        """Close the window."""
        self.message_queue.put(('quit', {}))
