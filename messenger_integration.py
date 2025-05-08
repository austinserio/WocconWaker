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
                for messaging_event in entry.get('messaging', []):
                    if 'message' in messaging_event and 'text' in messaging_event['message']:
                        user_id = messaging_event['sender']['id']
                        message_text = messaging_event['message']['text']
                        
                        messages.append({
                            'user_id': user_id,
                            'text': message_text,
                            'raw_event': messaging_event
                        })
        
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