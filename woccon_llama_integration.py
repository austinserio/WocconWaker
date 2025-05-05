"""
Enhanced Woccon Assistant with RAG capabilities.
This version combines rule-based responses with strategic LLM usage.
"""

import os
import sys
import json
import logging
import random
import re
from typing import Dict, List, Any, Optional, Set, Tuple
import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("woccon_assistant")

# Import the WocconT5 class
from main import WocconT5

# Optional: Try to import Ollama for LLM capabilities
try:
    import ollama
    OLLAMA_AVAILABLE = True
    logger.info("Ollama imported successfully.")
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available. LLM features will be disabled.")

class WocconAssistant:
    """
    Enhanced Woccon language assistant with RAG capabilities.
    Uses rule-based responses with strategic LLM usage.
    """
    
    def __init__(self, llm_model: str = "llama3.2:3b"):
        """Initialize the Woccon assistant."""
        logger.info("Initializing Enhanced Woccon Assistant...")
        
        # Initialize WocconT5
        self.woccon = WocconT5()
        
        # Load dictionary and rules files from source of truth
        self.document_store = {
            "dictionary": self._load_json_file("woccon_language/dictionary.json"),
            "rules": self._load_json_file("woccon_language/rules.json")
        }
        
        # Get all documented Woccon words for verification
        self.documented_words = set()
        for entry in self.woccon.dictionary.get("lexicon", []):
            self.documented_words.add(entry["woccon"].lower())
            
        logger.info(f"Loaded {len(self.documented_words)} documented Woccon words.")
        
        # Get all documented grammatical rules for verification
        self.documented_rules = set()
        if "grammar" in self.document_store.get("rules", {}):
            for rule in self.document_store["rules"]["grammar"]:
                self.documented_rules.add(rule["name"].lower())
        
        logger.info(f"Loaded {len(self.documented_rules)} documented grammatical rules.")
        
        # Initialize LLM if available
        self.llm_model = llm_model
        self.llm_available = False
        
        if OLLAMA_AVAILABLE:
            try:
                ollama.list()
                self.llm_available = True
                logger.info(f"LLM initialized with model: {llm_model}")
                # If LLM is available, prepare RAG components
                self._prepare_rag_components()
            except Exception as e:
                logger.warning(f"Could not initialize LLM: {str(e)}")
        
        # User sessions for context
        self.user_sessions = {}
        
        # Help message
        self.help_message = """🗣️ Woccon Language Assistant 🗣️

I can help you explore the documented Woccon language from John Lawson's 1709 word list.

Commands:
1️⃣ Look up words:
   • `lookup: [word]` - Search for a Woccon or English word
   • Or simply ask "What does [word] mean?" or "What's the Woccon word for [term]?"
   
2️⃣ Analyze Woccon words:
   • `analyze: [word]` - Get morphological breakdown of a word
   • Or ask "Break down the word [word]" or "What are the parts of [word]?"
   
3️⃣ Browse words by category:
   • `category: animals` - See words in a category
   • Or ask "Show me Woccon words for animals" or "What body part words exist in Woccon?"
   • Available categories: animals, tools, body_parts, clothing, containers, food
   
4️⃣ Interactive learning:
   • `learn: vocabulary` - Start a vocabulary lesson
   • `learn: analyze` - Learn about word structure

5️⃣ General questions:
   • Ask me about the Woccon language, its history, or related languages
   • I'll use only documented information to answer your questions

Remember: My knowledge is strictly limited to the ~140 words in Lawson's list.
I cannot create or generate new Woccon words beyond this documentation.
"""
    
    def _load_json_file(self, filepath: str) -> Dict:
        """Load a JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {str(e)}")
            return {}
    
    def _prepare_rag_components(self):
        """Prepare RAG components for the assistant."""
        # Create chunks from dictionary entries
        self.dictionary_chunks = []
        for entry in self.document_store["dictionary"].get("lexicon", []):
            # Create a chunk of content from each dictionary entry
            chunk = f"Woccon: {entry['woccon']}, English: {entry['english']}, POS: {entry['pos']}"
            if "notes" in entry:
                chunk += f", Notes: {entry['notes']}"
            self.dictionary_chunks.append(chunk)
        
        # Create chunks from grammatical rules
        self.rules_chunks = []
        if "grammar" in self.document_store.get("rules", {}):
            for rule in self.document_store["rules"]["grammar"]:
                chunk = f"Rule: {rule['name']}, Description: {rule['description']}"
                if "examples" in rule:
                    examples = "; ".join(rule["examples"])
                    chunk += f", Examples: {examples}"
                self.rules_chunks.append(chunk)
        
        # Create chunks from general information
        self.general_chunks = []
        if "general_info" in self.document_store.get("rules", {}):
            for info in self.document_store["rules"]["general_info"]:
                chunk = f"Topic: {info['topic']}, Information: {info['content']}"
                self.general_chunks.append(chunk)
        
        logger.info(f"Prepared RAG components: {len(self.dictionary_chunks)} dictionary chunks, "
                   f"{len(self.rules_chunks)} rules chunks, {len(self.general_chunks)} general info chunks")
    
    def _get_session(self, user_id: str) -> Dict[str, Any]:
        """Get or create a user session."""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                "current_activity": None,
                "history": []
            }
        return self.user_sessions[user_id]
    
    def handle_message(self, user_id: str, message_text: str) -> str:
        """Process a message with enhanced natural language understanding."""
        message_lower = message_text.lower().strip()
        session = self._get_session(user_id)
        
        # Log the message
        logger.info(f"Received message from {user_id}: {message_text}")
        
        # Add to session history
        session["history"].append({"role": "user", "content": message_text})
        
        # Special commands
        if message_lower in ["help", "menu", "commands", "?"]:
            response = self.help_message
            
        elif message_lower in ["quit", "exit", "stop", "end"]:
            session["current_activity"] = None
            response = "Session ended. Type 'help' to see available commands."
        
        # Command patterns
        elif message_lower.startswith(("lookup:", "find:", "search:")):
            term = message_text.split(":", 1)[1].strip()
            response = self._lookup_word(term)
            
        elif message_lower.startswith(("analyze:", "breakdown:")):
            word = message_text.split(":", 1)[1].strip()
            response = self._analyze_word(word)
            
        elif message_lower.startswith(("category:", "cat:")):
            category = message_text.split(":", 1)[1].strip()
            response = self._browse_category(category)
            
        elif message_lower.startswith(("learn:", "lesson:")):
            lesson_type = message_text.split(":", 1)[1].strip()
            response = self._start_lesson(user_id, lesson_type)
            
        # Continue ongoing activity if there is one
        elif session["current_activity"]:
            activity_type = session["current_activity"]["type"]
            
            if activity_type == "vocabulary_lesson":
                response = self._continue_vocabulary_lesson(user_id, message_text)
                
            elif activity_type == "analysis_lesson":
                response = self._continue_analysis_lesson(user_id, message_text)
        
        # Enhanced NLU patterns - check these after ongoing activities
        elif self._is_asking_for_meaning(message_lower):
            term = self._extract_term_for_meaning(message_lower)
            # Debug log
            logger.info(f"Detected meaning question. Extracted term: '{term}'")
            response = self._lookup_word(term)
            
        elif self._is_asking_for_analysis(message_lower):
            word = self._extract_term_for_analysis(message_lower)
            # Debug log
            logger.info(f"Detected analysis question. Extracted word: '{word}'")
            response = self._analyze_word(word)
            
        elif self._is_asking_for_category(message_lower):
            category = self._extract_category(message_lower)
            # Debug log
            logger.info(f"Detected category question. Extracted category: '{category}'")
            response = self._browse_category(category)
            
        # Extremely simple queries - try to be smart about what the user wants
        elif len(message_lower.split()) <= 2:
            # Is it a single word that might be a Woccon word?
            if len(message_lower.split()) == 1 and message_lower in self.documented_words:
                logger.info(f"Single Woccon word query detected: '{message_lower}'")
                response = self._lookup_woccon_term(message_lower)
            # Is it a simple English word or phrase?
            else:
                logger.info(f"Treating simple query as lookup: '{message_lower}'")
                # Clean up the term
                term = re.sub(r'[\'"\.,?!]', '', message_lower)
                # Try to look it up as an English word
                response = self._lookup_english_term(term)
        
        # Use RAG for general questions
        elif self.llm_available:
            logger.info(f"Using RAG for general question: '{message_lower}'")
            response = self._process_with_rag(user_id, message_text)
        else:
            response = "I didn't understand that command. Type 'help' to see what I can do."
        
        # Add to session history
        session["history"].append({"role": "assistant", "content": response})
        
        return response
    
    def _is_asking_for_meaning(self, message: str) -> bool:
        """Check if user is asking for word meaning."""
        # More flexible patterns for common ways to ask about meaning
        patterns = [
            # "What does X mean"
            r"what( does|'s| is) .*?([a-z-]+).*?( mean| translate)",
            # "Translate/define X"
            r"(translate|define|meaning of) .*?([a-z-]+)",
            # "How do you say X in Woccon"
            r"how (do you say|would you say|to say|say) .*?([^?]+?)( in woccon)?",
            # "What's the Woccon word for X"
            r"what('s| is) the( woccon)?( word)?( word)? for .*?([^?]+)",
            # Simple queries matching common patterns
            r"(woccon for|word for|say) ([^?]+)",
            r"([a-z-]+) in( woccon| english)",
            r"([a-z-]+) means",
            # Handles simple queries like "what's fish" or "how do you say water"
            r"(what'?s|what is|how .*say) ([a-z ]+)"
        ]
        return any(re.search(pattern, message) for pattern in patterns)
    
    def _extract_term_for_meaning(self, message: str) -> str:
        """Extract the term being asked about from a meaning question."""
        message = message.lower().strip()
        
        # Try extracting a Woccon term first
        woccon_patterns = [
            r"what( does|'s| is) .*?([a-z-]+).*?( mean| translate)",
            r"(translate|define|meaning of) .*?([a-z-]+)",
            r"([a-z-]+) means",
            r"([a-z-]+) in english"
        ]
        
        for pattern in woccon_patterns:
            match = re.search(pattern, message)
            if match:
                # Extract group and clean up any quotes or punctuation
                term = match.group(2).strip()
                return re.sub(r'[\'"\.,?!]', '', term)
        
        # Then try extracting an English term
        english_patterns = [
            r"how .* say .*?([^?]+?)( in woccon)?$",
            r"what('s| is) the( woccon)?( word)?( word)? for .*?([^?]+)",
            r"(woccon for|word for|say) ([^?]+)",
            r"([a-z ]+) in woccon",
            r"(what'?s|what is) ([a-z ]+)"
        ]
        
        for pattern in english_patterns:
            match = re.search(pattern, message)
            if match:
                # Different group index depending on pattern
                if "say" in pattern and "how" in pattern:
                    group_index = 1
                elif "for" in pattern and "what" in pattern:
                    group_index = 5
                elif "for" in pattern and not "what" in pattern:
                    group_index = 2
                elif "in woccon" in pattern:
                    group_index = 1
                else:
                    group_index = 2
                
                # Clean up any quotes, punctuation and extra spaces
                term = match.group(group_index).strip()
                term = re.sub(r'[\'"\.,?!]', '', term)
                
                # Handle some common articles and stop words
                term = re.sub(r'^(the|a|an) ', '', term)
                
                return term.strip()
        
        # Default fallback - extract any quoted word
        quoted_match = re.search(r"['\"]([^'\"]+)['\"]", message)
        if quoted_match:
            return quoted_match.group(1).strip()
        
        # Desperate fallback - just take the last few words if they look like they could be a term
        words = message.split()
        if len(words) >= 2:
            # Try last word
            if len(words[-1]) > 2 and words[-1] not in ["mean", "say", "woccon", "english", "translate"]:
                return words[-1]
            # Try last two words
            if len(words) >= 3 and words[-2] not in ["in", "for", "to", "the", "a", "an"]:
                return words[-2]
        
        # Final fallback - return empty string
        return ""
    
    def _is_asking_for_analysis(self, message: str) -> bool:
        """Check if user is asking for word analysis."""
        patterns = [
            # Explicit analysis requests
            r"(analyze|analyse|break down|breakdown|explain|structure of) .*?([a-z-]+)",
            r"(what are|show|tell me about) the (parts|structure|makeup|formation|analysis) of .*?([a-z-]+)",
            r"how is .*?([a-z-]+).*?( formed| structured| made up| built| constructed)?",
            r"(morphology|etymology|roots|affixes|composition) of .*?([a-z-]+)",
            # More casual/ambiguous analysis requests
            r"(what|how) .* (made|composed|structured)",
            r"(details|more info|components|elements) .* ([a-z-]+)",
            r"break .*? ([a-z-]+) .* (down|apart)",
            r"([a-z-]+) .* (structure|analysis|breakdown)"
        ]
        return any(re.search(pattern, message) for pattern in patterns)
    
    def _extract_term_for_analysis(self, message: str) -> str:
        """Extract the term being asked about from an analysis question."""
        message = message.lower().strip()
        
        patterns = [
            r"(analyze|analyse|break down|breakdown|explain|structure of) .*?([a-z-]+)",
            r"(what are|show|tell me about) the (parts|structure|makeup|formation|analysis) of .*?([a-z-]+)",
            r"how is .*?([a-z-]+).*?( formed| structured| made up| built| constructed)?",
            r"(morphology|etymology|roots|affixes|composition) of .*?([a-z-]+)",
            r"break .*? ([a-z-]+) .* (down|apart)",
            r"([a-z-]+) .* (structure|analysis|breakdown)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                # Extract the term based on pattern
                if "of" in pattern and "parts" in pattern:
                    term = match.group(3)
                elif "how is" in pattern:
                    term = match.group(1)
                elif "break" in pattern and "down" in pattern:
                    term = match.group(1)
                elif "structure|analysis" in pattern:
                    term = match.group(1)
                else:
                    term = match.group(2)
                
                # Clean up any quotes or punctuation
                term = re.sub(r'[\'"\.,?!]', '', term.strip())
                return term
        
        # Default fallback - extract any quoted word
        quoted_match = re.search(r"['\"]([^'\"]+)['\"]", message)
        if quoted_match:
            return quoted_match.group(1).strip()
        
        # Look for words that might be Woccon
        words = message.split()
        for word in words:
            # If it looks like it could be a Woccon word and is in our dictionary
            word = re.sub(r'[\'"\.,?!]', '', word)
            if word in self.documented_words:
                return word
        
        # Final fallback - try to find the most word-like term in the message
        words = message.split()
        for word in words:
            clean_word = re.sub(r'[\'"\.,?!]', '', word)
            # If it's longer than 3 chars and not a common English word
            if len(clean_word) > 3 and clean_word not in ["what", "where", "when", "analyze", "analysis", "structure", "word"]:
                return clean_word
        
        # Absolutely final fallback - return empty string
        return ""
    
    def _is_asking_for_category(self, message: str) -> bool:
        """Check if user is asking for words in a category."""
        patterns = [
            # Explicit category requests
            r"(show|list|give|tell) me( all)? .*?(woccon )?words .*?(for|about|related to|in) ([a-z ]+)",
            r"what (woccon )?words (exist|are there|do you have)( for| about| related to| in)? ([a-z ]+)",
            r"words (in|for|about) (the )?([a-z ]+)( category)?",
            r"([a-z ]+) words in woccon",
            # More casual category requests
            r"(animals|tools|body parts|food|weather|colors|containers|clothing) in woccon",
            r"woccon (animals|tools|body parts|food|weather|colors|containers|clothing)",
            r"(all|some|any) (animals|tools|body parts|food|weather|colors|containers|clothing)",
            r"(do you have|are there) (animals|tools|body parts|food|weather|colors|containers|clothing)",
            r"(category|group|words about|words for) ([a-z ]+)"
        ]
        return any(re.search(pattern, message) for pattern in patterns)
    
    def _extract_category(self, message: str) -> str:
        """Extract the category being asked about."""
        message = message.lower().strip()
        
        # Common categories to look for directly
        common_categories = ["animals", "tools", "weapons", "body parts", "clothing", 
                            "containers", "food", "colors", "weather", "time"]
        
        # Direct category mention - simplest case
        for category in common_categories:
            if category in message:
                return category
        
        # More complex pattern matching
        patterns = [
            r"(show|list|give|tell) me( all)? .*?(woccon )?words .*?(for|about|related to|in) ([a-z ]+)",
            r"what (woccon )?words (exist|are there|do you have)( for| about| related to| in)? ([a-z ]+)",
            r"words (in|for|about) (the )?([a-z ]+)( category)?",
            r"([a-z ]+) words in woccon",
            r"(category|group|words about|words for) ([a-z ]+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                # Extract the category based on the pattern
                if "for|about|related to|in" in pattern and "show|list|give|tell" in pattern:
                    category = match.group(5)
                elif "exist|are there|do you have" in pattern:
                    category = match.group(4 if "in" in match.group(0) else 5)
                elif "words (in|for|about)" in pattern:
                    category = match.group(3)
                elif "words in woccon" in pattern:
                    category = match.group(1)
                elif "category|group|words about|words for" in pattern:
                    category = match.group(2)
                else:
                    # Fallback to last word if pattern matching fails
                    words = message.split()
                    category = words[-1]
                
                # Clean up the category
                category = re.sub(r'[\'"\.,?!]', '', category.strip())
                
                # Handle some special cases to normalize category names
                category_map = {
                    "animal": "animals",
                    "tool": "tools",
                    "weapon": "tools",
                    "weapons": "tools",
                    "body": "body parts",
                    "body part": "body parts",
                    "container": "containers",
                    "color": "colors",
                    "colour": "colors",
                    "colours": "colors",
                    "cloth": "clothing",
                    "clothes": "clothing"
                }
                
                if category in category_map:
                    category = category_map[category]
                
                return category
        
        # Complete fallback - look for anything that might be a category
        category_hints = ["category", "group", "type", "kind", "class", "words for", "words about"]
        for hint in category_hints:
            if hint in message:
                # Get the word after the hint
                parts = message.split(hint)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip().split()[0]
        
        # Final fallback - return empty string
        return ""
    
    def _lookup_word(self, term: str) -> str:
        """Look up a word in either direction."""
        if not term:
            return "I'm not sure which word you're asking about. Please specify a word to look up."
        
        # Check if it's a Woccon word first
        woccon_results = self._lookup_woccon_term(term)
        
        # If not found as Woccon, try English
        if "I don't recognize" in woccon_results:
            return self._lookup_english_term(term)
        
        return woccon_results
    
    def _lookup_woccon_term(self, term: str) -> str:
        """Look up a Woccon word."""
        term = term.lower()
        
        # Check for exact match
        entry = self.woccon.lookup_word(term, "woc_to_eng")
        if entry:
            return f"""📚 Woccon word: {entry['woccon']}
