# messenger_integration.py - Complete reorganized version

import requests
import json
import re
from typing import Dict, Any, List, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

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
        self.profile_url = "https://graph.facebook.com/v18.0/me/messenger_profile"
        
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
                    
                    # Handle regular text messages with quick replies
                    if 'message' in event:
                        # Check if it's a quick reply
                        if 'quick_reply' in event['message'] and 'payload' in event['message']['quick_reply']:
                            payload = event['message']['quick_reply']['payload']
                            
                            # Convert quick reply payloads to text
                            text_mappings = {
                                "VOCAB_LESSON": "I'd like to start a vocabulary lesson",
                                "GRAMMAR_LESSON": "I'd like to start a grammar lesson",
                                "HELLO_WOCCON": "How do you say hello in Woccon?",
                                "ABOUT_WOCCON": "Tell me about the Woccon language",
                                "YES": "yes",
                                "NO": "no",
                                "NO_LESSON": "No thanks, I don't want a lesson right now"
                            }
                            
                            # Use the mapped text or the payload itself if not found
                            message_text = text_mappings.get(payload, payload)
                            
                            messages.append({
                                'user_id': user_id,
                                'text': message_text,
                                'raw_event': event,
                                'source': 'quick_reply'
                            })
                        # Regular text message
                        elif 'text' in event['message']:
                            message_text = event['message']['text']
                            
                            messages.append({
                                'user_id': user_id,
                                'text': message_text,
                                'raw_event': event,
                                'source': 'text'
                            })
                    
                    # Handle postbacks from buttons and menus
                    elif 'postback' in event:
                        postback_result = self.handle_postback(event)
                        if postback_result:
                            messages.append(postback_result)
        
        return messages
    
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
                "HELP": "What can you do? Show me available commands.",
                "ABOUT_WOCCON": "Tell me about the Woccon language and its history."
            }
            
            if payload in text_mappings:
                return {
                    'user_id': user_id,
                    'text': text_mappings[payload],
                    'raw_event': postback_data,
                    'source': 'postback'
                }
        
        return None
    
    def send_message(self, recipient_id: str, message_text: str) -> Dict[str, Any]:
        """
        Send a text message to a specific user.
        """
        if not self.page_access_token:
            print("[MessengerIntegration] ERROR: PAGE_ACCESS_TOKEN is not set")
            return {}

        url = self.api_url
        params = {"access_token": self.page_access_token}
        headers = {"Content-Type": "application/json"}
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
        }

        try:
            response = requests.post(url, params=params, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"[MessengerIntegration] Failed to send message to {recipient_id}: "
                      f"HTTP {response.status_code} – {response.text}")
            else:
                print(f"[MessengerIntegration] Sent message to {recipient_id}: {message_text}")
            return response.json()
        except Exception as e:
            print(f"[MessengerIntegration] Exception sending message: {e}")
            return {}
    
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
        
        try:
            response = requests.post(
                self.api_url,
                params=params,
                json=payload,
                timeout=5  # Set a timeout to avoid hanging
            )
            
            # Log the API request details
            log.debug(f"Typing indicator API request: URL={self.api_url}, Params={params}, Payload={payload}")
            
            # Check the response status code
            if response.status_code == 200:
                log.info(f"Typing indicator {'on' if typing_on else 'off'} sent successfully for recipient: {recipient_id}")
            else:
                log.error(f"Failed to send typing indicator. Status code: {response.status_code}, Response: {response.text}")
            
            return response.json()
        
        except requests.exceptions.RequestException as e:
            log.error(f"Error sending typing indicator: {e}")
            return {"error": str(e)}
    
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
    
    def setup_get_started_button(self) -> Dict[str, Any]:
        """Set up the Get Started button for new conversations."""
        params = {
            "access_token": self.page_access_token
        }
        
        payload = {
            "get_started": {
                "payload": "GET_STARTED"
            }
        }
        
        response = requests.post(
            self.profile_url,
            params=params,
            json=payload
        )
        
        return response.json()

    def setup_persistent_menu(self) -> Dict[str, Any]:
        """Set up a persistent menu with helpful options."""
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
            self.profile_url,
            params=params,
            json=payload
        )
        
        return response.json()
    
    def send_generic_template(self, recipient_id: str, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Send a generic template message with cards.
        
        Args:
            recipient_id: Facebook user ID
            elements: List of element objects for the carousel
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
                        "template_type": "generic",
                        "elements": elements
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

    def send_lesson_complete_card(self, recipient_id: str, lesson_type: str, score: int) -> Dict[str, Any]:
        """
        Send a card when a lesson is completed.
        
        Args:
            recipient_id: Facebook user ID
            lesson_type: Type of lesson completed (vocab or grammar)
            score: User's score
        """
        # Determine message based on score
        if score >= 80:
            title = "Excellent Work! 🎉"
            subtitle = f"You scored {score}% on your {lesson_type} lesson. Great job!"
        elif score >= 60:
            title = "Good Progress! 👍"
            subtitle = f"You scored {score}% on your {lesson_type} lesson. Keep practicing!"
        else:
            title = "Keep Learning! 📚"
            subtitle = f"You scored {score}% on your {lesson_type} lesson. Let's try again soon."
        
        elements = [
            {
                "title": title,
                "subtitle": subtitle,
                "image_url": "https://i.imgur.com/8tKFCJD.png",  # Default learning image
                "buttons": [
                    {
                        "type": "postback",
                        "title": "Try Another Lesson",
                        "payload": "VOCAB_LESSON" if lesson_type == "grammar" else "GRAMMAR_LESSON"
                    },
                    {
                        "type": "postback",
                        "title": "Practice Again",
                        "payload": "VOCAB_LESSON" if lesson_type == "vocab" else "GRAMMAR_LESSON"
                    }
                ]
            }
        ]
        
        return self.send_generic_template(recipient_id, elements)

    def send_welcome_carousel(self, recipient_id: str) -> Dict[str, Any]:
        """
        Send a welcome carousel with learning options.
        """
        elements = [
            {
                "title": "Learn Woccon Vocabulary",
                "subtitle": "Master essential Woccon words through interactive lessons",
                "image_url": "https://i.imgur.com/RDLnuQY.png",  # Vocabulary image
                "buttons": [
                    {
                        "type": "postback",
                        "title": "Start Vocab Lesson",
                        "payload": "VOCAB_LESSON"
                    }
                ]
            },
            {
                "title": "Learn Woccon Grammar",
                "subtitle": "Understand how to construct sentences in Woccon",
                "image_url": "https://i.imgur.com/8tKFCJD.png",  # Grammar image
                "buttons": [
                    {
                        "type": "postback",
                        "title": "Start Grammar Lesson",
                        "payload": "GRAMMAR_LESSON"
                    }
                ]
            },
            {
                "title": "About Woccon",
                "subtitle": "Learn about the history and culture of the Woccon people",
                "image_url": "https://i.imgur.com/D76J58p.png",  # Culture image
                "buttons": [
                    {
                        "type": "postback",
                        "title": "Woccon History",
                        "payload": "ABOUT_WOCCON"
                    }
                ]
            }
        ]
        
        return self.send_generic_template(recipient_id, elements)
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile information from Facebook.
        
        Args:
            user_id: Facebook user ID
            
        Returns:
            User profile data (first_name, last_name, profile_pic)
        """
        url = f"https://graph.facebook.com/v18.0/{user_id}"
        
        params = {
            "fields": "first_name,last_name,profile_pic",
            "access_token": self.page_access_token
        }
        
        try:
            response = requests.get(url, params=params)
            return response.json()
        except Exception as e:
            print(f"Error getting user profile: {e}")
            return {"first_name": "Friend", "last_name": "", "profile_pic": ""}
    
    def analyze_message_content(self, text: str, response: str) -> Tuple[List[Dict[str, str]], bool]:
        """
        Analyze message content to determine appropriate quick replies.
        
        Args:
            text: User's message
            response: Assistant's response
            
        Returns:
            Tuple of (quick_replies, should_use_quick_replies)
        """
        quick_replies = []
        should_use_quick_replies = False
        
        # Check if this is a lesson offer
        if any(phrase in response.lower() for phrase in ["vocabulary lesson", "grammar lesson", "start a lesson"]):
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "Start Vocab Lesson",
                    "payload": "VOCAB_LESSON"
                },
                {
                    "content_type": "text",
                    "title": "Start Grammar Lesson",
                    "payload": "GRAMMAR_LESSON"
                },
                {
                    "content_type": "text",
                    "title": "No Thanks",
                    "payload": "NO_LESSON"
                }
            ]
            should_use_quick_replies = True
            
        # Check if this is a yes/no question
        elif any(phrase in response.lower() for phrase in ["yes to begin", "say 'yes'", "say yes"]):
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "Yes",
                    "payload": "YES"
                },
                {
                    "content_type": "text",
                    "title": "No",
                    "payload": "NO"
                }
            ]
            should_use_quick_replies = True
            
        # Check if this is a vocabulary inquiry
        elif any(phrase in response.lower() for phrase in ["woccon word", "means", "translated as", "definition of"]):
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "More examples",
                    "payload": "Show more examples with this word"
                },
                {
                    "content_type": "text",
                    "title": "Similar words",
                    "payload": "What are similar words?"
                }
            ]
            should_use_quick_replies = True
            
        # Check if this is a lesson in progress
        elif "What is the Woccon word for" in response or "Translate this Woccon word" in response:
            if not ("yes/no" in response.lower() or "type your answer" in response.lower()):
                quick_replies = [
                    {"content_type": "text", "title": "I don't know", "payload": "I don't know"},
                    {"content_type": "text", "title": "Skip", "payload": "Skip"},
                    {"content_type": "text", "title": "End Lesson", "payload": "End lesson"}
                ]
                should_use_quick_replies = True
        
        return quick_replies, should_use_quick_replies
    
    def detect_lesson_completion(self, response: str) -> Tuple[bool, str, int]:
        """
        Detect if a lesson has been completed from the response.
        
        Args:
            response: Assistant's response
            
        Returns:
            Tuple of (is_complete, lesson_type, score)
        """
        is_complete = "Lesson complete" in response or "lesson finished" in response
        
        lesson_type = "vocab"
        if "grammar" in response.lower():
            lesson_type = "grammar"
            
        # Try to parse score
        score_match = re.search(r"score:?\s*(\d+)", response.lower())
        score = int(score_match.group(1)) if score_match else 70
        
        return is_complete, lesson_type, score