"""ElevenLabs Text-to-Speech integration.

This module provides a minimal ElevenLabs TTS client used by the conversation
engine to read narrator and character dialogue aloud.

API key setup and usage details are documented in README.md under
"ElevenLabs TTS". See that section for instructions before enabling TTS.
"""

import base64
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict
from typing import Optional, Dict

import requests
import websocket

logger = logging.getLogger(__name__)

# Default narrator voice ID provided by the user
NARRATOR_VOICE_ID = "rPZcDAY6w7P5W4oOXZYc"


class ElevenLabsTTS:
    """Simple ElevenLabs TTS client with a background playback queue.

    Notes:
        - API key is read from ELEVENLABS_API_KEY environment variable
          unless explicitly provided.
        - See README.md ("ElevenLabs TTS") for setup details and links to
          ElevenLabs API documentation.
    """

    def __init__(self, api_key: Optional[str] = None, narrator_voice_id: str = NARRATOR_VOICE_ID, cache_size: int = 50):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ELEVENLABS_API_KEY not found. "
                "Set it in .env file or pass as parameter. "
                "See README.md section 'ElevenLabs TTS' for setup instructions."
            )

        self.narrator_voice_id = narrator_voice_id
        self.session = requests.Session()

        # Cache of all available voices and their metadata for fallback mapping
        self._fallback_voices: list[dict] = []  # each: {"voice_id", "name", "description", "labels", ...}
        self._fallback_index: int = 0

        # Audio cache for pre-generated TTS (LRU cache with max size)
        self._audio_cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_size = cache_size
        self._cache_lock = threading.Lock()

        logger.info("ElevenLabsTTS initializing (narrator_voice_id=%s, cache_size=%d)", self.narrator_voice_id, cache_size)

        # Background queue so audio playback doesn't block the UI
        self._task_queue: "queue.Queue[tuple[str, str, str]]" = queue.Queue()

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

        logger.info("ElevenLabsTTS initialized and worker thread started")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def speak_narrator(self, text: str, display_callback=None) -> None:
        """Queue narrator text for speech with the narrator voice.

        Args:
            text: Text to be spoken.
            display_callback: Optional callback(text) to display text when audio starts playing
        """
        if not text or not text.strip():
            logger.debug("speak_narrator called with empty text; skipping")
            return
        logger.info("Queueing narrator TTS (%d chars)", len(text))
        self._enqueue(self.narrator_voice_id, text, label="narrator", display_callback=display_callback)

    def speak_character(self, character_name: str, voice_id: Optional[str], text: str, display_callback=None) -> None:
        """Queue character text for speech using the given voice.

        Args:
            character_name: Name of the character (for logging only).
            voice_id: ElevenLabs voice ID to use (if None, no audio).
            text: Text to be spoken.
            display_callback: Optional callback(text) to display text when audio starts playing
        """
        if not text or not text.strip():
            logger.debug("speak_character called with empty text for %s; skipping", character_name)
            return
        if not voice_id:
            logger.debug("speak_character called for %s without voice_id; skipping", character_name)
            return
        label = f"character:{character_name}"
        logger.info("Queueing character TTS for %s (voice_id=%s, %d chars)", character_name, voice_id, len(text))
        self._enqueue(voice_id, text, label=label, display_callback=display_callback)
    
    def preview_voice(self, voice_id: str, character_name: str) -> None:
        """Play a short preview of the voice immediately (not queued).
        
        Args:
            voice_id: ElevenLabs voice ID to preview
            character_name: Character name (used in preview text)
        """
        preview_text = f"Hello, my name is {character_name}. I'm ready to begin our story."
        logger.info("Previewing voice_id=%s for %s", voice_id, character_name)
        
        # Generate and play immediately (blocking)
        try:
            self._speak_blocking(voice_id, preview_text, f"preview:{character_name}")
        except Exception as e:
            logger.error("Error previewing voice for %s: %s", character_name, e)

    def design_and_create_voice(self, voice_name: str, voice_description: str) -> Optional[str]:
        """Design a voice using ElevenLabs Text-to-Voice API and create it.
        
        This is a two-step process:
        1. POST /v1/text-to-voice/design - generates voice previews with generated_voice_id
        2. POST /v1/text-to-voice - creates the voice using the generated_voice_id
        
        See: https://api.elevenlabs.io/docs#tag/Text-to-Voice
        
        Args:
            voice_name: Name for the created voice (e.g. "Dr. Sarah Chen")
            voice_description: Detailed description for voice generation (e.g. "A sassy squeaky mouse")
                              Description must be 20-1000 characters.
        
        Returns:
            The created voice_id, or None if creation failed.
        """
        voice_description = (voice_description or "").strip()
        voice_name = (voice_name or "").strip()
        
        if not voice_description or len(voice_description) < 20:
            logger.error("Voice description must be at least 20 characters")
            return None
        if len(voice_description) > 1000:
            logger.warning("Voice description truncated to 1000 characters")
            voice_description = voice_description[:1000]
        
        if not voice_name:
            logger.error("Voice name is required")
            return None
        
        # Step 1: Design voice and get generated_voice_id
        design_url = "https://api.elevenlabs.io/v1/text-to-voice/design"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        
        # Extract gender from description if present (for better matching)
        # ElevenLabs API may support explicit gender parameter
        gender = None
        desc_lower = voice_description.lower()
        if desc_lower.startswith('female') or 'female' in desc_lower[:20]:
            gender = 'female'
        elif desc_lower.startswith('male') or 'male' in desc_lower[:20]:
            gender = 'male'
        
        design_payload = {
            "voice_description": voice_description,
            "auto_generate_text": True,  # Let ElevenLabs generate suitable text
            "loudness": 0.5,  # Default loudness
            "guidance_scale": 5.0,  # Default guidance (higher = more adherence to description)
        }
        
        # Add gender if detected (some ElevenLabs endpoints support this)
        if gender:
            design_payload["gender"] = gender
            logger.info("Detected gender '%s' from description, adding to payload", gender)
        
        try:
            logger.info("Designing voice with ElevenLabs for '%s': %s", voice_name, voice_description[:100])
            resp = self.session.post(design_url, headers=headers, json=design_payload, timeout=60)
            resp.raise_for_status()
            design_data = resp.json()
            
            previews = design_data.get("previews", [])
            if not previews:
                logger.error("No voice previews returned from ElevenLabs design API")
                return None
            
            # Log all previews so we can see what ElevenLabs generated
            logger.info("ElevenLabs returned %d voice previews for '%s'", len(previews), voice_name)
            for i, preview in enumerate(previews):
                preview_id = preview.get("generated_voice_id", "unknown")
                # Log the preview metadata if available
                logger.info("  Preview %d: generated_voice_id=%s", i+1, preview_id)
            
            # Use the first preview's generated_voice_id
            # TODO: In the future, we could play all previews and let the user choose
            generated_voice_id = previews[0].get("generated_voice_id")
            if not generated_voice_id:
                logger.error("No generated_voice_id in preview response")
                return None
            
            logger.info("Using preview 1 (generated_voice_id=%s) for voice creation", generated_voice_id)
            
            # Step 2: Create the voice using generated_voice_id
            create_url = "https://api.elevenlabs.io/v1/text-to-voice"
            create_payload = {
                "voice_name": voice_name,
                "voice_description": voice_description,
                "generated_voice_id": generated_voice_id,
            }
            
            logger.info("Creating voice '%s' from generated_voice_id=%s", voice_name, generated_voice_id)
            resp = self.session.post(create_url, headers=headers, json=create_payload, timeout=30)
            resp.raise_for_status()
            create_data = resp.json()
            
            voice_id = create_data.get("voice_id")
            if not voice_id:
                logger.error("No voice_id returned from ElevenLabs create API")
                return None
            
            logger.info("Voice '%s' created successfully (voice_id=%s)", voice_name, voice_id)
            return voice_id
            
        except requests.exceptions.RequestException as e:
            logger.error("Error calling ElevenLabs Text-to-Voice API for '%s': %s", voice_name, e)
            if hasattr(e.response, 'text'):
                logger.error("API response: %s", e.response.text[:500])
            return None
        except Exception as e:
            logger.error("Unexpected error during voice creation for '%s': %s", voice_name, e)
            return None
    
    def find_or_create_voice(self, character_name: str, voice_description: str, auto_create: bool = False) -> Optional[str]:
        """Find an existing voice or create a new one using ElevenLabs Text-to-Voice API.
        
        This method first tries to find an existing voice using the search API.
        If auto_create is True and no voice is found, it will design and create a new voice.
        
        Args:
            character_name: Name of the character (used as voice name if creating)
            voice_description: Description for voice search/creation (20-1000 chars for creation)
            auto_create: If True, create a new voice when search finds nothing (default: False)
        
        Returns:
            A voice_id (existing or newly created), or None if not found and creation disabled/failed.
        """
        # First, try to find an existing voice
        voice_id = self.find_voice_id(voice_description)
        if voice_id:
            return voice_id
        
        # If not found and auto_create is enabled, design and create a new voice
        if auto_create:
            logger.info(
                "No existing voice found for '%s'; creating new voice with description: %s",
                character_name,
                voice_description[:100],
            )
            return self.design_and_create_voice(character_name, voice_description)
        
        # Otherwise, fall back to the existing fallback logic
        logger.info("No voice found for '%s' and auto_create=False; using fallback", character_name)
        return self._pick_fallback_voice(voice_description)
    
    def find_voice_id(self, search: str) -> Optional[str]:
        """Find a voice ID using ElevenLabs /v2/voices search.

        Args:
            search: Search query describing the desired voice (e.g. "gravelly detective, male, mid-40s").

        Returns:
            The first matching voice_id, or None if none found.
        """
        search = (search or "").strip()
        if not search:
            return None

        url = "https://api.elevenlabs.io/v2/voices"
        headers = {"xi-api-key": self.api_key}
        params = {
            "search": search,
            "page_size": 1,
        }

        try:
            logger.info("Searching ElevenLabs voices for query: %s", search)
            resp = self.session.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            voices = data.get("voices", []) or []
            logger.info("ElevenLabs /v2/voices returned %d candidates for query '%s'", len(voices), search)
            if not voices:
                logger.warning("No ElevenLabs voices matched search '%s'", search)
                # Fall back to any available voice
                return self._pick_fallback_voice(search)

            voice_id = voices[0].get("voice_id")
            if voice_id == self.narrator_voice_id:
                logger.info(
                    "Search for '%s' returned narrator voice_id=%s; using fallback voice instead",
                    search,
                    voice_id,
                )
                return self._pick_fallback_voice(search)

            logger.info("ElevenLabs voice match for '%s': %s", search, voice_id)
            return voice_id
        except Exception as e:
            logger.error("Error searching ElevenLabs voices for '%s': %s", search, e)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _enqueue(self, voice_id: str, text: str, label: str, display_callback=None) -> None:
        logger.debug("Enqueuing TTS task label=%s voice_id=%s length=%d", label, voice_id, len(text))
        self._task_queue.put((voice_id, text, label, display_callback))

    def _load_fallback_voice_ids(self) -> None:
        """Load and cache all available ElevenLabs voices for fallback mapping.

        Called when search-based lookup finds no matches. This ensures characters
        can still be assigned distinct voices even if voice_search hints don't
        match anything in the account's voice library.
        """
        if self._fallback_voices:
            return

        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": self.api_key}
        try:
            logger.info("Loading all ElevenLabs voices for fallback mapping")
            resp = self.session.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            voices = data.get("voices", []) or []
            self._fallback_voices = voices
            logger.info("Loaded %d ElevenLabs voices for fallback mapping", len(voices))
        except Exception as e:
            logger.error("Error loading fallback ElevenLabs voices: %s", e)
            self._fallback_voices = []

    def _pick_fallback_voice(self, search: str) -> Optional[str]:
        """Pick a fallback voice_id when search-based lookup fails.

        We try to pick a voice whose name/description/labels best match the
        search hint (e.g. gender or style), and we round-robin so multiple
        characters get different voices. All selections are logged.
        """
        self._load_fallback_voice_ids()
        if not self._fallback_voices:
            logger.warning(
                "No ElevenLabs voices available for fallback mapping (search='%s')",
                search,
            )
            return None

        search_lower = (search or "").lower()
        wants_male = any(tok in search_lower for tok in ["male", "man", "boy"])
        wants_female = any(tok in search_lower for tok in ["female", "woman", "girl"])

        def voice_text(v: dict) -> str:
            name = (v.get("name") or "").lower()
            desc = (v.get("description") or "").lower()
            labels = v.get("labels") or {}
            labels_text = " ".join(str(val).lower() for val in labels.values())
            return f"{name} {desc} {labels_text}".strip()

        # First pass: filter voices that obviously conflict with gender hints
        filtered: list[dict] = []
        for v in self._fallback_voices:
            text = voice_text(v)
            if wants_male and "female" in text:
                continue
            if wants_female and "male" in text:
                continue
            filtered.append(v)

        candidates = filtered or self._fallback_voices

        # Round-robin starting point based on index, but also lightly score by token overlap
        tokens = [t for t in re.split(r"[\s,]+", search_lower) if t]

        def score_voice(v: dict) -> int:
            text = voice_text(v)
            score = 0
            for tkn in tokens:
                if tkn and tkn in text:
                    score += 1
            # Tiny bonus if gender words align
            if wants_male and "male" in text:
                score += 2
            if wants_female and "female" in text:
                score += 2
            return score

        # Prefer non-narrator voices if possible
        non_narrator = [v for v in candidates if v.get("voice_id") != self.narrator_voice_id]
        candidates = non_narrator or candidates

        # Sort by score descending but keep round-robin offset for variety
        scored = sorted(candidates, key=score_voice, reverse=True)
        if not scored:
            return None

        idx = self._fallback_index % len(scored)
        self._fallback_index += 1
        chosen = scored[idx]
        voice_id = chosen.get("voice_id")
        logger.warning(
            "Falling back to ElevenLabs voice_id=%s (name='%s') for query '%s'",
            voice_id,
            chosen.get("name"),
            search,
        )
        return voice_id

    def _worker_loop(self) -> None:
        logger.debug("ElevenLabsTTS worker loop started")
        while True:
            voice_id, text, label, display_callback = self._task_queue.get()
            logger.debug("Worker picked up TTS task label=%s voice_id=%s length=%d", label, voice_id, len(text))
            try:
                # Call display callback before playing audio (if provided)
                if display_callback:
                    logger.debug("Calling display_callback before playing audio for %s", label)
                    display_callback(text)
                
                self._speak_blocking(voice_id, text, label)
                logger.debug("Worker completed TTS task label=%s", label)
            except Exception as e:
                logger.error("Error during ElevenLabs TTS playback (%s): %s", label, e)
            finally:
                self._task_queue.task_done()

    def _speak_blocking(self, voice_id: str, text: str, label: str) -> None:
        """Blocking call that requests TTS audio via WebSocket and plays it locally.

        This uses the ElevenLabs Text-to-Speech WebSocket endpoint:

            wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input

        We send a short initialize message with voice_settings and API key,
        then send the full text in a single chunk with try_trigger_generation.
        Audio chunks are received as base64-encoded MP3 and concatenated.

        NOTE: This intentionally does not hide errors. Any issues reaching
        ElevenLabs or playing audio are logged at error level.
        """
        text = (text or "").strip()
        if not text:
            return
        
        # Check cache first
        cache_key = self._get_cache_key(voice_id, text)
        with self._cache_lock:
            if cache_key in self._audio_cache:
                # Move to end (mark as recently used)
                self._audio_cache.move_to_end(cache_key)
                audio_bytes = self._audio_cache[cache_key]
                logger.info("Cache HIT for %s (voice_id=%s, %d chars, %d bytes)", label, voice_id, len(text), len(audio_bytes))
                self._play_audio(audio_bytes, label)
                return
        
        logger.info("Cache MISS for %s (voice_id=%s, %d chars)", label, voice_id, len(text))

        ws_url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?output_format=mp3_44100_128"

        headers = [
            f"xi-api-key: {self.api_key}",
        ]

        logger.info(
            "Opening ElevenLabs TTS WebSocket for %s (voice_id=%s, %d chars)",
            label,
            voice_id,
            len(text),
        )

        # Collect decoded audio bytes from streaming messages
        audio_bytes = bytearray()
        chunk_count = 0

        try:
            ws = websocket.create_connection(ws_url, header=headers, timeout=30)
        except Exception as e:
            logger.error("Failed to open ElevenLabs WebSocket for %s: %s", label, e)
            return

        try:
            # Initialize connection with voice settings and API key
            init_msg = {
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
                "xi_api_key": self.api_key,
            }
            ws.send(json.dumps(init_msg))

            # Send the full text and trigger generation
            ws.send(json.dumps({"text": text, "try_trigger_generation": True}))

            # Signal end of input text
            ws.send(json.dumps({"text": ""}))

            # Receive streamed audioOutput chunks until isFinal or socket closes
            while True:
                try:
                    raw = ws.recv()
                except websocket.WebSocketConnectionClosedException:
                    break
                if not raw:
                    break

                try:
                    data = json.loads(raw)
                except Exception:
                    # Some messages may not be JSON; ignore them
                    continue

                # audioOutput messages contain base64 audio; some events may have null/empty audio
                if "audio" in data:
                    audio_b64 = data.get("audio")
                    if not audio_b64:
                        logger.debug("Received ElevenLabs audioOutput with empty audio for %s", label)
                    else:
                        try:
                            chunk = base64.b64decode(audio_b64)
                            if chunk:
                                audio_bytes.extend(chunk)
                                chunk_count += 1
                        except Exception as e:
                            logger.error("Error decoding ElevenLabs audio chunk for %s: %s", label, e)

                # Stop when generation is marked final
                if data.get("isFinal") is True or data.get("event") == "finalOutput":
                    break

        except Exception as e:
            logger.error("Error during ElevenLabs WebSocket TTS for %s: %s", label, e)
        finally:
            try:
                ws.close()
            except Exception:
                pass

        if not audio_bytes:
            logger.warning("No audio received from ElevenLabs WebSocket for %s", label)
            return

        logger.info(
            "Received %d audio chunks from ElevenLabs WebSocket for %s (total_bytes=%d)",
            chunk_count,
            label,
            len(audio_bytes),
        )
        
        # Store in cache (convert to bytes for immutability)
        audio_bytes_final = bytes(audio_bytes)
        with self._cache_lock:
            self._audio_cache[cache_key] = audio_bytes_final
            # Enforce LRU eviction if cache exceeds max size
            while len(self._audio_cache) > self._cache_size:
                evicted_key = next(iter(self._audio_cache))
                self._audio_cache.pop(evicted_key)
                logger.debug("Evicted cache entry (key=%s)", evicted_key)
            logger.info("Stored in cache (cache_size=%d/%d)", len(self._audio_cache), self._cache_size)
        
        # Play the audio
        self._play_audio(audio_bytes_final, label)
    
    def _get_cache_key(self, voice_id: str, text: str) -> str:
        """Generate a cache key from voice_id and text.
        
        Args:
            voice_id: ElevenLabs voice ID
            text: Text to be spoken
            
        Returns:
            SHA256 hash of (voice_id, text) as cache key
        """
        key_str = f"{voice_id}|{text}"
        return hashlib.sha256(key_str.encode('utf-8')).hexdigest()
    
    def _play_audio(self, audio_bytes: bytes, label: str) -> None:
        """Play audio bytes using OS audio player.
        
        Args:
            audio_bytes: MP3 audio data to play
            label: Label for logging (e.g. 'narrator' or 'character:Name')
        """
        # Write to a temporary file and play it with the OS audio player.
        # On macOS, use 'afplay'. On other platforms, log a warning for now.
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        logger.debug("Playing ElevenLabs audio for %s from %s (%d bytes)", label, tmp_path, len(audio_bytes))

        try:
            if sys.platform == "darwin":
                # macOS: afplay is the built-in CLI audio player
                # NOTE: afplay -v range is 0.0 to 1.0 only (not higher)
                # To make narrator louder, we keep narrator at 1.0 and lower characters
                if label == "narrator":
                    volume = "1.0"  # Full volume for narrator
                elif label.startswith("character:"):
                    volume = "0.2"  # Much lower volume for character voices (was 0.3)
                elif label.startswith("preview:"):
                    volume = "0.5"  # Medium volume for previews
                else:
                    volume = "0.8"
                
                logger.debug(f"Playing {label} at volume {volume}")
                subprocess.run(["afplay", "-v", volume, tmp_path], check=False)
            else:
                logger.warning(
                    "ElevenLabs TTS audio file generated at %s but no cross-platform "
                    "player is configured for platform '%s' yet.",
                    tmp_path,
                    sys.platform,
                )
        except Exception as e:
            logger.error("Error playing ElevenLabs audio for %s: %s", label, e)
