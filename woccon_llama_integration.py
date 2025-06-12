import os, json, re, logging, random
from collections import deque
from typing import Dict, List, Tuple, Optional, Any
import ollama  # your local Llama server client
from main import WocconT5
import requests

# Import the improved lesson managers
from lesson_manager import LessonManager
from grammar_lesson_manager import GrammarLessonManager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_assistant")


class WocconAssistant:
    """RAG-powered Woccon assistant. Lessons start only when users explicitly request them."""

    def __init__(self,
                 dict_path="woccon_language/dictionary.json",
                 rules_path="woccon_language/rules.json",
                 model="llama3:8b",
                 ctx_turns=6):
        # Core data & model
        self.woccon = WocconT5()
        log.info("About to load JSON; dict_path=%r   rules_path=%r", dict_path, rules_path)

        self.dictionary = self._load_json(dict_path)
        self.rules = self._load_json(rules_path)
        log.info("Rules keys: %s", list(self.rules.keys()))

        self.model = model or os.getenv("OLLAMA_MODEL", "llama3:8b")
        self.ctx_turns = ctx_turns

        # Set the Ollama API URL dynamically
        self.url = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat")
        log.info(f"Using Ollama URL: {self.url}")

        # Prepare retrieval corpus
        self.documented_words = {
            e["woccon"].lower() for e in self.dictionary.get("lexicon", [])
        }
        self.chunks = [
            f"Woccon: {e['woccon']} | English: {e['english']} | POS: {e['pos']}"
            for e in self.dictionary.get("lexicon", [])
        ]
        
        # Add grammar rules and patterns to retrieval corpus from rules.json
        if "morphology" in self.rules and "affixes" in self.rules["morphology"]:
            # Add suffixes
            for suffix in self.rules["morphology"]["affixes"].get("suffixes", []):
                self.chunks.append(
                    f"Grammar: Suffix {suffix['form']} | Function: {suffix['function']} | "
                    f"Examples: {', '.join(suffix.get('examples', []))}"
                )
            # Add prefixes
            for prefix in self.rules["morphology"]["affixes"].get("prefixes", []):
                self.chunks.append(
                    f"Grammar: Prefix {prefix['form']} | Function: {prefix['function']} | "
                    f"Examples: {', '.join(prefix.get('examples', []))}"
                )
        
        # Add roots information
        if "morphology" in self.rules and "common_roots" in self.rules["morphology"]:
            for root in self.rules["morphology"]["common_roots"]:
                derivatives_text = ", ".join([f"{d['form']} ({d['gloss']})" for d in root.get("derivatives", [])])
                self.chunks.append(
                    f"Grammar: Root {root['root']} | Meaning: {root['meaning']} | "
                    f"Derivatives: {derivatives_text}"
                )
        
        # Add inflectional morphology
        if "morphology" in self.rules and "inflectional_morphology" in self.rules["morphology"]:
            modes = self.rules["morphology"]["inflectional_morphology"].get("modes", [])
            for mode in modes:
                examples_text = ", ".join([f"{ex['form']} ({ex['gloss']})" for ex in mode.get("examples", [])])
                self.chunks.append(
                    f"Grammar: Mode {mode['name']} | Marker: {mode['marker']} | "
                    f"Description: {mode['description']} | Examples: {examples_text}"
                )
        
        # Add phonological processes
        if "phonology" in self.rules and "phonological_processes" in self.rules["phonology"]:
            for process in self.rules["phonology"]["phonological_processes"]:
                examples_text = ", ".join([f"Woccon: {ex['Woccon']}, Catawba: {ex['Catawba']} ({ex['gloss']})" for ex in process.get("examples", [])])
                self.chunks.append(
                    f"Grammar: Phonological process {process['process']} | "
                    f"Description: {process['description']} | Examples: {examples_text}"
                )

        # in __init__, right after you build self.chunks:
        log.info("First 5 chunks: %s", self.chunks[:5])


        log.info("RAG ready: %d chunks (%d documented words)",
                 len(self.chunks),
                 len(self.documented_words))

        # Session state per user
        self.sessions: Dict[str, Dict] = {}
    
    # also add this helper to test retrieval
    def debug_retrieve(self, query):
        results = self._retrieve(query, k=5)
        log.info("Retrieve(%r) → %s", query, results)
        return results


    def send_message(self, prompt: str):
        """Send a message to the Ollama API."""
        try:
            response = requests.post(
                self.url,
                json={"model": self.model, "prompt": prompt}
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "No response")
        except Exception as e:
            log.error(f"Error connecting to Ollama: {e}")
            return "Error: Unable to connect to the Ollama server."

    def reply(self, user_id: str, text: str) -> str:
        """Process user input and respond. Lessons only start when explicitly requested."""
        # Initialize or get session
        session = self.sessions.setdefault(user_id, {
            "history": deque(maxlen=self.ctx_turns * 2 + 2),
            "lesson": None,
            "last_lesson_state": None,  # Store state of last incomplete lesson
            "last_interaction": None,   # Store last user input
            "pending_action": None,     # Store a pending action choice if needed
            "context": {},              # Store context between interactions
            "direct_lesson_request": False,  # Track if the current query is a direct lesson request
        })

        # Store last interaction
        session["last_interaction"] = text
        lower = text.lower().strip()
        
        # Reset direct lesson request flag
        session["direct_lesson_request"] = False
        
        # 1️⃣ Check for direct lesson requests first
        direct_lesson_request = self._check_direct_lesson_request(lower)
        if direct_lesson_request:
            session["direct_lesson_request"] = True
            lesson_type = direct_lesson_request.get("type", "unspecified")
            
            if lesson_type != "unspecified":
                # Start the requested lesson type directly
                if lesson_type == "vocab":
                    words = random.sample(self.dictionary["lexicon"], 3)
                    session["lesson"] = LessonManager(words, parent=self, mode="vocab")
                    return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()
                else:  # grammar lesson
                    items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
                    session["lesson"] = GrammarLessonManager(items, parent=self)
                    return "📚 Starting a grammar lesson!\n\n" + session["lesson"].prompt()
            else:
                # Ask which type they want
                session["pending_action"] = "choose_lesson_type"
                
                return (
                    "📚 I'd be happy to start a lesson! What type would you like?\n\n"
                    "• Say 'vocabulary' to learn Woccon words\n"
                    "• Say 'grammar' to learn grammar rules and patterns"
                )
        
        # 2️⃣ Handle pending actions (only for lesson type selection)
        if session["pending_action"] == "choose_lesson_type":
            # Check if they specified a lesson type
            vocab_patterns = ["vocab", "vocabulary", "words", "terms", "dictionary"]
            grammar_patterns = ["grammar", "rules", "structure", "patterns"]
            
            if any(pattern in lower for pattern in vocab_patterns):
                # Start vocabulary lesson
                words = random.sample(self.dictionary["lexicon"], 3)
                session["lesson"] = LessonManager(words, parent=self, mode="vocab")
                session["pending_action"] = None
                return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()
            elif any(pattern in lower for pattern in grammar_patterns):
                # Start grammar lesson
                items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
                session["lesson"] = GrammarLessonManager(items, parent=self)
                session["pending_action"] = None
                return "📚 Starting a grammar lesson!\n\n" + session["lesson"].prompt()
            else:
                # Default to vocab if they didn't specify clearly
                words = random.sample(self.dictionary["lexicon"], 3)
                session["lesson"] = LessonManager(words, parent=self, mode="vocab")
                session["pending_action"] = None
                return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()

        # 3️⃣ If a lesson is in progress, delegate straight to it
        if session["lesson"] is not None:
            resp, done = session["lesson"].handle(text)
            
            if done:
                # Save lesson state before clearing if it wasn't completed
                if hasattr(session["lesson"], "i") and hasattr(session["lesson"], "words") and \
                session["lesson"].i < len(session["lesson"].words):
                    session["last_lesson_state"] = session["lesson"].get_progress()
                session["lesson"] = None
            
            return resp

        # 4️⃣ Handle continuation of previous lessons
        if session["last_lesson_state"] and self._is_continue_request(lower):
            lesson_state = session["last_lesson_state"]
            
            if lesson_state.get("type") == "vocab":
                # Resume vocabulary lesson
                words = lesson_state.get("words", [])
                if words:
                    lesson = LessonManager(words, parent=self, mode="vocab")
                    # Restore state
                    lesson.i = lesson_state.get("index", 0)
                    lesson.score = lesson_state.get("score", 0)
                    lesson.streak = lesson_state.get("streak", 0)
                    lesson.stage = lesson_state.get("stage", "prompt")
                    lesson.mode = lesson_state.get("mode", "eng_to_woc")
                    
                    session["lesson"] = lesson
                    session["last_lesson_state"] = None  # Clear the saved state
                    
                    return f"📚 Resuming your vocabulary lesson from where you left off!\n\n{lesson.prompt()}"
            
            elif lesson_state.get("type") == "grammar":
                # Grammar lessons are harder to resume exactly, so we'll just start a new one
                items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
                lesson = GrammarLessonManager(items, parent=self)
                
                session["lesson"] = lesson
                session["last_lesson_state"] = None  # Clear the saved state
                
                return f"📚 Starting a new grammar lesson!\n\n{lesson.prompt()}"

        # 5️⃣ Additional check for explicit lesson requests that might not have been caught
        # This is the added code to handle direct requests like "I'd like a vocab lesson please!"
        if re.search(r"\b(like|want|start|begin|do|give me|teach me)\b.+\b(vocab|vocabulary|lesson)\b", lower):
            words = random.sample(self.dictionary["lexicon"], 3)
            session["lesson"] = LessonManager(words, parent=self, mode="vocab")
            return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()
        
        if re.search(r"\b(like|want|start|begin|do|give me|teach me)\b.+\b(grammar|rules|lesson)\b", lower):
            items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
            session["lesson"] = GrammarLessonManager(items, parent=self)
            return "📚 Starting a grammar lesson!\n\n" + session["lesson"].prompt()

        # 6️⃣ Process the query using RAG-first approach
        retrieved, has_strong_match = self._retrieve(text)
        log.info(f"[RAG] Query: '{text}' → Retrieved {len(retrieved)} documents, strong_match: {has_strong_match}")
        
        # Check if this is a specific word/translation request
        is_word_request = self._is_word_or_translation_request(text)
        
        if is_word_request and not has_strong_match:
            # For specific word requests without strong matches, generate contextual response
            answer = self._generate_contextual_not_found_response(text, session["history"])
        elif not retrieved:
            # No documents found at all, but still generate contextual response
            answer = self._generate_contextual_general_response(text, session["history"])
        else:
            # We have some documents, proceed with LLM generation
            messages = self._build_prompt(text, retrieved, session["history"])
            raw = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.3}
            )["message"]["content"]
            answer = self._strict_verify(raw, has_strong_match, is_word_request)
        
        # Update history
        session["history"].append({"role": "user", "content": text})
        session["history"].append({"role": "assistant", "content": answer})
        
        # 7️⃣ No automatic lesson offers - lessons only start when explicitly requested
        
        return answer
    
    
    def _check_direct_lesson_request(self, text: str) -> Optional[Dict]:
        """
        Improved detection of direct lesson requests with clearer differentiation between
        grammar and vocabulary lessons. Now captures more natural language patterns.
        """
        text = text.lower().strip()
        
        # Very explicit grammar lesson requests - high confidence
        grammar_patterns = [
            r"^\s*grammar lesson\s*\??$",  # Just "grammar lesson" or "grammar lesson?"
            r"\b(start|begin|do|give me) (?:a )?grammar lesson\b",
            r"\bcan you (?:do|teach|give) (?:a )?grammar lesson\b",
            r"^\s*teach me grammar\s*$",  # Exact match for "teach me grammar"
            r"^\s*grammar\s*\?$",  # Just "grammar?"
        ]
        
        if any(re.search(pattern, text) for pattern in grammar_patterns):
            return {"type": "grammar", "confidence": "high"}
        
        # Very explicit vocabulary lesson requests - high confidence
        vocab_patterns = [
            r"^\s*vocab(?:ulary)? lesson\s*\??$",  # Just "vocab lesson" or "vocabulary lesson?"
            r"\b(start|begin|do|give me) (?:a )?vocab(?:ulary) lesson\b",
            r"\bcan you (?:do|teach|give) (?:a )?vocab(?:ulary) lesson\b",
            r"^\s*teach me vocab(?:ulary)\s*$",  # Exact match for "teach me vocabulary"
            r"^\s*words\s*\?$",  # Just "words?"
        ]
        
        if any(re.search(pattern, text) for pattern in vocab_patterns):
            return {"type": "vocab", "confidence": "high"}
        
        # Less explicit but still pretty clear grammar requests
        grammar_medium_patterns = [
            r"\b(?:teach|show|learn) (?:me |us )?(?:about )?grammar\b",
            r"\bgrammar (?:help|practice|exercises|tutorial)\b",
            r"\b(?:i want to|let's|i'd like to) learn grammar\b",
        ]
        
        if any(re.search(pattern, text) for pattern in grammar_medium_patterns):
            return {"type": "grammar", "confidence": "medium"}
        
        # Less explicit but still pretty clear vocabulary requests
        vocab_medium_patterns = [
            r"\b(?:teach|show|learn) (?:me |us )?(?:about )?vocab(?:ulary)?\b",
            r"\bvocab(?:ulary) (?:help|practice|exercises|tutorial)\b",
            r"\b(?:i want to|let's|i'd like to) learn vocab(?:ulary)\b",
            r"\blearn (?:some |a few )?words\b",
            # Added more natural language patterns
            r"\bcould you (?:teach|help with|show me) (?:some )?vocab(?:ulary)?\b",
            r"\bi'?d like (?:to learn|a|some) vocab(?:ulary)?\b",
            r"\bi'?d like (?:a )?vocab(?:ulary)? lesson\b",
            r"\bwant (?:to learn|a|some) vocab(?:ulary)?\b",
            r"\b(?:can|could) (?:i|we) (?:have|do|get) (?:a )?vocab(?:ulary)?\b",
            r"\b(?:please|pls) (?:teach|show) (?:me|us) (?:some )?vocab(?:ulary)?\b",
        ]
        
        if any(re.search(pattern, text) for pattern in vocab_medium_patterns):
            return {"type": "vocab", "confidence": "medium"}
        
        # Very general lesson requests
        if (re.search(r"\b(give|start|begin|teach) (?:a |me )?lesson\b", text) or 
            re.search(r"\bcan you (?:do|teach|give) (?:a )?lesson\b", text) or
            re.search(r"^\s*lesson\s*\??$", text) or  # Just "lesson" or "lesson?"
            re.search(r"\bi'?d like (?:a |to have a )?lesson\b", text)):  # "I'd like a lesson"
            return {"type": "unspecified", "confidence": "medium"}
                
        return None
        
    
    def _is_continue_request(self, text: str) -> bool:
        """Check if user wants to continue a previous lesson."""
        continue_patterns = [
            r"\b(continue|resume|go back to|pickup|pick up|get back to) (?:the |my |our )?(lesson|learning|studies|practice)\b",
            r"\bwhere (?:was i|were we|did we leave off)\b",
            r"\bcontinue where (?:i|we) left off\b",
            r"\bpick up from where (?:i|we) (?:were|left off)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in continue_patterns)
    
    def _is_word_or_translation_request(self, text: str) -> bool:
        """Check if user is asking for a specific word or translation."""
        text = text.lower().strip()
        
        # Direct word/translation patterns
        word_patterns = [
            r"\bwhat.+(woccon|word|means?|translation)\b",
            r"\bhow.+(say|translate|word)\b", 
            r"\b(translate|word for|woccon for|english for)\b",
            r"\bwhat.+(called|named)\b",
            r"\bmeans?\s*['\"]?\w+['\"]?\s*\??\s*$",  # "what does X mean?"
            r"\b['\"]?\w+['\"]?\s+(means?|translation|woccon|english)\b",
            r"^(hello|hi|goodbye|yes|no|please|thank you|water|fire|food|house)[\?\s]*$",  # Common single words
            r"\bis there.+(word|translation)\b",
            r"\bdo you know.+(word|translation)\b",
            r"\b(what|how) about\s+\w+\??$",  # "what about X?" or "how about X?"
            r"^\s*\w+\s*\??$"  # Single word queries like "fire?" or "grapes"
        ]
        
        return any(re.search(pattern, text) for pattern in word_patterns)
    
    def _generate_contextual_not_found_response(self, query: str, history: deque) -> str:
        """Generate contextual response using LLM when specific word/translation not found."""
        # Build a prompt that instructs the LLM to respond contextually about missing words
        system_prompt = (
            "You are a helpful assistant for the documented Woccon language. "
            "The user asked about a word that is NOT in the documented vocabulary. "
            "CRITICAL RULES - NEVER use these words or phrases:\n"
            "- might, could, possibly, likely, probably, perhaps, maybe\n"
            "- it's possible, may be, would be, could be\n"
            "- native to, region where, geographic, cultural reasons\n"
            "- suggests, indicates, implies, connection, related\n\n"
            "ONLY say: The word is not in John Lawson's 1709 word list. Offer to help with documented words.\n"
            "Example good response: 'Unfortunately, [word] is not in John Lawson's 1709 word list of 143 Woccon words. I can help you explore what IS documented instead.'\n"
            "Be helpful but stick to this simple fact-based approach."
        )
        
        # Include recent history for context
        tail = list(history)[-self.ctx_turns * 2:]
        messages = (
            [{"role": "system", "content": system_prompt}]
            + tail
            + [{"role": "user", "content": query}]
        )
        
        try:
            raw = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.7}  # Slightly higher temperature for more natural responses
            )["message"]["content"]
            # Apply strict verification to catch any speculation
            verified = self._strict_verify(raw, False, True)
            return verified
        except Exception as e:
            log.error(f"Error generating contextual response: {e}")
            # Fallback to static response
            return self._generate_not_found_response(query)
    
    def _generate_contextual_general_response(self, query: str, history: deque) -> str:
        """Generate contextual response using LLM when no documents found for general queries."""
        system_prompt = (
            "You are a helpful assistant for the documented Woccon language. "
            "The user asked a question that doesn't match any specific documented content. "
            "CRITICAL: Do NOT speculate, guess, or make up information. Stick to documented facts only. "
            "Respond conversationally to their query, acknowledging what they asked about. "
            "Explain that you have access to John Lawson's 1709 word list of 143 Woccon words and related linguistic information. "
            "Offer specific ways you can help them learn about what IS actually documented in the Woccon language. "
            "Be helpful and contextual but never speculative."
        )
        
        # Include recent history for context
        tail = list(history)[-self.ctx_turns * 2:]
        messages = (
            [{"role": "system", "content": system_prompt}]
            + tail
            + [{"role": "user", "content": query}]
        )
        
        try:
            raw = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.7}
            )["message"]["content"]
            # Apply strict verification to catch any speculation
            verified = self._strict_verify(raw, False, False)
            return verified
        except Exception as e:
            log.error(f"Error generating contextual response: {e}")
            # Fallback to static response
            return self._generate_general_help_response(query)
    
    def _generate_not_found_response(self, query: str) -> str:
        """Generate response when specific word/translation not found in RAG data."""
        return (
            f"I don't have information about that specific word or translation in the documented Woccon vocabulary. "
            f"The Woccon language documentation contains 143 attested words from John Lawson's 1709 word list. "
            f"If you're looking for a specific word, I can help you explore what's available in the documented vocabulary, "
            f"or you could ask about Woccon grammar patterns, language history, or cultural context instead."
        )
    
    def _generate_general_help_response(self, query: str) -> str:
        """Generate response when no relevant documents found for general queries."""
        return (
            f"I can help you learn about the documented Woccon language! "
            f"I have access to 143 attested Woccon words, grammar patterns, and cultural information. "
            f"You can ask me about specific Woccon words, language structure, history, or request vocabulary lessons. "
            f"What would you like to learn about?"
        )
    
    def _is_help_request(self, text: str) -> bool:
        """Check if user is asking for help with commands."""
        help_patterns = [
            r"\b(help|commands|what can you do|how do i|features|capabilities)\b",
            r"what (?:can you|do you) do",
            r"(?:show|list|tell me) (?:the )?commands",
        ]
        
        return any(re.search(pattern, text) for pattern in help_patterns)
    
    def _matches_any_pattern(self, text: str, patterns: List[str]) -> bool:
        """Helper method to check if text matches any of the given patterns."""
        return any(re.search(pattern, text) for pattern in patterns)

    def _retrieve(self, query: str, k: int = 12) -> Tuple[List[str], bool]:
        """
        Retrieval function for RAG. Returns (documents, has_strong_match).
        """
        tokens = set(re.findall(r"[a-z]+", query.lower()))
        scored = [(sum(t in chunk.lower() for t in tokens), chunk)
                  for chunk in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Get documents with any score > 0
        relevant_docs = [chunk for score, chunk in scored[:k] if score > 0]
        
        # Check if we have a strong match (score >= 2 or exact word match)
        has_strong_match = False
        if scored and scored[0][0] >= 2:
            has_strong_match = True
        
        # If no strong match from scoring, check for exact English word matches
        if not has_strong_match:
            for token in tokens:
                # Check against documented Woccon words
                if any(token in doc_word.lower() for doc_word in self.documented_words):
                    has_strong_match = True
                    break
                # Check against English meanings in the retrieved docs
                for doc in relevant_docs:
                    if f"english: {token}" in doc.lower():
                        has_strong_match = True
                        break
                if has_strong_match:
                    break
        
        return relevant_docs, has_strong_match

    def _build_prompt(self, query: str, docs: List[str], history: deque) -> List[Dict]:
        """
        Build prompt for the LLM with strict instructions to only use documented information.
        """
        # system section with retrieved docs
        if docs:
            doc_text = "\n".join(docs)
            system = (
                "You are a helpful assistant for the documented Woccon language. IMPORTANT RULES:\n"
                "1. ONLY use information from the provided documents below\n"
                "2. NEVER invent, guess, or speculate about Woccon words that aren't in the documents\n"
                "3. NEVER make connections between words unless explicitly shown in the documents\n"
                "4. NEVER speculate about geographic, cultural, or linguistic reasons for missing words\n"
                "5. If asked about words not in the documents, simply state they aren't documented\n"
                "6. When discussing grammar, only reference patterns explicitly visible in the documented examples\n"
                "7. Do NOT use words like 'might', 'could be', 'possibly', 'likely', 'probably' when discussing Woccon\n"
                "8. Be helpful and educational, but stay strictly within documented facts\n\n"
                "DOCUMENTED WOCCON INFORMATION:\n"
                f"{doc_text}\n\n"
                "Answer based ONLY on the information above. If something isn't documented, say so clearly without speculation."
            )
        else:
            system = (
                "You are a helpful assistant for the Woccon language. IMPORTANT:\n"
                "- You have access to 143 documented Woccon words from John Lawson's 1709 word list\n"
                "- NEVER invent, guess, or speculate about words that aren't documented\n"
                "- NEVER make up connections between words or linguistic explanations\n"
                "- Do NOT use words like 'might', 'could be', 'possibly', 'likely', 'probably'\n"
                "- If users ask about undocumented words, simply explain they aren't in the documented list\n"
                "- Focus on what IS actually documented: vocabulary, cultural context, and language history\n"
                "- Encourage exploration of the actual documented vocabulary without speculation"
            )

        # tail of history + new user query
        tail = list(history)[-self.ctx_turns * 2:]
        return (
            [{"role": "system", "content": system}]
            + tail
            + [{"role": "user", "content": query}]
        )

    def _strict_verify(self, text: str, has_strong_match: bool, is_word_request: bool) -> str:
        """
        Strict verification that prevents hallucination of Woccon words and language content.
        """
        # Skip verification for certain safe response types
        if any(marker in text.lower() for marker in [
            "i don't know", 
            "not in the dictionary",
            "not enough information",
            "can't find",
            "no information",
            "not documented",
            "unfortunately",
            "isn't in",
            "word list",
            "lawson's"
        ]):
            return text
            
        # Look for statements that claim specific words are Woccon
        # Be more specific to avoid false positives like "the word X"
        woccon_claims = re.finditer(
            r"(?:woccon (?:word|term) (?:for .+ )?is ['\"]([a-z\-]+)['\"]|woccon is ['\"]([a-z\-]+)['\"]|in woccon,? ['\"]([a-z\-]+)['\"]|the woccon (?:word )?['\"]([a-z\-]+)['\"])", 
            text, re.I
        )
        
        for match in woccon_claims:
            # Get the first non-None group
            candidate = next((g for g in match.groups() if g is not None), "").lower()
            
            # Skip very short words that might be particles or common words
            if len(candidate) <= 2:
                continue
                
            # Skip common English words that aren't language-specific
            common_english = {
                "the", "and", "for", "is", "of", "to", "in", "a", "an", "this", "that",
                "have", "has", "had", "with", "from", "they", "them", "their", "there",
                "where", "when", "what", "how", "why", "who", "can", "could", "would",
                "should", "will", "are", "was", "were", "been", "being", "do", "does", "did"
            }
            if candidate in common_english:
                continue
                
            # Check if word is in documented vocabulary
            if candidate not in self.documented_words:
                # Check for very close matches (within 1-2 characters)
                close_match = False
                for documented_word in self.documented_words:
                    # Allow for slight spelling variations
                    if (abs(len(candidate) - len(documented_word)) <= 2 and 
                        (candidate in documented_word or documented_word in candidate)):
                        close_match = True
                        break
                        
                if not close_match:
                    return (
                        f"I don't have information about the word '{candidate}' in the documented Woccon vocabulary. "
                        f"The documented Woccon language contains 143 attested words from John Lawson's 1709 word list. "
                        f"I can help you explore what words are actually documented, or provide information about "
                        f"Woccon grammar patterns and cultural context instead."
                    )
        
        # Check for speculation words and phrases
        speculation_patterns = [
            r"\b(might|could|possibly|likely|probably|perhaps|maybe|it's possible|may have|would have)\b",
            r"\b(if we were to|if they had|it's unlikely|it's likely)\b",
            r"\b(this suggests|this indicates|this implies)\b",
            r"\b(native to|not native to|region where.*lived)\b",
            r"\b(phonological process|nasalization.*corresponds)\b"
        ]
        
        speculation_found = False
        for pattern in speculation_patterns:
            if re.search(pattern, text, re.I):
                speculation_found = True
                break
        
        if speculation_found:
            return (
                f"I don't have documented information about that specific word in John Lawson's 1709 Woccon word list. "
                f"The documented vocabulary contains 143 attested words. "
                f"I can help you explore what words are actually documented, or provide information about "
                f"documented Woccon grammar patterns and cultural context instead."
            )
        
        # Check for claims about grammar rules or language features not in the rules
        grammar_claims = re.finditer(
            r"woccon (has|uses|follows|contains|includes).*?(suffix|prefix|rule|pattern|grammar)",
            text, re.I
        )
        
        for match in grammar_claims:
            # For grammar claims, we should be cautious but less strict since morphological 
            # analysis might legitimately identify patterns
            if not has_strong_match:
                warning = (
                    "\n\n⚠️ Note: This analysis is based on limited documented material. "
                    "Some grammatical patterns may be reconstructed or speculative."
                )
                if warning not in text:
                    text += warning
        
        return text
    
        
    @staticmethod
    def _load_json(path: str) -> Dict:
        """Load JSON from file."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

# CLI runner
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama3:8b")
    args = parser.parse_args()

    print(f"Starting Woccon Assistant with model: {args.model}")

    bot = WocconAssistant(model=args.model)
    print(bot.send_message("Hello, how are you?"))

    print("\n🗣️  Woccon CLI — type 'control + C' to exit.\n")

    while True:
        try:
            msg = input("woccon> ").strip()
            #if msg.lower() in ("quit", "exit"):
            #    break
            print("\n" + bot.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break