Meaning: {entry['english']}
Part of speech: {entry['pos']}

This word is documented in John Lawson's 1709 Woccon word list."""
        
        # Check for partial matches
        partial_matches = []
        for word in self.woccon.dictionary.get("lexicon", []):
            if term in word["woccon"].lower():
                partial_matches.append(word)
        
        if partial_matches:
            response = f"I don't recognize '{term}' exactly, but found {len(partial_matches)} similar Woccon words:\n\n"
            for word in partial_matches[:5]:  # Limit to 5 results
                response += f"- {word['woccon']} = {word['english']} ({word['pos']})\n"
            
            if len(partial_matches) > 5:
                response += f"\n... and {len(partial_matches) - 5} more matches."
                
            return response
        
        return f"I don't recognize '{term}' as a documented Woccon word. There are only about 140 documented Woccon words from Lawson's 1709 list."
    
    def _lookup_english_term(self, term: str) -> str:
        """Look up an English term."""
        term = term.lower()
        
        # Check for exact match
        entry = self.woccon.lookup_word(term, "eng_to_woc")
        if entry:
            return f"""📚 English term: {term}
Woccon word: {entry['woccon']}
Part of speech: {entry['pos']}

This word is documented in John Lawson's 1709 Woccon word list."""
        
        # Check for partial matches
        partial_matches = []
        for word in self.woccon.dictionary.get("lexicon", []):
            if term in word["english"].lower():
                partial_matches.append(word)
        
        if partial_matches:
            response = f"I don't have an exact match for '{term}', but found {len(partial_matches)} related Woccon words:\n\n"
            for word in partial_matches[:5]:  # Limit to 5 results
                response += f"- {word['woccon']} = {word['english']} ({word['pos']})\n"
            
            if len(partial_matches) > 5:
                response += f"\n... and {len(partial_matches) - 5} more matches."
                
            return response
        
        return f"I don't have a documented Woccon word for '{term}'. There are only about 140 documented Woccon words from Lawson's 1709 list."
    
    def _analyze_word(self, word: str) -> str:
        """Analyze a Woccon word's structure."""
        if not word:
            return "I'm not sure which word you want me to analyze. Please specify a Woccon word."
            
        word = word.lower()
        
        # Check if the word exists
        entry = self.woccon.lookup_word(word, "woc_to_eng")
        if not entry:
            return f"I don't recognize '{word}' as a documented Woccon word. There are only about 140 documented Woccon words from Lawson's 1709 list."
        
        # Get analysis
        analysis = self.woccon.analyze_word(word)
        
        # Format the result
        result = [f"📝 Analysis of '{word}':"]
        result.append(f"Meaning: {entry['english']}")
        result.append(f"Part of speech: {entry['pos']}\n")
        
        # Show affixes
        if analysis["affixes"]:
            result.append("Affixes Found:")
            for affix in analysis["affixes"]:
                result.append(f"- {affix['type'].capitalize()} '{affix['form']}' = {affix['function']} ({affix.get('confidence', 'medium')} confidence)")
            result.append("")
        
        # Show roots
        if analysis["roots"]:
            result.append("Roots Found:")
            for root in analysis["roots"]:
                result.append(f"- {root['match_type'].capitalize()} '{root['root']}' = '{root['meaning']}' ({root['confidence']} confidence)")
                if root.get("note"):
                    result.append(f"  Note: {root['note']}")
            result.append("")
        
        # Show sound correspondences
        if analysis["sound_links"]:
            result.append("Sound Correspondences:")
            for link in analysis["sound_links"]:
                result.append(f"- Woccon '{link['woccon']}' corresponds to Catawba '{link['catawba']}'")
            result.append("")
        
        # Show semantic groups (categories)
        if analysis.get("semantic_groups"):
            categories = list(analysis["semantic_groups"].keys())
            if categories:
                result.append(f"This word belongs to these categories: {', '.join(categories)}")
        
        return "\n".join(result)
    
    def _browse_category(self, category: str) -> str:
        """Browse words in a semantic category."""
        if not category:
            return "Please specify a category to browse. Available categories include: animals, tools, body_parts, clothing, containers, food."
            
        category = category.lower().replace(" ", "_")
        
        # Map common variations
        category_map = {
            "animal": "animals",
            "tool": "tools",
            "weapon": "tools",
            "container": "containers",
            "body": "body_parts",
            "body_part": "body_parts",
            "color": "colors",
            "colour": "colors",
            "weather": "weather",
            "time": "time",
            "food": "food",
            "cloth": "clothing",
            "clothes": "clothing"
        }
        
        if category in category_map:
            category = category_map[category]
        
        # Find words in this category
        category_words = []
        for word in self.woccon.dictionary.get("lexicon", []):
            analysis = self.woccon.analyze_word(word["woccon"])
            if analysis.get("semantic_groups") and category in analysis["semantic_groups"]:
                category_words.append(word)
        
        if not category_words:
            return f"I couldn't find any documented Woccon words in the '{category}' category. Try another category like: animals, tools, body_parts, clothing, containers, food."
        
        # Format the result
        result = [f"📚 Woccon words in the '{category}' category:"]
        
        for word in category_words:
            result.append(f"- {word['woccon']} = {word['english']} ({word['pos']})")
            
        result.append(f"\nFound {len(category_words)} words in this category.")
        
        return "\n".join(result)
    
    def _start_lesson(self, user_id: str, lesson_type: str) -> str:
        """Start an interactive lesson."""
        session = self._get_session(user_id)
        lesson_type = lesson_type.lower()
        
        if lesson_type in ["vocab", "vocabulary", "words"]:
            return self._start_vocabulary_lesson(user_id)
        elif lesson_type in ["analyze", "analysis", "structure"]:
            return self._start_analysis_lesson(user_id)
        else:
            return f"I don't recognize the lesson type '{lesson_type}'. Available options are 'vocabulary' or 'analyze'."
    
    def _start_vocabulary_lesson(self, user_id: str) -> str:
        """Start a vocabulary lesson."""
        session = self._get_session(user_id)
        
        # Choose a semantic category
        categories = ["animals", "tools", "body_parts", "clothing", "containers", "food"]
        category = random.choice(categories)
        
        # Find words in this category
        category_words = []
        for word in self.woccon.dictionary.get("lexicon", []):
            analysis = self.woccon.analyze_word(word["woccon"])
            if analysis.get("semantic_groups") and category in analysis["semantic_groups"]:
                category_words.append(word)
        
        if not category_words:
            # Fallback to random words if category is empty
            category_words = random.sample(self.woccon.dictionary.get("lexicon", []), 
                                          min(5, len(self.woccon.dictionary.get("lexicon", []))))
        
        # Select up to 5 words
        selected_words = random.sample(category_words, min(5, len(category_words)))
        
        # Set up the lesson
        session["current_activity"] = {
            "type": "vocabulary_lesson",
            "category": category,
            "words": selected_words,
            "current_index": 0,
            "learned_words": []
        }
        
        # Create introduction
        result = [f"📚 Welcome to your Woccon Vocabulary Lesson: {category.replace('_', ' ').title()} 📚"]
        result.append(f"I'll introduce you to {len(selected_words)} Woccon words from John Lawson's 1709 word list.")
        result.append("Let's get started with your first word!\n")
        
        # Add the first word
        current_word = selected_words[0]
        result.append(f"🔹 Woccon: {current_word['woccon']}")
        result.append(f"🔹 English: {current_word['english']}")
        result.append(f"🔹 Part of speech: {current_word['pos']}\n")
        
        result.append("Try saying this word out loud! When you're ready, type 'next' to continue or 'more' to learn about this word's structure.")
        
        return "\n".join(result)
    
    def _continue_vocabulary_lesson(self, user_id: str, message_text: str) -> str:
        """Continue a vocabulary lesson."""
        session = self._get_session(user_id)
        activity = session["current_activity"]
        
        message_lower = message_text.lower().strip()
        
        # Check for exit command
        if message_lower in ["quit", "exit", "stop", "end"]:
            session["current_activity"] = None
            return "Vocabulary lesson ended. Type 'help' to see other commands."
        
        # Check for analysis request
        if message_lower in ["more", "analyze", "details", "structure"]:
            current_word = activity["words"][activity["current_index"]]
            return self._analyze_word(current_word["woccon"])
        
        # Check for next word request
        if message_lower in ["next", "continue", "go on"]:
            # Move to next word
            activity["current_index"] += 1
            
            # Check if we've reached the end
            if activity["current_index"] >= len(activity["words"]):
                session["current_activity"] = None
                return "🎉 Congratulations! You've completed the vocabulary lesson. Type 'learn: vocabulary' to start another one, or 'help' to see other commands."
            
            # Show the next word
            current_word = activity["words"][activity["current_index"]]
            
            result = [f"Great! Here's your next word:"]
            result.append(f"🔹 Woccon: {current_word['woccon']}")
            result.append(f"🔹 English: {current_word['english']}")
            result.append(f"🔹 Part of speech: {current_word['pos']}\n")
            
            result.append("Try saying this word out loud! When you're ready, type 'next' to continue or 'more' to learn about this word's structure.")
            
            return "\n".join(result)
        
        # Otherwise, just provide a hint
        return "Type 'next' to see the next word, 'more' to analyze the current word, or 'quit' to end the lesson."
    
    def _start_analysis_lesson(self, user_id: str) -> str:
        """Start a word analysis lesson."""
        session = self._get_session(user_id)
        
        # Choose words with interesting structure
        interesting_words = []
        for word in self.woccon.dictionary.get("lexicon", []):
            analysis = self.woccon.analyze_word(word["woccon"])
            if analysis["roots"] or analysis["affixes"]:
                interesting_words.append(word)
        
        if not interesting_words:
            # Fallback to random words
            interesting_words = self.woccon.dictionary.get("lexicon", [])
        
        # Select up to 3 words
        selected_words = random.sample(interesting_words, min(3, len(interesting_words)))
        
        # Set up the lesson
        session["current_activity"] = {
            "type": "analysis_lesson",
            "words": selected_words,
            "current_index": 0
        }
        
        # Create introduction
        result = [f"🔍 Welcome to your Woccon Word Analysis Lesson 🔍"]
        result.append(f"I'll show you how to break down {len(selected_words)} Woccon words to understand their structure.")
        result.append("Let's get started with your first word!\n")
        
        # Show the first word analysis
        current_word = selected_words[0]
        result.append(self._analyze_word(current_word["woccon"]))
        result.append("\nType 'next' to continue to the next word, or 'quit' to end the lesson.")
        
        return "\n".join(result)
    
    def _continue_analysis_lesson(self, user_id: str, message_text: str) -> str:
        """Continue an analysis lesson."""
        session = self._get_session(user_id)
        activity = session["current_activity"]
        
        message_lower = message_text.lower().strip()
        
        # Check for exit command
        if message_lower in ["quit", "exit", "stop", "end"]:
            session["current_activity"] = None
            return "Analysis lesson ended. Type 'help' to see other commands."
        
        # Check for next word request
        if message_lower in ["next", "continue", "go on"]:
            # Move to next word
            activity["current_index"] += 1
            
            # Check if we've reached the end
            if activity["current_index"] >= len(activity["words"]):
                session["current_activity"] = None
                return "🎉 Congratulations! You've completed the analysis lesson. Type 'learn: analyze' to start another one, or 'help' to see other commands."
            
            # Show the next word analysis
            current_word = activity["words"][activity["current_index"]]
            
            result = ["Great! Here's the analysis of your next word:\n"]
            result.append(self._analyze_word(current_word["woccon"]))
            result.append("\nType 'next' to continue to the next word, or 'quit' to end the lesson.")
            
            return "\n".join(result)
        
        # Otherwise, just provide a hint
        return "Type 'next' to see the next word analysis, or 'quit' to end the lesson."
        
    def _retrieve_relevant_chunks(self, query: str) -> List[str]:
        """Retrieve relevant chunks from documentation based on query."""
        if not self.llm_available:
            return []
            
        # Simple keyword-based retrieval for now
        # In a real implementation, you'd use vector embeddings and similarity search
        query_terms = set(re.findall(r'\b[a-z]+\b', query.lower()))
        
        # Remove common stop words
        stop_words = {"the", "a", "an", "in", "on", "at", "to", "for", "with", "by", "about",
                     "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
                     "do", "does", "did", "will", "would", "should", "can", "could", "may",
                     "might", "must", "and", "or", "but", "if", "then", "else", "when",
                     "which", "who", "whom", "whose", "what", "where", "why", "how"}
        query_terms -= stop_words
        
        # Add some expanded terms for common topics
        expanded_terms = set()
        expansion_map = {
            "language": {"woccon", "language", "linguistic", "speak", "spoken", "speech"},
            "grammar": {"grammar", "syntax", "structure", "rule", "pattern"},
            "history": {"history", "historical", "past", "origin", "lawson", "1709"},
            "catawba": {"catawba", "related", "cousin", "connection", "similar", "relationship"}
        }
        
        for term in query_terms:
            for key, values in expansion_map.items():
                if term in values:
                    expanded_terms.update(values)
        
        query_terms.update(expanded_terms)
        
        # Score each chunk based on term frequency
        chunk_scores = []
        
        # Dictionary chunks
        for i, chunk in enumerate(self.dictionary_chunks):
            score = sum(1 for term in query_terms if term in chunk.lower())
            if score > 0:
                chunk_scores.append((score, "dictionary", i, chunk))
        
        # Rules chunks
        for i, chunk in enumerate(self.rules_chunks):
            score = sum(1 for term in query_terms if term in chunk.lower())
            if score > 0:
                chunk_scores.append((score, "rules", i, chunk))
        
        # General info chunks
        for i, chunk in enumerate(self.general_chunks):
            score = sum(1 for term in query_terms if term in chunk.lower())
            if score > 0:
                chunk_scores.append((score, "general", i, chunk))
        
        # Sort by score (descending)
        chunk_scores.sort(reverse=True)
        
        # Return top chunks (up to 10)
        relevant_chunks = [chunk for _, _, _, chunk in chunk_scores[:10]]
        
        # If nothing found, return some basic info
        if not relevant_chunks:
            if self.general_chunks:
                return self.general_chunks[:3]  # Return a few general info chunks
            return ["No specific information found in the Woccon documentation for this query."]
        
        return relevant_chunks
    
    def _process_with_rag(self, user_id: str, message_text: str) -> str:
        """Process queries using RAG to retrieve relevant information."""
        if not self.llm_available:
            return "I can only answer specific questions about documented Woccon words. Try 'lookup:', 'analyze:', or 'help'."
        
        # Retrieve relevant chunks based on query
        relevant_chunks = self._retrieve_relevant_chunks(message_text)
        
        # Create a prompt that includes retrieved chunks
        system_prompt = f"""You are a helpful assistant specializing ONLY in the documented Woccon language from John Lawson's 1709 list.

CRITICAL RULES:
- NEVER create, invent, or hypothesize new Woccon words
- NEVER claim to know pronunciations, grammar, or structures beyond what's documented
- ONLY use information from the documentation provided below
- If information is not in the documentation, clearly state it's not available
- Keep responses conversational but factual

DOCUMENTATION:
{'\n\n'.join(relevant_chunks)}

Respond to questions about the Woccon language in a helpful but cautious manner.
Always base your response ONLY on the documentation provided.
If asked about something not in the documentation, acknowledge the limitations of our knowledge about Woccon.
"""
        
        try:
            # Use the LLM with the RAG-enhanced system prompt
            response = ollama.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_text}
                ],
                options={
                    "temperature": 0.2  # Low temperature for factual responses
                }
            )
            
            llm_response = response["message"]["content"]
            
            # Verify the response doesn't contain made-up content
            verified_response = self._verify_rag_response(llm_response)
            
            return verified_response
            
        except Exception as e:
            logger.error(f"Error using LLM: {str(e)}")
            return "I encountered an error processing your question. Please try using specific commands like 'lookup:', 'analyze:', or 'help'."
    
    def _verify_rag_response(self, response: str) -> str:
        """Enhanced verification to prevent hallucination in RAG responses."""
        # Extract potential Woccon words
        potential_woccon_words = set(re.findall(r'\b([a-z][a-z-]+[a-z])\b', response.lower()))
        
        # Remove common English words and general terms
        common_words = {
            # Woccon-related terms
            "woccon", "lawson", "dictionary", "catawba", "siouan", 
            
            # Common nouns related to language
            "language", "word", "words", "vocabulary", "pronunciation", "grammar",
            "list", "sentence", "sentences", "phrase", "phrases", "meaning", "lexicon",
            "terms", "symbols", "speech", "structure", "structures", "patterns",
            "analysis", "breakdown", "affixes", "roots", "suffixes", "prefixes",
            "nouns", "verbs", "adjectives", "adverbs", "english", "documentation",
            "sources", "evidence", "records", "entries", "meaning", "meanings",
            "sound", "sounds", "pronunciation", "pronunciations", "syllable", "syllables",
            
            # Words related to history, documentation
            "historical", "document", "documented", "undocumented", "linguist", "linguistics",
            "colonial", "indigenous", "native", "american", "carolina", "north", "south",
            "tribal", "tribe", "speaker", "speakers", "century", "knowledge", "available",
            "information", "explorer", "record", "recorded", "preserved", "preservation",
            "collection", "collected", "expedition", "anthropologist", "anthropology",
            "historian", "limited", "extinct", "revival", "revitalization",
            
            # Common verbs
            "have", "has", "had", "been", "being", "would", "could", "should", "might",
            "must", "will", "can", "know", "known", "understand", "understood", "learn",
            "learned", "speak", "spoke", "spoken", "communicate", "said", "wrote", "written",
            "documented", "recorded", "preserved", "means", "meant", "note", "noted",
            "include", "included", "indicate", "indicated", "suggest", "suggested",
            "provide", "provided", "show", "shown", "refer", "referred", "demonstrates",
            "revealed", "contains", "believe", "mentions", "appears", "reveals", "lacks",
            
            # Common adjectives and adverbs
            "common", "commonly", "specific", "specifically", "certain", "certainly",
            "particular", "particularly", "various", "several", "different", "similar",
            "complete", "completely", "partial", "partially", "extensive", "limited",
            "original", "originally", "modern", "modernly", "contemporary", "ancient",
            "historically", "linguistically", "unfortunately", "fortunately", "likely",
            "unlikely", "possible", "impossible", "probable", "improbable", "accurate",
            "inaccurate", "exact", "exactly", "approximate", "approximately", "precise",
            "precisely", "vague", "vaguely", "definite", "definitely", "interesting",
            "important", "significant", "unique", "rare", "essential",
            
            # Common prepositions, articles, conjunctions
            "about", "above", "across", "after", "against", "along", "among", "around",
            "before", "behind", "below", "beneath", "beside", "between", "beyond",
            "during", "except", "inside", "outside", "through", "toward", "under", "within",
            "without", "with", "from", "until", "upon", "onto", "into", "regarding",
            "concerning", "despite", "besides", "like", "unlike", "using", "that", "which",
            "when", "where", "while", "because", "since", "although", "though", "whether",
            "unless", "while", "than", "even", "only", "just", "still", "rather", "quite",
            "somewhat", "very", "too", "much", "more", "most", "less", "least", "enough",
            "such", "both", "either", "neither", "each", "every", "some", "any", "many",
            "few", "little", "other", "another", "same", "own", "these", "those", "this",
            "them", "their", "there", "here", "your", "mine", "ours", "yours", "theirs",
            "and", "but", "for", "nor", "yet", "not", "are", "the", "also"
        }
        
        # Also add numbers and basic words
        numbers = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                   "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                   "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "hundred", "thousand"}
        common_words.update(numbers)
        
        # Remove all these common words from our potential Woccon words
        potential_woccon_words -= common_words
        
        # Check which words aren't in our documented list
        undocumented_words = potential_woccon_words - self.documented_words
        
        # Look for patterns that suggest the LLM is making up Woccon content
        woccon_invention_patterns = [
            r"woccon word for .* is ['\"]*([a-z-]+)['\"]*",
            r"['\"]*([a-z-]+)['\"]*( means| translates to) .* in (english|translation)",
            r"pronounced as ['\"]*([^'\"]+)['\"]*",
            r"greeting in woccon is ['\"]*([a-z-]+)['\"]*",
            r"woccon numbers include ['\"]*([a-z-]+)['\"]*",
            r"count in woccon: ['\"]*([a-z-]+)['\"]*"
        ]
        
        # Check if any of our patterns match, and if the word isn't in our documented list
        hallucinated_words = set()
        for pattern in woccon_invention_patterns:
            matches = re.finditer(pattern, response.lower())
            for match in matches:
                word = match.group(1).strip()
                if word not in self.documented_words:
                    hallucinated_words.add(word)
        
        # Grammar hallucination patterns that would suggest the LLM is making up grammar rules
        grammar_patterns = [
            r"woccon (uses|has|had|employs|follows) (a|an|the) .* (system|structure|pattern|rule|order)",
            r"(suffix|prefix|infix) ['\"]*([a-z-]+)['\"]*( means| indicates| shows| expresses)",
            r"woccon verbs (are|were) (conjugated|formed|structured|made|created) by",
            r"woccon (sentences|phrases) (follow|are structured|use|have) (a|an|the) .* (order|pattern|structure)"
        ]
        
        contains_grammar_invention = any(re.search(pattern, response.lower()) for pattern in grammar_patterns)
        
        # If we find clearly hallucinated content, replace with a warning
        if hallucinated_words or contains_grammar_invention:
            logger.warning(f"Detected clear hallucination in RAG response. Hallucinated words: {hallucinated_words}")
            return """I need to clarify that I can only provide information about the approximately 140 Woccon words and limited grammatical features documented in historical sources.

I cannot generate new Woccon words, pronunciations, or grammatical rules beyond this documentation.

If you'd like to explore the documented Woccon vocabulary and features, please try:
- 'lookup: [word]' to look up documented words
- 'analyze: [word]' to analyze word structure 
- 'category: [category]' to browse words by category
- 'learn: vocabulary' to start an interactive lesson

I'm happy to help you explore what we do know about this fascinating language!"""
        
        # If we only find some potentially undocumented words but no clear invention patterns, proceed with caution
        if undocumented_words:
            # If many undocumented words (5+) and they look like they could be Woccon inventions
            # (3+ characters, not common English words), then warn
            suspicious_words = {word for word in undocumented_words 
                              if len(word) >= 3 
                              and not word.endswith('s') 
                              and not word.endswith('ed') 
                              and not word.endswith('ing')}
            
            if len(suspicious_words) >= 3:
                logger.warning(f"Found multiple suspicious words: {suspicious_words}")
                return """I need to clarify that I can only provide information about the approximately 140 Woccon words documented in historical sources.

Some of my response may have contained speculative information beyond what is documented. Let me try again with a more factual approach.

Please use commands like 'lookup:', 'analyze:', or 'category:' to explore specific documented Woccon vocabulary."""
        
        # If no clear hallucination, return the original response
        return response
    
    def _process_with_llm(self, user_id: str, message_text: str) -> str:
        """Legacy method for simple LLM processing with strict guardrails."""
        # For backward compatibility - now just calls the RAG method
        return self._process_with_rag(user_id, message_text)

