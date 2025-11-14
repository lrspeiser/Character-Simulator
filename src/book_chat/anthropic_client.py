"""
Anthropic Claude API client wrapper.
See .env.example for API key setup instructions.
See README.md for API reference links.
"""

import os
import sys
import logging
from typing import List, Dict, Any, Optional
from anthropic import Anthropic

# Configure logging (default to INFO, can be overridden)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ClaudeClient:
    """Wrapper for Claude API with verbose logging and error handling."""
    
    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize Claude client.
        
        Args:
            api_key: Anthropic API key (if None, reads from environment)
            model: Claude model to use
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. "
                "Set it in .env file or pass as parameter. "
                "See .env.example for instructions."
            )
        
        self.model = model
        self.client = Anthropic(api_key=self.api_key)
        logger.info(f"ClaudeClient initialized with model: {self.model}")
    
    def count_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation: ~4 chars per token)."""
        return len(text) // 4
    
    def send_message(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        stream: bool = False,
        prefix: Optional[str] = None,
        stream_callback: Optional[callable] = None,
        assistant_prefill: Optional[str] = None
    ) -> str:
        """
        Send a message to Claude and return the response.
        
        Args:
            system_prompt: System instruction for Claude
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens in response
            stream: Whether to stream the response to stdout
            prefix: Optional prefix to print before streaming (e.g., character name)
            stream_callback: Optional callback function for streaming text to GUI
            assistant_prefill: Optional prefill text for assistant response (forces format)
            
        Returns:
            Claude's response text (includes prefill if provided)
        """
        logger.debug("=" * 80)
        logger.debug("SENDING MESSAGE TO CLAUDE")
        logger.debug(f"Model: {self.model}")
        logger.debug(f"System prompt: {system_prompt[:200]}...")
        logger.debug(f"Message count: {len(messages)}")
        logger.debug(f"Max tokens: {max_tokens}")
        logger.debug(f"Streaming: {stream}")
        logger.debug(f"Assistant prefill: {assistant_prefill}")
        
        # Add assistant prefill if provided
        if assistant_prefill:
            messages = messages + [{
                "role": "assistant",
                "content": assistant_prefill
            }]
        
        try:
            if stream:
                # Streaming mode - output to callback or stdout
                if stream_callback:
                    # Stream to GUI via callback
                    full_response = ""
                    with self.client.messages.stream(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system_prompt,
                        messages=messages
                    ) as stream:
                        for text in stream.text_stream:
                            stream_callback(text)
                            full_response += text
                    logger.debug(f"Streamed response to GUI: {full_response}")
                    # Include prefill in returned response
                    if assistant_prefill:
                        return assistant_prefill + full_response
                    return full_response
                else:
                    # Stream to stdout (CLI mode)
                    if prefix:
                        print(prefix, end="", flush=True)
                    
                    full_response = ""
                    with self.client.messages.stream(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system_prompt,
                        messages=messages
                    ) as stream:
                        for text in stream.text_stream:
                            print(text, end="", flush=True)
                            full_response += text
                    
                    print()  # Newline after streaming
                    logger.debug(f"Streamed response: {full_response}")
                    # Include prefill in returned response
                    if assistant_prefill:
                        return assistant_prefill + full_response
                    return full_response
                
            else:
                # Non-streaming mode (for decision-making)
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages
                )
                
                logger.debug("RESPONSE RECEIVED")
                logger.debug(f"Response ID: {response.id}")
                logger.debug(f"Stop reason: {response.stop_reason}")
                logger.debug(f"Usage: {response.usage}")
                
                response_text = response.content[0].text
                logger.debug(f"Response text: {response_text}")
                logger.debug("=" * 80)
                
                # Include prefill in returned response
                if assistant_prefill:
                    return assistant_prefill + response_text
                return response_text
            
        except Exception as e:
            logger.error(f"ERROR calling Claude API: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception details: {str(e)}")
            # Re-raise - do not hide errors per user rules
            raise
