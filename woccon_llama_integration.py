"""
Woccon Language Assistant with Llama Integration
This implementation combines your WocconT5 analyzer with Llama to create
a natural language interface for Messenger that makes Woccon language
learning interactive and accessible.
"""

import os
import sys
import json
import time
import requests
from typing import Dict, List, Any, Optional
import logging
import re
import random

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("woccon_assistant")

# Import your WocconT5 class
from main import WocconT5

# Import Llama client (using Ollama as it's easy to use locally)
import ollama

class WocconLanguageAssistant:
    def __init__(self, llm_model: str = "llama3.2:3b"):
        """
        Initialize the Woccon Language Assistant with both WocconT5 and Llama integration
        
        Args:
            llm_model: The Llama model to use (default is llama3.2:3b for testing)
        """
        logger.info("Initializing Woccon Language Assistant...")
        
        # Initialize WocconT5 for Woccon language analysis
        self.woccon = WocconT5()
        
        # Initialize Llama model
        self.llm_model = llm_model
        self.llm_initialized = False
        
        # Check if Ollama is running
        try:
            ollama.list()
            self.llm_initialized = True
            logger.info(f"Successfully connected to Ollama with model: {llm_model}")
        except Exception as e:
            logger.warning(f"Could not connect to Ollama: {str(e)}")
            logger.warning("Natural language capabilities will be limited")
        
        # Load interactive prompts for language lessons
        self.lesson_templates = self._load_lesson_templates()
        
        # User session tracking
        self.user_sessions = {}
    
    def _load_lesson_templates(self) -> Dict[str, str]:
        """Load lesson templates from templates.json if available"""
        templates = {
            "vocabulary": "Let's practice some Woccon vocabulary! I'll show you words in the '{category}' category. First word: {word} means '{english}' in English. Try to remember this word!",
            "analyze": "Let's look at the structure of the Woccon word '{word}'. This word means '{english}'. Notice how it uses the root '{root}' which means '{root_meaning}'. Can you think of other words that might use this root?",
            "pronunciation": "Let's practice pronouncing the Woccon word '{word}'. It's written as '{word}' and means '{english}'. In Woccon, consonants are pronounced similar to English. Try saying this word out loud!",
            "greeting": "Welcome back to your Woccon language learning! Would you like to: 1) Learn new vocabulary, 2) Analyze word structures, 3) Practice pronunciation, or 4) Just look up specific words?"
        }
        
        # Try to load custom templates if available
        try:
            with open("templates.json", "r", encoding="utf-8") as f:
                custom_templates = json.load(f)
                templates.update(custom_templates)
                logger.info("Loaded custom lesson templates")
        except:
            logger.info("Using default lesson templates")
        
        return templates
    
    def _get_session(self, user_id: str) -> Dict[str, Any]:
        """Get or create a session for a user"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                "last_interaction": time.time(),
                "context": [],
                "current_lesson": None,
                "learned_words": set(),
                "current_word": None
            }
        
        # Update last interaction time
        self.user_sessions[user_id]["last_interaction"] = time.time()
        return self.user_sessions[user_id]
    
    def _create_system_prompt(self) -> str:
        """Create a system prompt for the LLM with information about Woccon"""
        return """You are a helpful Woccon language assistant.
        
Woccon was an Eastern Siouan language spoken in the coastal plains of North Carolina along the lower Neuse River. 
The language is known primarily from a word list of about 140 terms collected by John Lawson in 1709.

Your primary roles are:
1. Help users look up and understand EXISTING Woccon words from Lawson's list ONLY
2. Explain the structure and morphology of documented Woccon words
3. Create simple, engaging language lessons using ONLY known words
4. Answer questions about the Woccon language and culture

CRITICAL RULES:
- NEVER generate new Woccon words that aren't in Lawson's original list
- NEVER infer, reconstruct, or create hypothetical Woccon words or phrases
- NEVER translate an English word to Woccon unless you find an exact match in the dictionary
- If asked for a Woccon word that isn't in the list, clearly state that it's not documented
- ALWAYS make clear the limitations of our knowledge about Woccon
- ALWAYS clarify when you're describing linguistic reconstruction or inference

Your tone should be educational, culturally sensitive, and encouraging for language learners.

