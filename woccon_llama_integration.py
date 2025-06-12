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

        # 6️⃣ Process the query using RAG + LLM
        # Get answer from LLM
        retrieved = self._retrieve(text)
        messages = self._build_prompt(text, retrieved, session["history"])
        raw = ollama.chat(
            model=self.model,
            messages=messages,
            options={"temperature": 0.3}
        )["message"]["content"]
        answer = self._minimal_verify(raw)
        
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

    def _retrieve(self, query: str, k: int = 12) -> List[str]:
        """
        Retrieval function for RAG.
        """
        tokens = set(re.findall(r"[a-z]+", query.lower()))
        scored = [(sum(t in chunk.lower() for t in tokens), chunk)
                  for chunk in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for score, chunk in scored[:k] if score]

    def _build_prompt(self, query: str, docs: List[str], history: deque) -> List[Dict]:
        """
        Build prompt for the LLM.
        """
        # system section with retrieved docs
        doc_text = "\n".join(docs) if docs else "NO MATCHES IN CORPUS."
        system = (
            "You are a helpful, conversational assistant for the documented Woccon language.\n"
            "Use ONLY facts from the provided documents. If you don't know, say so.\n"
            "Be friendly and educational when explaining linguistic concepts.\n"
            "When asked about phonology or sound patterns, focus on syllable structure, vowel patterns, and consonant distributions.\n\n"
            f"DOCUMENTS:\n{doc_text}"
        )

        # tail of history + new user query
        tail = list(history)[-self.ctx_turns * 2:]
        return (
            [{"role": "system", "content": system}]
            + tail
            + [{"role": "user", "content": query}]
        )

    def _minimal_verify(self, text: str) -> str:
        """
        More lenient verification that doesn't flag common words or partial matches.
        """
        # Skip verification for certain response types
        if any(marker in text for marker in [
            "I don't know", 
            "not in the dictionary",
            "not enough information",
            "can't find"
        ]):
            return text
            
        # Look for statements that claim specific words are Woccon
        patt = re.compile(r"(?:woccon (?:word|for|term)|in woccon,?).*?['\"]?([a-z\-]+)['\"]?", re.I)
        
        for m in patt.finditer(text):
            candidate = m.group(1).lower()
            
            # Check if this is a common English word or a short word that might be part of examples
            if len(candidate) <= 2 or candidate in ["the", "and", "for", "is", "of", "to", "in"]:
                continue
                
            # Check for partial matches with documented words (might be a slight variation)
            close_match = False
            for word in self.documented_words:
                # If it's a substring of a documented word or vice versa
                if candidate in word or word in candidate:
                    close_match = True
                    break
                    
            # Only warn if it's neither documented nor a close match
            if candidate not in self.documented_words and not close_match:
                return (
                    f"⚠️ Note: {candidate} isn't in the documented Woccon word list; "
                    "this may be speculative or a reconstruction.\n\n" + text
                )
        
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