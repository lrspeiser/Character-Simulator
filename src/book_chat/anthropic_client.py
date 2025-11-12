"""
Anthropic Claude API client wrapper.
See .env.example for API key setup instructions.
See README.md for API reference links.
"""

import os
import logging
from typing import List, Dict, Any
from anthropic import Anthropic

# Configure verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ClaudeClient:
    """Wrapper for Claude API with verbose logging and error handling."""
    
    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-5"):
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
    
    def send_message(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024
    ) -> str:
        """
        Send a message to Claude and return the response.
        
        Args:
            system_prompt: System instruction for Claude
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens in response
            
        Returns:
            Claude's response text
        """
        logger.debug("=" * 80)
        logger.debug("SENDING MESSAGE TO CLAUDE")
        logger.debug(f"Model: {self.model}")
        logger.debug(f"System prompt: {system_prompt}")
        logger.debug(f"Messages: {messages}")
        logger.debug(f"Max tokens: {max_tokens}")
        
        try:
            # Note: Do NOT include 'temperature' parameter per user rules
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages
            )
            
            logger.debug("RESPONSE RECEIVED")
            logger.debug(f"Response ID: {response.id}")
            logger.debug(f"Response model: {response.model}")
            logger.debug(f"Stop reason: {response.stop_reason}")
            logger.debug(f"Usage: {response.usage}")
            
            # Extract text from response
            response_text = response.content[0].text
            logger.debug(f"Response text: {response_text}")
            logger.debug("=" * 80)
            
            return response_text
            
        except Exception as e:
            logger.error(f"ERROR calling Claude API: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception details: {str(e)}")
            # Re-raise - do not hide errors per user rules
            raise