Remember: We are working with a limited word list of approximately 140 words from 1709, and 
your goal is to make this existing documented knowledge accessible and educational, not to
expand beyond what's documented."""
    
    def handle_message(self, user_id: str, message_text: str) -> str:
        """Process a message from the user and generate a response"""
        # Get user session
        session = self._get_session(user_id)
        
        # First, check for specific commands
        if message_text.lower().startswith(("lookup:", "find:", "search:")):
            # Handle word lookup
            search_term = message_text.split(":", 1)[1].strip()
            return self._lookup_word(search_term)
            
        elif message_text.lower().startswith(("analyze:", "breakdown:")):
            # Handle word analysis
            word = message_text.split(":", 1)[1].strip()
            return self._analyze_word(word)
            
        elif message_text.lower().startswith(("lesson:", "learn:", "practice:")):
            # Handle lesson request
            lesson_type = message_text.split(":", 1)[1].strip().lower()
            return self._start_lesson(user_id, lesson_type)
            
        elif message_text.lower() in ["help", "menu", "commands"]:
            # Handle help request
            return self._get_help_message()
        
        # If there's an active lesson, process it
        if session["current_lesson"]:
            return self._continue_lesson(user_id, message_text)
        
        # For everything else, if LLM is available, use it to interpret the request
        if self.llm_initialized:
            return self._process_with_llm(user_id, message_text)
        else:
            # Fallback to basic keyword matching without LLM
            return self._process_without_llm(message_text)
    
    def _lookup_word(self, search_term: str) -> str:
        """Look up a word in the Woccon dictionary"""
        results = []
        
        # Try Woccon to English
        entry = self.woccon.lookup_word(search_term, "woc_to_eng")
        if entry:
            results.append(f"📚 Woccon word: '{entry['woccon']}' means '{entry['english']}' ({entry['pos']})")
        
        # Try English to Woccon
        english_matches = []
        for word in self.woccon.dictionary.get("lexicon", []):
            if search_term.lower() in word["english"].lower():
                english_matches.append(word)
                
        if english_matches:
            results.append(f"Found {len(english_matches)} Woccon words related to '{search_term}':")
            for word in english_matches[:5]:  # Limit to 5 results
                results.append(f"- {word['woccon']} = {word['english']} ({word['pos']})")
            
            if len(english_matches) > 5:
                results.append(f"...and {len(english_matches) - 5} more.")
        
        if not results:
            return f"I couldn't find any Woccon words matching '{search_term}'. Remember, we only have about 141 documented Woccon words from John Lawson's 1709 word list."
        
        return "\n".join(results)
    
    def _analyze_word(self, word: str) -> str:
        """Analyze the structure of a Woccon word"""
        # Check if word exists
        entry = self.woccon.lookup_word(word, "woc_to_eng")
        if not entry:
            return f"I don't recognize '{word}' as a documented Woccon word. Please check the spelling or try another word."
        
        # Get full analysis
        analysis = self.woccon.analyze_word(word)
        
        # Format the output
        result = []
        result.append(f"📝 Analysis of '{word}':")
        result.append(f"Meaning: {entry['english']}")
        result.append(f"Part of speech: {entry['pos']}\n")
        
        # Show affixes
        if analysis["affixes"]:
            result.append("Affixes Found:")
            for affix in sorted(analysis["affixes"], key=lambda x: x["position"]):
                confidence = affix.get('confidence', 'medium')
                result.append(f"- {affix['type'].capitalize()} '{affix['form']}' = {affix['function']} ({confidence} confidence)")
        
        # Show roots
        if analysis["roots"]:
            result.append("\nRoots Found:")
            for root_info in analysis["roots"]:
                confidence = f"{root_info['match_type']} ({root_info['confidence']} confidence)"
                result.append(f"- Found {confidence} '{root_info['root']}' meaning '{root_info['meaning']}'")
        
        # Show semantic groups
        if analysis.get("semantic_groups"):
            groups = list(analysis["semantic_groups"].keys())
            if groups:
                result.append(f"\nThis word belongs to these semantic categories: {', '.join(groups)}")
        
        # Educational note
        result.append("\nUnderstanding word structure helps you learn patterns in the Woccon language!")
        
        return "\n".join(result)
    
    def _start_lesson(self, user_id: str, lesson_type: str) -> str:
        """Start a language lesson of the specified type"""
        session = self._get_session(user_id)
        
        # Map user input to lesson types
        lesson_mapping = {
            "vocabulary": "vocabulary",
            "vocab": "vocabulary",
            "words": "vocabulary",
            "analyze": "analyze",
            "structure": "analyze",
            "roots": "analyze",
            "pronunciation": "pronunciation",
            "pronounce": "pronunciation",
            "speaking": "pronunciation"
        }
        
        # Normalize lesson type
        normalized_type = lesson_mapping.get(lesson_type.lower())
        if not normalized_type:
            return f"I don't recognize the lesson type '{lesson_type}'. Available lessons are: vocabulary, analyze, and pronunciation."
        
        # Set current lesson
        session["current_lesson"] = normalized_type
        
        # Select a random word for the lesson (since WocconT5 doesn't have get_random_example)
        import random
        
        # Filter words to ensure we select well-documented words with clear meanings
        good_lesson_words = []
        for word in self.woccon.dictionary.get("lexicon", []):
            # Skip complex or compound words for basic lessons
            if "-" in word["woccon"] and normalized_type != "analyze":
                continue
                
            # Skip words with unclear or multiple meanings
            if "," in word["english"]:
                continue
                
            # Skip very short words
            if len(word["woccon"]) < 3:
                continue
                
            # Focus on nouns for vocabulary lessons
            if normalized_type == "vocabulary" and word["pos"] != "noun":
                continue
                
            good_lesson_words.append(word)
            
        if not good_lesson_words:
            # Fallback to all words if filtering is too strict
            good_lesson_words = self.woccon.dictionary.get("lexicon", [])
        
        random_word = random.choice(good_lesson_words)
        session["current_word"] = random_word
        
        # Create lessons using templates with only documented words
        if normalized_type == "vocabulary":
            return self._create_vocabulary_lesson(user_id, random_word)
        elif normalized_type == "analyze":
            return self._create_analysis_lesson(random_word)
        elif normalized_type == "pronunciation":
            return self._create_pronunciation_lesson(random_word)
        else:
            return f"Let's learn about the Woccon word '{random_word['woccon']}' which means '{random_word['english']}' in English."
    
    def _create_vocabulary_lesson(self, user_id: str, word: dict) -> str:
        """Create a vocabulary lesson for a specific word"""
        # Get the semantic category for this word
        categories = []
        eng = word["english"].lower()
        
        category_keywords = {
            "animals": ["fish", "snake", "bird", "dog", "wolf", "squirrel", "panther", "goose", "duck", "swan"],
            "food": ["corn", "acorn", "hominy", "eat", "food", "bread", "peas"],
            "tools": ["knife", "axe", "spoon", "hoe", "needle", "gunpowder", "weapon"],
            "body_parts": ["head", "hand", "body", "foot", "hair", "face"],
            "numbers": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        }
        
        for category, keywords in category_keywords.items():
            if any(keyword in eng for keyword in keywords):
                categories.append(category)
                
        if not categories:
            categories = ["vocabulary"]
            
        category = categories[0]
        
        # Find related words in the same category
        related_words = []
        for w in self.woccon.dictionary.get("lexicon", []):
            if w["woccon"] != word["woccon"]:  # Skip the current word
                for keyword in category_keywords.get(category, []):
                    if keyword in w["english"].lower():
                        related_words.append(w)
                        break
        
        # Limit to 3 related words
        if len(related_words) > 3:
            related_words = random.sample(related_words, 3)
            
        # Create the lesson
        lesson = f"""📚 Woccon Vocabulary Lesson: {category.title()} 📚

Let's learn the Woccon word for '{word['english']}':

🔹 Woccon: {word['woccon']}
🔹 English: {word['english']}
🔹 Part of speech: {word['pos']}

"""
        
        if related_words:
            lesson += f"Here are some related {category} words in Woccon:\n\n"
            for i, related in enumerate(related_words, 1):
                lesson += f"{i}. {related['woccon']} = {related['english']}\n"
            
        lesson += """
Try practicing this word! Can you say it out loud? Remember, we don't know exactly how Woccon was pronounced, but we can make an educated guess based on other Native American languages from the region.

Would you like to:
1. Learn another word? (say "next")
2. Practice this word? (say the word)
3. Learn about the structure of this word? (say "analyze")

You can also end the lesson by saying "quit lesson".
"""
        
        return lesson
        
    def _create_analysis_lesson(self, word: dict) -> str:
        """Create an analysis lesson for a specific word"""
        # Get the analysis
        analysis = self.woccon.analyze_word(word["woccon"])
        
        # Create the lesson
        lesson = f"""🔍 Woccon Word Analysis: {word['woccon']} 🔍

Let's analyze the structure of the Woccon word '{word['woccon']}':

🔹 Meaning: {word['english']}
🔹 Part of speech: {word['pos']}

"""
        
        # Add information about roots
        if analysis["roots"]:
            lesson += "This word contains the following root(s):\n\n"
            for root in analysis["roots"]:
                lesson += f"• {root['root']} = '{root['meaning']}'\n"
                if root.get("note"):
                    lesson += f"  Note: {root['note']}\n"
            lesson += "\n"
            
        # Add information about affixes
        if analysis["affixes"]:
            lesson += "This word contains the following affix(es):\n\n"
            for affix in analysis["affixes"]:
                lesson += f"• {affix['type'].capitalize()} '{affix['form']}' = {affix['function']}\n"
            lesson += "\n"
            
        # Add information about sound correspondences
        if analysis["sound_links"]:
            lesson += "Sound correspondences with Catawba:\n\n"
            for link in analysis["sound_links"]:
                lesson += f"• Woccon '{link['woccon']}' corresponds to Catawba '{link['catawba']}'\n"
            lesson += "\n"
            
        # If no structural elements were found
        if not analysis["roots"] and not analysis["affixes"] and not analysis["sound_links"]:
            lesson += "This word doesn't appear to contain any known roots or affixes. It may be a simple root word itself, or its structure may not be fully understood from the limited documentation we have.\n\n"
            
        lesson += """Understanding word structure helps us see patterns in the language, even with our limited documentation.

Would you like to:
1. Analyze another word? (say "next")
2. Learn more vocabulary? (say "vocabulary")
3. See words related to this one? (say "related")

You can also end the lesson by saying "quit lesson".
"""
        
        return lesson
        
    def _create_pronunciation_lesson(self, word: dict) -> str:
        """Create a pronunciation lesson for a specific word"""
        # Create the lesson
        lesson = f"""🗣️ Woccon Pronunciation Practice: {word['woccon']} 🗣️

Let's practice pronouncing the Woccon word for '{word['english']}':

🔹 Woccon spelling: {word['woccon']}

While we don't know exactly how Woccon was pronounced, we can make some educated guesses based on related Eastern Siouan languages:

• Consonants (p, t, k, m, n, r, s, h, w, y) were likely similar to their English equivalents
• Vowels (a, e, i, o, u) might have been pronounced more like in Spanish or Italian
• Stress patterns are unknown, so try different syllable emphases

Try saying the word out loud several times, breaking it into syllables if needed.

"""
        
        # Add syllable breakdown if possible
        syllables = []
        word_text = word["woccon"]
        
        # Very basic syllable separation - not linguistically accurate but helpful for practice
        current = ""
        for char in word_text:
            current += char
            if char in "aeiou" and len(current) > 1:
                syllables.append(current)
                current = ""
        
        if current:
            syllables.append(current)
            
        if syllables:
            lesson += "Possible syllable breakdown:\n\n"
            lesson += " - ".join(syllables)
            lesson += "\n\n"
            
        lesson += """Remember, this is just a learning exercise. The actual pronunciation of Woccon words is not known with certainty.

Would you like to:
1. Practice another word? (say "next")
2. Learn more vocabulary? (say "vocabulary")
3. Analyze this word's structure? (say "analyze")

You can also end the lesson by saying "quit lesson".
"""
        
        return lesson
    
    def _continue_lesson(self, user_id: str, message_text: str) -> str:
        """Continue an existing lesson"""
        session = self._get_session(user_id)
        lesson_type = session["current_lesson"]
        current_word = session["current_word"]
        
        # Process user response based on lesson type
        if lesson_type == "vocabulary":
            # For vocabulary lessons, check if they want another word
            if any(x in message_text.lower() for x in ["next", "another", "more", "continue"]):
                return self._start_lesson(user_id, "vocabulary")
            
            # If they repeat the word, give positive feedback
            if current_word["woccon"].lower() in message_text.lower():
                session["learned_words"].add(current_word["woccon"])
                
                # If they've learned several words, offer a different lesson type
                if len(session["learned_words"]) >= 3:
                    session["current_lesson"] = None  # End lesson
                    return "Great job! You've practiced several Woccon words. Would you like to try analyzing word structure next? Type 'lesson:analyze' to start."
                
                return f"Great job saying {current_word['woccon']}! Would you like to learn another word? Say 'next' to continue."
            
            # Otherwise, give a hint
            return f"Try saying the Woccon word '{current_word['woccon']}' which means '{current_word['english']}'. Or say 'next' for another word."
            
        elif lesson_type == "analyze":
            # For analysis lessons, check if they want another word
            if any(x in message_text.lower() for x in ["next", "another", "more", "continue"]):
                return self._start_lesson(user_id, "analyze")
            
            # If they seem to be asking a question about the structure
            if "?" in message_text or any(x in message_text.lower() for x in ["why", "how", "what"]):
                # End this lesson and provide detailed analysis
                session["current_lesson"] = None
                return self._analyze_word(current_word["woccon"])
            
            # Otherwise, give more information
            analysis = self.woccon.analyze_word(current_word["woccon"])
            
            if analysis["affixes"]:
                affix = analysis["affixes"][0]
                return f"The word '{current_word['woccon']}' uses the {affix['type']} '{affix['form']}' which {affix['function']}. Would you like to analyze another word? Say 'next' to continue."
            
            return f"Would you like to analyze another Woccon word? Say 'next' to continue, or ask me a specific question about '{current_word['woccon']}'."
            
        elif lesson_type == "pronunciation":
            # For pronunciation lessons, check if they want another word
            if any(x in message_text.lower() for x in ["next", "another", "more", "continue"]):
                return self._start_lesson(user_id, "pronunciation")
            
            # If they indicate they've tried pronouncing it
            if any(x in message_text.lower() for x in ["said", "tried", "pronounced", "spoke"]):
                session["learned_words"].add(current_word["woccon"])
                return f"Great job practicing '{current_word['woccon']}'! In Woccon, vowels are thought to be pronounced similarly to Spanish or Italian. Would you like to try another word? Say 'next' to continue."
            
            # Otherwise, give more guidance
            return f"Try saying '{current_word['woccon']}' out loud. Focus on each syllable. Let me know when you've tried it, or say 'next' for another word."
        
        # End the lesson if we don't recognize the type
        session["current_lesson"] = None
        return "Let's take a break from the lesson. What would you like to do next? You can look up words, analyze their structure, or start another lesson."
    
    def _process_with_llm(self, user_id: str, message_text: str) -> str:
        """Process a message using the LLM for natural language understanding"""
        session = self._get_session(user_id)
        
        # Create a conversation context
        messages = [{"role": "system", "content": self._create_system_prompt()}]
        
        # Add previous context (limited to last 5 exchanges)
        for ctx in session["context"][-5:]:
            messages.append(ctx)
        
        # Add the current message
        messages.append({"role": "user", "content": message_text})
        
        # Try to get a response from the LLM
        try:
            response = ollama.chat(
                model=self.llm_model,
                messages=messages,
                options={
                    "temperature": 0.7,
                    "num_predict": 1024
                }
            )
            
            # Extract the assistant's message
            assistant_message = response["message"]["content"]
            
            # Verify no made-up Woccon words are in the response
            verified_message = self._verify_no_made_up_words(assistant_message)
            
            # Update the context
            session["context"].append({"role": "user", "content": message_text})
            session["context"].append({"role": "assistant", "content": verified_message})
            
            # Check if the LLM response indicates it's trying to look up or analyze a word
            if any(x in verified_message.lower() for x in ["look up", "find the word", "analyze the word"]):
                # Extract potential Woccon word
                words = set()
                for word in self.woccon.dictionary.get("lexicon", []):
                    if word["woccon"].lower() in message_text.lower():
                        words.add(word["woccon"])
                
                if words:
                    word = list(words)[0]
                    return f"{verified_message}\n\n{self._analyze_word(word)}"
            
            return verified_message
            
        except Exception as e:
            logger.error(f"Error processing with LLM: {str(e)}")
            return self._process_without_llm(message_text)
            
    def _verify_no_made_up_words(self, message: str) -> str:
        """
        Verify that the message doesn't contain made-up Woccon words.
        If it does, replace the message with a warning.
        """
        # Get all legitimate Woccon words and their translations
        legitimate_words = {}
        for entry in self.woccon.dictionary.get("lexicon", []):
            legitimate_words[entry["woccon"].lower()] = entry["english"].lower()
            
        # Also check the phrases
        for phrase in self.woccon.dictionary.get("phrases", []):
            legitimate_words[phrase["woccon"].lower()] = phrase["english"].lower()
            
        # Create patterns that might indicate the LLM is making up content
        warning_patterns = [
            r"in woccon,? (?:the|a) word for",
            r"the woccon (?:term|word) for",
            r"woccon vocabulary includes",
            r"would be",
            r"might be",
            r"could be",
            r"inferred",
            r"reconstructed",
            r"translated as",
            r"means .* in woccon",
            r"repeat after me",
            r"say (it|these|this) with me",
            r"practice saying",
            r"pronounced",
            r"is pronounced"
        ]
        
        # Get color words from dictionary for verification
        real_color_words = []
        for word, meaning in legitimate_words.items():
            if any(color in meaning for color in ["red", "blue", "green", "yellow", "black", "white"]):
                real_color_words.append(f"{word} (meaning: {meaning})")
        
        # Actual color words from the dictionary
        documented_colors = {
            "red": "yauta",  # also means "turkey"
            "black": "yah-testea",  # also means "blue"
            "blue": "yah-testea",  # also means "black"
            "white": "waurraupa"
        }
        
        # Check the message for warning patterns
        contains_warning_pattern = any(re.search(pattern, message.lower()) for pattern in warning_patterns)
        
        # Scan for words that look like they're presented as Woccon but aren't in our dictionary
        non_english_words = set()
        lines = message.split('\n')
        for line in lines:
            # Skip lines that are clearly not claiming to be Woccon words
            if "**" in line or line.strip().startswith('#') or len(line.strip()) < 3:
                continue
                
            # Look for patterns like "Word: translation" or similar
            for word in re.findall(r'\b([a-zA-Z-]+)\b(?:\s*:\s|\s*\(|:|\s*-\s*|\s*=\s*)', line):
                word = word.lower().strip(".,!?()[]{}:;\"'")
                # If it's not an English word and not in our dictionary, flag it
                if (len(word) > 3 and 
                    word not in legitimate_words and 
                    not word in {"woccon", "lesson", "color", "pronounce", "pronounced", "hello", "warm", "activity"}):
                    non_english_words.add(word)
            
            # Also check for quoted words
            for word in re.findall(r'[""]([^""]+)["""]', line):
                word = word.lower().strip(".,!?()[]{}:;\"'")
                # If it's presented as Woccon but isn't in our dictionary, flag it
                if (len(word) > 3 and 
                    word not in legitimate_words and 
                    "pronounced" in line.lower() or "woccon" in line.lower()):
                    non_english_words.add(word)
        
        # Look for color words specifically
        fake_color_words = False
        for color in ["yellow", "green", "purple", "orange", "brown"]:
            if color in message.lower() and color not in ["black", "blue", "red", "white"]:
                # We don't have words for these colors in the dictionary
                fake_color_words = True
                break
                
        # If we suspect made-up content, create a correction message
        if (contains_warning_pattern and non_english_words) or fake_color_words:
            # Create a correction focusing on legitimate content
            correction = """I need to clarify something important about the Woccon language. 

Woccon is documented only through John Lawson's 1709 word list of approximately 140 terms. This limited vocabulary means that we don't have words for many common concepts, including most colors.

The only documented color words in Woccon are:
- "yah-testea" = black, blue
- "yauta" = red (also means "turkey")
- "waurraupa" = white

I cannot create or invent new Woccon words that aren't in this historical record. Instead, I can help you explore and learn the authentic documented vocabulary that we do have.

Would you like me to create a legitimate language lesson using only the documented Woccon words? I could focus on animals, numbers, or basic objects that are actually recorded in Lawson's list."""
            
            return correction
            
        # If we see "Hello" or greeting words, those are definitely fake
        if re.search(r'hello:\s*[""]?[a-z]+[""]?', message.lower(), re.IGNORECASE):
            return """I need to clarify an important point about the Woccon language: 

Woccon is documented only through John Lawson's 1709 word list of approximately 140 terms. This limited vocabulary means that we don't have words for many common concepts, including greetings like "hello" or "goodbye" (with the possible exception of "yuppa mei" which means "bye, go you").

I cannot create or invent new Woccon words that aren't in this historical record. Instead, I can help you explore and learn the authentic documented vocabulary that we do have.

Would you like me to create a legitimate language lesson using only the documented Woccon words? I could focus on animals, numbers, or basic objects that are actually recorded in Lawson's list."""
        
        return message
    
    def _process_without_llm(self, message_text: str) -> str:
        """Fallback method when LLM is not available - uses basic keyword matching"""
        message_lower = message_text.lower()
        
        # Check for word lookup intent
        if any(x in message_lower for x in ["what is", "what does", "mean", "translate"]):
            # Look for Woccon words in the message
            for word in self.woccon.dictionary.get("lexicon", []):
                if word["woccon"].lower() in message_lower:
                    return self._lookup_word(word["woccon"])
            
            # Try to find English words to translate
            content_words = [word for word in message_lower.split() if len(word) > 3]
            for word in content_words:
                results = self._lookup_word(word)
                if "couldn't find" not in results:
                    return results
        
        # Check for analysis intent
        if any(x in message_lower for x in ["analyze", "structure", "breakdown", "roots", "affixes"]):
            # Look for Woccon words in the message
            for word in self.woccon.dictionary.get("lexicon", []):
                if word["woccon"].lower() in message_lower:
                    return self._analyze_word(word["woccon"])
        
        # Check for lesson intent
        if any(x in message_lower for x in ["learn", "lesson", "teach", "practice"]):
            lesson_types = ["vocabulary", "analyze", "pronunciation"]
            for lesson_type in lesson_types:
                if lesson_type in message_lower:
                    return self._start_lesson("default_user", lesson_type)
            
            # If no specific type, default to vocabulary
            return self._start_lesson("default_user", "vocabulary")
        
        # Default response
        return self._get_help_message()
    
    def _get_help_message(self) -> str:
        """Generate a help message"""
        return """🗣️ Woccon Language Assistant 🗣️

I can help you explore and learn the Woccon language. Here's what I can do:

1️⃣ Look up words
   • "lookup: fire" (English to Woccon)
   • "lookup: yau" (Woccon to English)

2️⃣ Analyze word structure
   • "analyze: yawowa"
   • "breakdown: tauh-he"

3️⃣ Provide language lessons
   • "lesson: vocabulary" (learn vocabulary)
   • "lesson: analyze" (study word structure) 
   • "lesson: pronunciation" (practice speaking)

4️⃣ Answer questions about Woccon
   • Just ask me anything about the language!

Remember, Woccon is documented primarily through a word list of about 140 terms collected in 1709, so I'll focus on what we know for certain."""
    
    def _get_category_keywords(self, category: str) -> List[str]:
        """Get keywords for a specific category"""
        categories = {
            "animals": ["fish", "snake", "bird", "dog", "wolf", "squirrel", "panther"],
            "water_related": ["water", "rain", "fish", "river", "stream", "wet"],
            "clothing": ["cloth", "blanket", "shirt", "wear", "breech", "stocking", "hide", "skin", "buckskin"],
            "containers": ["container", "bottle", "bowl", "basket", "box", "gourd"],
            "body_parts": ["head", "hand", "body", "foot", "hair", "face"],
            "natural_elements": ["tree", "wood", "fire", "stone", "rock", "earth"],
            "tools": ["tool", "knife", "axe", "spoon", "hoe", "needle", "gunpowder", "weapon"],
            "cultural_terms": ["indian", "chief", "warrior", "spirit", "ceremony", "hominy", "skin", "hide", "buckskin"]
        }
        
        return categories.get(category, [])