class MessengerBot:
    """Facebook Messenger bot for the Woccon language assistant."""
    
    def __init__(self, page_access_token: str, verify_token: str = "woccon_bot_verify_token"):
        """Initialize the Messenger bot."""
        self.page_access_token = page_access_token
        self.verify_token = verify_token
        self.assistant = WocconAssistant()
        logger.info("Messenger bot initialized.")
    
    def verify_webhook(self, mode: str, token: str, challenge: str) -> str:
        """Verify webhook for Facebook integration."""
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verified.")
            return challenge
        else:
            logger.warning("Webhook verification failed.")
            return "Verification token mismatch", 403
    
    def process_webhook(self, data: Dict) -> bool:
        """Process incoming webhook data from Messenger."""
        if data.get("object") != "page":
            logger.warning("Received non-page object.")
            return False
        
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                # Get the sender ID
                sender_id = messaging_event.get("sender", {}).get("id")
                
                # Check if this is a message event
                if messaging_event.get("message"):
                    message_text = messaging_event.get("message", {}).get("text")
                    
                    if message_text:
                        logger.info(f"Received message from {sender_id}: {message_text}")
                        
                        # Send typing indicator
                        self.send_typing_indicator(sender_id)
                        
                        # Process the message
                        response = self.assistant.handle_message(sender_id, message_text)
                        
                        # Send the response
                        self.send_message(sender_id, response)
        
        return True
    
    def send_message(self, recipient_id: str, message_text: str):
        """Send a message to the specified recipient via Messenger API."""
        # Split long messages to respect Messenger's limits
        if len(message_text) > 2000:
            chunks = self._split_message(message_text)
            for chunk in chunks:
                self._send_message_request(recipient_id, chunk)
        else:
            self._send_message_request(recipient_id, message_text)
    
    def _send_message_request(self, recipient_id: str, message_text: str):
        """Send actual message request to Messenger API."""
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
        """Send a typing indicator to the user."""
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
        """Split a long message into chunks respecting Messenger's limits."""
        # Simple implementation - split on newlines if possible
        if len(message) <= max_length:
            return [message]
            
        chunks = []
        paragraphs = message.split("\n\n")
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) + 2 > max_length:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # If the paragraph itself is too long, split it
                if len(paragraph) > max_length:
                    words = paragraph.split(" ")
                    for word in words:
                        if len(current_chunk) + len(word) + 1 > max_length:
                            chunks.append(current_chunk)
                            current_chunk = word + " "
                        else:
                            current_chunk += word + " "
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
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
    """Verify webhook for Facebook integration."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    result = messenger_bot.verify_webhook(mode, token, challenge)
    
    if isinstance(result, tuple):
        return result
    
    return result

@app.route('/webhook', methods=['POST'])
def webhook():
    """Process incoming messages from Messenger."""
    data = request.get_json()
    
    messenger_bot.process_webhook(data)
    
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    """Simple index page to confirm the server is running."""
    return "Woccon Language Assistant is running!"

def run_server():
    """Run the Flask server."""
    app.run(host='0.0.0.0', port=5000)

# CLI test interface
def run_cli():
    """Run a CLI interface for testing."""
    assistant = WocconAssistant()
    
    print("\n🗣️ Woccon Language Assistant CLI 🗣️")
    print("Type 'help' for available commands or 'quit' to exit")
    
    while True:
        try:
            user_input = input("\nwoccon> ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Exiting Woccon CLI. Goodbye!")
                break
                
            response = assistant.handle_message("cli_user", user_input)
            print(f"\n{response}")
            
        except KeyboardInterrupt:
            print("\nExiting Woccon CLI. Goodbye!")
            break
            
        except Exception as e:
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Woccon Language Assistant")
    parser.add_argument("--cli", action="store_true", help="Start the CLI interface")
    parser.add_argument("--server", action="store_true", help="Start the Messenger webhook server")
    parser.add_argument("--model", type=str, default="llama3.2:3b", help="Specify LLM model to use")
    args = parser.parse_args()
    
    if args.cli:
        # Start CLI interface
        run_cli()
    elif args.server:
        # Start Messenger webhook server
        print("Starting Messenger webhook server...")
        run_server()
    else:
        # Show help by default
        parser.print_help()