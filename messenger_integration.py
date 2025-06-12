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
        
        # Cache for failed typing indicator recipients to avoid spamming
        self.typing_indicator_failed_users = set()
        
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
                            # Skip echo messages (bot's own messages echoed back)
                            if event['message'].get('is_echo', False):
                                log.info(f"[WebhookProcessing] Skipping echo quick reply from {user_id}")
                                continue
                                
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
                            # Skip echo messages (bot's own messages echoed back)
                            if event['message'].get('is_echo', False):
                                log.info(f"[WebhookProcessing] Skipping echo message from {user_id}")
                                continue
                                
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
        Automatically splits messages longer than 2000 characters.
        """
        print(f"[DEBUG] send_message called with recipient_id={recipient_id}, message_text='{message_text[:50]}...'")
        
        if not self.page_access_token:
            print("[MessengerIntegration] ERROR: PAGE_ACCESS_TOKEN is not set")
            return {}

        # Check if message needs splitting
        if len(message_text) <= 2000:
            return self._send_single_message(recipient_id, message_text)
        else:
            return self._send_split_message(recipient_id, message_text)

    def _send_single_message(self, recipient_id: str, message_text: str) -> Dict[str, Any]:
        """Send a single message that fits within Facebook's limits."""
        url = self.api_url
        params = {"access_token": self.page_access_token}
        headers = {"Content-Type": "application/json"}
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
        }
        
        print(f"[DEBUG] Sending to Facebook API: {payload}")

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

    def _send_split_message(self, recipient_id: str, message_text: str) -> Dict[str, Any]:
        """Split and send a long message across multiple Facebook messages."""
        print(f"[DEBUG] Message too long ({len(message_text)} chars), splitting into parts...")
        
        # Split the message intelligently
        parts = self._split_message_intelligently(message_text)
        
        print(f"[DEBUG] Split into {len(parts)} parts")
        
        # Send each part with a small delay
        results = []
        for i, part in enumerate(parts):
            print(f"[DEBUG] Sending part {i+1}/{len(parts)} ({len(part)} chars)")
            
            # Add part indicators for multi-part messages
            if len(parts) > 1:
                if i == 0:
                    part = part + f"\n\n📄 (Part {i+1}/{len(parts)})"
                elif i == len(parts) - 1:
                    part = f"📄 (Part {i+1}/{len(parts)})\n\n" + part
                else:
                    part = f"📄 (Part {i+1}/{len(parts)})\n\n" + part + f"\n\n📄 (continued...)"
            
            result = self._send_single_message(recipient_id, part)
            results.append(result)
            
            # Small delay between parts to ensure proper order
            if i < len(parts) - 1:
                import time
                time.sleep(0.5)
        
        # Return the result of the last part
        return results[-1] if results else {}

    def _split_message_intelligently(self, message_text: str, max_length: int = 1900) -> List[str]:
        """
        Split a message intelligently at good break points.
        Uses max_length of 1900 to leave room for part indicators.
        """
        if len(message_text) <= max_length:
            return [message_text]
        
        parts = []
        remaining = message_text
        
        while len(remaining) > max_length:
            # Find the best split point within the limit
            split_point = max_length
            
            # Try to split at paragraph breaks first
            paragraph_break = remaining.rfind('\n\n', 0, max_length)
            if paragraph_break > max_length * 0.5:  # Don't split too early
                split_point = paragraph_break + 2
            else:
                # Try to split at sentence breaks
                sentence_break = remaining.rfind('. ', 0, max_length)
                if sentence_break > max_length * 0.6:
                    split_point = sentence_break + 2
                else:
                    # Try to split at line breaks
                    line_break = remaining.rfind('\n', 0, max_length)
                    if line_break > max_length * 0.7:
                        split_point = line_break + 1
                    else:
                        # Last resort: split at word boundaries
                        word_break = remaining.rfind(' ', 0, max_length)
                        if word_break > max_length * 0.8:
                            split_point = word_break + 1
            
            # Extract the part and continue with the rest
            part = remaining[:split_point].rstrip()
            parts.append(part)
            remaining = remaining[split_point:].lstrip()
        
        # Add the final part
        if remaining:
            parts.append(remaining)
        
        return parts

    def send_typing_indicator(self, recipient_id: str, typing_on: bool = True) -> Dict[str, Any]:
        """
        Send a typing indicator to show the bot is processing.

        Args:
            recipient_id: Facebook user ID (PSID)
            typing_on: True to show typing, False to hide
        """
        if not self.page_access_token:
            log.warning("[TypingIndicator] PAGE_ACCESS_TOKEN is not set")
            return {"error": "PAGE_ACCESS_TOKEN not configured"}
            
        # Skip if this user has already failed typing indicators
        if recipient_id in self.typing_indicator_failed_users:
            return {"error": "typing_indicators_disabled_for_user", "can_retry": False}
            
        # Use the newer API version and try different approaches
        url = "https://graph.facebook.com/v19.0/me/messages"
        params = {"access_token": self.page_access_token}
        
        # Try the simplest payload first
        payload = {
            "recipient": {"id": recipient_id},
            "sender_action": "typing_on" if typing_on else "typing_off"
        }

        try:
            # Single POST, no raise_for_status() so we can log the error body
            response = requests.post(url, params=params, json=payload, timeout=5)
            try:
                body = response.json()
            except ValueError:
                body = {"error": response.text}

            if response.status_code != 200:
                # Check for specific error codes that indicate messaging window issues
                error_subcode = body.get('error', {}).get('error_subcode')
                if error_subcode == 2018048:
                    log.warning(f"[TypingIndicator] Error 2018048 for recipient={recipient_id} - disabling typing indicators for this user")
                    print(f"❌ Typing indicator FAILED for user {recipient_id} - Facebook policy restriction (error 2018048)")
                    print(f"   This usually means: 24h messaging window expired, invalid recipient, or missing permissions")
                    # Add user to failed list to avoid future attempts
                    self.typing_indicator_failed_users.add(recipient_id)
                    return {"error": "messaging_policy_violation", "can_retry": False, "subcode": 2018048}
                else:
                    log.error(
                        f"[TypingIndicator] HTTP {response.status_code} for recipient={recipient_id}\n"
                        f"Action={payload['sender_action']}\n"
                        f"Payload={payload}\n"
                        f"Response={body}"
                    )
            else:
                log.info(f"[TypingIndicator] {payload['sender_action']} ok for recipient={recipient_id}")
                print(f"✅ Typing indicator {payload['sender_action']} sent successfully to {recipient_id}")

            return body
        except Exception as e:
            log.error(f"[TypingIndicator] Exception for recipient={recipient_id}: {e}")
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
        
        # Check if this is an explicit lesson offer (only when user is asked directly)
        if any(phrase in response.lower() for phrase in ["say 'yes' to begin", "would you like to start a", "start a lesson?"]):
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "Yes",
                    "payload": "YES"
                },
                {
                    "content_type": "text",
                    "title": "No Thanks",
                    "payload": "NO"
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