# Facebook Messenger integration
class MessengerBot:
    def __init__(self, page_access_token: str, verify_token: str = "woccon_bot_verify_token"):
        """
        Initialize the Messenger Bot
        
        Args:
            page_access_token: Facebook Page Access Token
            verify_token: Webhook verification token
        """
        self.page_access_token = page_access_token
        self.verify_token = verify_token
        self.woccon_assistant = WocconLanguageAssistant()
        logger.info("Messenger Bot initialized")
    
    def verify_webhook(self, mode: str, token: str, challenge: str) -> str:
        """Verify webhook for Facebook integration"""
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verified")
            return challenge
        else:
            logger.warning("Webhook verification failed")
            return "Verification token mismatch", 403
    
    def process_webhook(self, data: Dict) -> bool:
        """Process incoming webhook data from Messenger"""
        if data.get("object") != "page":
            logger.warning("Received non-page object")
            return False
        
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                # Get the sender ID
                sender_id = messaging_event.get("sender", {}).get("id")
                
                # Check if this is a message event
                if messaging_event.get("message"):
                    message_text = messaging_event.get("message", {}).get("text", "")
                    
                    if message_text:
                        logger.info(f"Received message from {sender_id}: {message_text}")
                        
                        # Send typing indicator
                        self.send_typing_indicator(sender_id)
                        
                        # Process the message
                        response = self.woccon_assistant.handle_message(sender_id, message_text)
                        
                        # Send the response
                        self.send_message(sender_id, response)
        
        return True
    
    def send_message(self, recipient_id: str, message_text: str):
        """Send a message to the specified recipient via Messenger API"""
        # Split long messages to respect Messenger's limits
        if len(message_text) > 2000:
            chunks = self._split_message(message_text)
            for chunk in chunks:
                self._send_message_request(recipient_id, chunk)
        else:
            self._send_message_request(recipient_id, message_text)
    
    def _send_message_request(self, recipient_id: str, message_text: str):
        """Send actual message request to Messenger API"""
        params = {
            "access_token": self.page_access_token
        }
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "text": message_text
            }
        }
        
        try:
            response = requests.post(
                "https://graph.facebook.com/v15.0/me/messages",
                params=params,
                headers=headers,
                json=data
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to send message: {response.text}")
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
    
    def send_typing_indicator(self, recipient_id: str, is_typing: bool = True):
        """Send a typing indicator to the user"""
        params = {
            "access_token": self.page_access_token
        }
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "recipient": {
                "id": recipient_id
            },
            "sender_action": "typing_on" if is_typing else "typing_off"
        }
        
        try:
            requests.post(
                "https://graph.facebook.com/v15.0/me/messages",
                params=params,
                headers=headers,
                json=data
            )
        except Exception as e:
            logger.error(f"Error sending typing indicator: {str(e)}")
    
    def _split_message(self, message: str, max_length: int = 2000) -> List[str]:
        """Split a long message into chunks respecting Messenger's limits"""
        chunks = []
        
        # Check if the message needs splitting
        if len(message) <= max_length:
            return [message]
        
        # Split on natural boundaries if possible
        paragraphs = message.split("\n\n")
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed the limit, start a new chunk
            if len(current_chunk) + len(paragraph) + 2 > max_length:
                # If the current chunk isn't empty, add it to chunks
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # If the paragraph itself is too long, split it
                if len(paragraph) > max_length:
                    sentences = paragraph.split(". ")
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 2 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk)
                                current_chunk = ""
                            
                            # If even a single sentence is too long, force split it
                            if len(sentence) > max_length:
                                words = sentence.split(" ")
                                for word in words:
                                    if len(current_chunk) + len(word) + 1 > max_length:
                                        chunks.append(current_chunk)
                                        current_chunk = word + " "
                                    else:
                                        current_chunk += word + " "
                            else:
                                current_chunk = sentence + ". "
                        else:
                            current_chunk += sentence + ". "
                else:
                    current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"
        
        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks


