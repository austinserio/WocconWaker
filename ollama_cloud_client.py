"""
Ollama Cloud client abstraction layer.
Replaces local Ollama API calls with Ollama Cloud API while maintaining the same interface.
Uses REST API for Ollama Cloud service.
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any

log = logging.getLogger("ollama_cloud_client")


class OllamaCloudClient:
    """
    Ollama Cloud client that mimics the local Ollama chat interface.
    This allows seamless replacement of local Ollama with Ollama Cloud API.
    """
    
    def __init__(self, 
                 endpoint: Optional[str] = None,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None):
        """
        Initialize Ollama Cloud client.
        
        Args:
            endpoint: Ollama Cloud endpoint URL (from env: OLLAMA_CLOUD_ENDPOINT, default: https://api.ollama.com)
            api_key: Ollama Cloud API key (from env: OLLAMA_CLOUD_API_KEY)
            model: Model name (from env: OLLAMA_MODEL, default: llama3:8b)
        """
        self.endpoint = endpoint or os.getenv("OLLAMA_CLOUD_ENDPOINT", "https://api.ollama.com")
        self.api_key = api_key or os.getenv("OLLAMA_CLOUD_API_KEY")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3:8b")
        
        if not self.api_key:
            raise ValueError("OLLAMA_CLOUD_API_KEY environment variable is required")
        
        # Ensure endpoint doesn't have trailing slash
        self.endpoint = self.endpoint.rstrip('/')
        
        # Ollama Cloud uses the same API structure as local Ollama: /api/chat
        self.api_url = f"{self.endpoint}/api/chat"
        
        log.info(f"Ollama Cloud client initialized with model: {self.model}, endpoint: {self.endpoint}")
    
    def _map_ollama_params(self, ollama_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Ollama parameters (already in Ollama format, just ensure compatibility).
        
        Args:
            ollama_params: Dictionary of Ollama-style parameters
            
        Returns:
            Dictionary of Ollama-compatible parameters
        """
        # Ollama Cloud uses the same parameter format as local Ollama
        # Just ensure we're using the right parameter names
        mapped_params = {}
        
        # Temperature
        if "temperature" in ollama_params:
            mapped_params["temperature"] = ollama_params["temperature"]
        
        # Top-p
        if "top_p" in ollama_params:
            mapped_params["top_p"] = ollama_params["top_p"]
        
        # Num predict (max tokens)
        if "num_predict" in ollama_params:
            mapped_params["num_predict"] = ollama_params["num_predict"]
        
        # Stop sequences
        if "stop" in ollama_params:
            mapped_params["stop"] = ollama_params["stop"]
        
        # Frequency penalty
        if "frequency_penalty" in ollama_params:
            mapped_params["frequency_penalty"] = ollama_params["frequency_penalty"]
        
        # Presence penalty
        if "presence_penalty" in ollama_params:
            mapped_params["presence_penalty"] = ollama_params["presence_penalty"]
        
        # Repeat penalty (Ollama-specific)
        if "repeat_penalty" in ollama_params:
            mapped_params["repeat_penalty"] = ollama_params["repeat_penalty"]
        
        # Seed
        if "seed" in ollama_params:
            mapped_params["seed"] = ollama_params["seed"]
        
        return mapped_params
    
    def chat(self, 
             model: Optional[str] = None,
             messages: List[Dict[str, str]] = None,
             options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Chat completion method that mimics ollama.chat() interface.
        
        Args:
            model: Model name (overrides instance default if provided)
            messages: List of message dicts with 'role' and 'content' keys
            options: Dictionary of model parameters (Ollama-style)
            
        Returns:
            Dictionary with 'message' key containing response, matching Ollama format:
            {
                "message": {
                    "content": "response text"
                }
            }
        """
        if messages is None:
            messages = []
        
        # Use provided model or instance default
        model_name = model or self.model
        
        # Map options to Ollama format
        ollama_options = {}
        if options:
            ollama_options = self._map_ollama_params(options)
        
        try:
            # Prepare request payload for Ollama Cloud API
            # Ollama Cloud uses the same format as local Ollama
            payload = {
                "model": model_name,
                "messages": messages,
                **ollama_options
            }
            
            # Prepare headers with API key for Ollama Cloud
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Make REST API call to Ollama Cloud
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            
            # Check for errors
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            
            # Extract content from Ollama response
            # Ollama response structure: {"message": {"content": "..."}}
            content = ""
            if "message" in response_data and "content" in response_data["message"]:
                content = response_data["message"]["content"]
            elif "response" in response_data:
                # Some Ollama API versions use "response" instead
                content = response_data["response"]
            
            # Return in Ollama-compatible format
            return {
                "message": {
                    "content": content
                }
            }
            
        except requests.exceptions.RequestException as e:
            log.error(f"Ollama Cloud API request error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Response status: {e.response.status_code}")
                log.error(f"Response body: {e.response.text}")
            raise
        except Exception as e:
            log.error(f"Unexpected error calling Ollama Cloud API: {e}")
            raise


# Global client instance (singleton pattern)
_client_instance: Optional[OllamaCloudClient] = None


def get_client() -> OllamaCloudClient:
    """
    Get or create the global Ollama Cloud client instance.
    
    Returns:
        OllamaCloudClient instance
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = OllamaCloudClient()
    return _client_instance


def chat(model: Optional[str] = None,
         messages: List[Dict[str, str]] = None,
         options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convenience function that mimics ollama.chat() for drop-in replacement.
    
    Args:
        model: Model name
        messages: List of message dicts
        options: Model parameters
        
    Returns:
        Dictionary with 'message' key containing response
    """
    client = get_client()
    return client.chat(model=model, messages=messages, options=options)











