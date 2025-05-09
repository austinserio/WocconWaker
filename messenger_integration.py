import requests
import json
from typing import Dict, Any, List, Optional

class MessengerIntegration:
    def __init__(self, page_access_token: str, verify_token: str, app_secret: str = None):
        """
        Initialize the Facebook Messenger integration.
        
        Args:
            page_access_token: Token provided by Facebook for your page
            verify_token: Custom token you set to verify webhook
            app_secret: App secret for request validation (optional)
        """
        self.page_access_token = page_access_token
        self.verify_token = verify_token
        self.app_secret = app_secret
        self.api_url = "https://graph.facebook.com/v18.0/me/messages"
        
    def verify_webhook(self, mode: str, token: str) -> bool:
        """Verify the webhook subscription."""
        return mode == 'subscribe' and token == self.verify_token
    
    def process_webhook(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process incoming webhook data from Facebook Messenger.
        
        Returns:
            List of message objects containing user_id and message text
        """
        messages = []
        
        if 'object' in data and data['object'] == 'page':
            for entry in data.get('entry', []):
                for event in entry.get('messaging', []):
                    user_id = event['sender']['id']
                    
                    # Handle regular text messages
                    if 'message' in event and 'text' in event['message']:
                        message_text = event['message']['text']
                        
                        messages.append({
                            'user_id': user_id,
                            'text': message_text,
                            'raw_event': event
                        })
                    
                    # Handle postbacks from buttons and menus
                    elif 'postback' in event:
                        postback_result = self.handle_postback(event)
                        if postback_result:
                            messages.append(postback_result)
        
        return messages
    
    def send_message(self, recipient_id: str, message_text: str) -> Dict[str, Any]:
        """
        Send a text message to a specific user.
        
        Args:
            recipient_id: Facebook user ID to send message to
            message_text: Text content to send
            
        Returns:
            API response from Facebook
        """
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "text": message_text
            }
        }
        
        response = requests.post(
            self.api_url,
            params=params,
            json=payload
        )
        
        return response.json()
    
    def send_typing_indicator(self, recipient_id: str, typing_on: bool = True) -> Dict[str, Any]:
        """
        Send typing indicator to show the bot is processing.
        
        Args:
            recipient_id: Facebook user ID
            typing_on: True to show typing, False to hide
        """
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "sender_action": "typing_on" if typing_on else "typing_off"
        }
        
        response = requests.post(
            self.api_url,
            params=params,
            json=payload
        )
        
        return response.json()
    
    def send_button_template(self, recipient_id: str, text: str, buttons: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Send a button template message.
        
        Args:
            recipient_id: Facebook user ID
            text: Text above the buttons
            buttons: List of button objects with title and payload
        """
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text,
                        "buttons": buttons
                    }
                }
            }
        }
        
        response = requests.post(
            self.api_url,
            params=params,
            json=payload
        )
        
        return response.json()
    
    # Add these methods to messenger_integration.py
    def setup_get_started_button(self) -> Dict[str, Any]:
        """Set up the Get Started button for new conversations."""
        url = f"https://graph.facebook.com/v18.0/me/messenger_profile"
        
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "get_started": {
                "payload": "GET_STARTED"
            }
        }
        
        response = requests.post(
            url,
            params=params,
            json=payload
        )
        
        return response.json()

    def setup_persistent_menu(self) -> Dict[str, Any]:
        """Set up a persistent menu with helpful options."""
        url = f"https://graph.facebook.com/v18.0/me/messenger_profile"
        
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "persistent_menu": [
                {
                    "locale": "default",
                    "composer_input_disabled": False,
                    "call_to_actions": [
                        {
                            "type": "postback",
                            "title": "Start Vocabulary Lesson",
                            "payload": "VOCAB_LESSON"
                        },
                        {
                            "type": "postback",
                            "title": "Start Grammar Lesson",
                            "payload": "GRAMMAR_LESSON"
                        },
                        {
                            "type": "postback",
                            "title": "Help",
                            "payload": "HELP"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(
            url,
            params=params,
            json=payload
        )
        
        return response.json()

    def send_quick_replies(self, recipient_id: str, message_text: str, 
                        quick_replies: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Send a message with quick reply buttons.
        
        Args:
            recipient_id: Facebook user ID
            message_text: Text content of the message
            quick_replies: List of quick reply objects
        """
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "text": message_text,
                "quick_replies": quick_replies
            }
        }
        
        response = requests.post(
            self.api_url,
            params=params,
            json=payload
        )
        
        return response.json()

    def handle_postback(self, postback_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process postback events from buttons and menus.
        
        Args:
            postback_data: Postback event data
            
        Returns:
            Dictionary with user_id and equivalent text to process
        """
        if 'postback' in postback_data and 'payload' in postback_data['postback']:
            user_id = postback_data['sender']['id']
            payload = postback_data['postback']['payload']
            
            # Convert postback payloads to text commands that the WocconAssistant can understand
            text_mappings = {
                "GET_STARTED": "Hello! I'm interested in learning about Woccon.",
                "VOCAB_LESSON": "I'd like to start a vocabulary lesson",
                "GRAMMAR_LESSON": "I'd like to start a grammar lesson",
                "HELP": "What can you do? Show me available commands."
            }
            
            if payload in text_mappings:
                return {
                    'user_id': user_id,
                    'text': text_mappings[payload],
                    'raw_event': postback_data
                }
        
        return None