# Flask web server for Messenger webhook
from flask import Flask, request, Response

app = Flask(__name__)

# Initialize the Messenger Bot
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN', '')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'woccon_bot_verify_token')
messenger_bot = MessengerBot(PAGE_ACCESS_TOKEN, VERIFY_TOKEN)

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Verify webhook for Facebook integration"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    result = messenger_bot.verify_webhook(mode, token, challenge)
    
    if isinstance(result, tuple):
        return result
    
    return result

@app.route('/webhook', methods=['POST'])
def webhook():
    """Process incoming messages from Messenger"""
    data = request.get_json()
    
    messenger_bot.process_webhook(data)
    
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    """Simple index page to confirm the server is running"""
    return "Woccon Language Assistant is running!"

def run_server():
    """Run the Flask server"""
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    # If running standalone, start a test CLI interface if desired
    import argparse
    
    parser = argparse.ArgumentParser(description="Woccon Language Assistant")
    parser.add_argument("--cli", action="store_true", help="Start CLI interface instead of web server")
    parser.add_argument("--messenger", action="store_true", help="Start Messenger webhook server")
    parser.add_argument("--test", action="store_true", help="Run test examples")
    parser.add_argument("--model", type=str, default="llama3.2:3b", help="Specify the LLM model to use")
    args = parser.parse_args()
    
    if args.cli:
        # Run a simple CLI for testing
        print("Starting Woccon Language Assistant CLI...")
        assistant = WocconLanguageAssistant(llm_model=args.model)
        
        print("\n🗣️ Woccon Language Assistant 🗣️")
        print("Type 'help' for available commands or 'quit' to exit")
        
        while True:
            try:
                user_input = input("\nwoccon> ").strip()
                
                # Handle empty input
                if not user_input:
                    continue
                
                # Check for quit command
                if user_input.lower() in ["quit", "exit", "q"]:
                    print("Exiting Woccon CLI. Goodbye!")
                    break
                
                # Process the input
                response = assistant.handle_message("cli_user", user_input)
                print("\n" + response)
                
            except KeyboardInterrupt:
                print("\nExiting Woccon CLI. Goodbye!")
                break
                
            except Exception as e:
                print(f"Error: {str(e)}")
    
    elif args.messenger:
        # Run the Messenger webhook server
        print("Starting Messenger webhook server...")
        # Initialize the Messenger Bot with the specified model
        messenger_bot = MessengerBot(PAGE_ACCESS_TOKEN, VERIFY_TOKEN)
        messenger_bot.woccon_assistant = WocconLanguageAssistant(llm_model=args.model)
        run_server()
    
    elif args.test:
        # Run a simple test
        assistant = WocconLanguageAssistant(llm_model=args.model)
        
        # Test a few examples
        test_inputs = [
            "lookup: fire",
            "analyze: yawowa",
            "What is the word for dog in Woccon?",
            "Tell me about Woccon language",
            "lesson: vocabulary"
        ]
        
        print("\n=== WOCCON LANGUAGE ASSISTANT TEST ===\n")
        
        for test_input in test_inputs:
            print(f"INPUT: {test_input}")
            response = assistant.handle_message("test_user", test_input)
            print(f"RESPONSE: {response}\n")
            print("-" * 50 + "\n")
        
        print("Test complete. Run with --cli for interactive mode or --messenger to start the webhook server.")
    
    else:
        # By default, just show help information
        print("\nWoccon Language Assistant")
        print("========================\n")
        print("Available command-line options:")
        print("  --cli         Start an interactive CLI")
        print("  --messenger   Start the Messenger webhook server")
        print("  --test        Run test examples")
        print("  --model       Specify the LLM model (default: llama3.2:3b)")
        print("\nExample usage:")
        print("  python woccon_llama_integration.py --cli")
        print("  python woccon_llama_integration.py --test --model llama3:8b")
        print("  python woccon_llama_integration.py --messenger")