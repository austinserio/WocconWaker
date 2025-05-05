import os, json, re, logging, random
from collections import deque
from typing import Dict, List, Tuple, Optional, Any
import ollama  # your local Llama server client
from main import WocconT5

# Import the improved lesson managers
from lesson_manager import LessonManager
from grammar_lesson_manager import GrammarLessonManager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_assistant")


class WocconAssistant:
    """RAG-powered Woccon assistant with enhanced mini-lessons and better decision logic."""

    def __init__(self,
                 dict_path="woccon_language/dictionary.json",
                 rules_path="woccon_language/rules.json",
                 model="llama3:8b",
                 ctx_turns=6):
        # Core data & model
        self.woccon = WocconT5()
        self.dictionary = self._load_json(dict_path)
        self.rules = self._load_json(rules_path)
        self.model = model
        self.ctx_turns = ctx_turns

        # Prepare retrieval corpus
        self.documented_words = {
            e["woccon"].lower() for e in self.dictionary.get("lexicon", [])
        }
        self.chunks = [
            f"Woccon: {e['woccon']} | English: {e['english']} | POS: {e['pos']}"
            for e in self.dictionary.get("lexicon", [])
        ]
        log.info("RAG ready: %d chunks (%d documented words)",
                 len(self.chunks),
                 len(self.documented_words))

        # Session state per user
        self.sessions: Dict[str, Dict] = {}
    
    def _is_direct_question_about_language(self, text: str) -> bool:
        """Determine if text is a direct question about the language rather than a request for interactive features."""
        text = text.lower().strip()
        
        # Patterns that indicate information requests rather than lesson requests
        info_patterns = [
            r"what (?:is|are) (?:the )?(?:sound patterns|phonology|pronunciation)",
            r"how (?:is|are) (?:the )?(?:sounds|phonology|pronunciation)",
            r"can you (?:tell|give) me (?:the )?(?:sound patterns|phonology)",
            r"what (?:does|do) (?:the )?(?:word|suffixes|prefixes)",
            r"explain (?:the )?(?:grammar|syntax|structure|phonology)",
            r"(?:sound|phonological) (?:pattern|structure|analysis)",
            r"how many (?:sounds|phonemes|vowels|consonants)",
        ]
        
        return any(re.search(pattern, text) for pattern in info_patterns)
    
    def _is_request_for_sound_analysis(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if the text is requesting sound pattern analysis for a specific word."""
        text = text.lower().strip()
        
        # Patterns to identify requests for sound analysis of specific words
        sound_patterns = [
            r"(?:sound patterns|phonology|pronunciation) (?:of|for) (?:the )?(?:word )?'?([a-z\-]+)'?",
            r"(?:analyze|examine) (?:the )?(?:sound|phonology|pronunciation) (?:of|in|for) '?([a-z\-]+)'?",
            r"how (?:is|are) '?([a-z\-]+)'? pronounced",
            r"what are (?:the )?(?:sound patterns|phonological features) (?:of|for) '?([a-z\-]+)'?",
        ]
        
        for pattern in sound_patterns:
            match = re.search(pattern, text)
            if match:
                return True, match.group(1)
        
        return False, None

    def reply(self, user_id: str, text: str) -> str:
        """Enhanced reply method with conversational lesson offering."""
        # Initialize or get session
        session = self.sessions.setdefault(user_id, {
            "history": deque(maxlen=self.ctx_turns * 2 + 2),
            "lesson": None,
            "last_lesson_state": None,  # Store state of last incomplete lesson
            "last_interaction": None,   # Store last user input
            "pending_action": None,     # Store a pending action choice if needed
            "context": {},              # Store context between interactions
            "topic_history": [],        # Track recent topics discussed
            "question_count": 0,        # Track how many questions about a topic  
        })

        # Store last interaction
        session["last_interaction"] = text
        lower = text.lower().strip()
        
        # Update question count and track topics
        session["question_count"] += 1
        
        # 1️⃣ Handle pending actions first (confirmations, choices, etc.)
        if session["pending_action"]:
            action = session["pending_action"]
            context = session["context"]
            
            if action == "confirm_lesson_start":
                lesson_type = context.get("lesson_type", "vocab")
                
                # Check if they confirmed
                if re.search(r"\b(yes|yeah|yep|sure|ok|okay|start|begin|do it|proceed)\b", lower):
                    # Clear pending action and start lesson
                    session["pending_action"] = None
                    
                    if lesson_type == "vocab":
                        words = random.sample(self.dictionary["lexicon"], 3)
                        session["lesson"] = LessonManager(words, parent=self, mode="vocab")
                        return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()
                    else:  # grammar lesson
                        items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
                        session["lesson"] = GrammarLessonManager(items, parent=self)
                        return "📚 Starting a grammar lesson!\n\n" + session["lesson"].prompt()
                        
                # Check if they declined
                elif re.search(r"\b(no|nope|nah|don'?t|not now|later|cancel)\b", lower):
                    session["pending_action"] = None
                    
                    # If they declined lessons repeatedly, stop offering for a while
                    if context.get("declined_count", 0) >= 2:
                        session["context"]["suppress_lesson_offers"] = True
                    else:
                        session["context"]["declined_count"] = context.get("declined_count", 0) + 1
                        
                    return "No problem! What would you like to know about Woccon instead?"
                
                # If they didn't clearly answer yes or no, process as a regular query
                else:
                    # Clear pending action since they're clearly interested in something else
                    session["pending_action"] = None
                    # Continue with normal processing - fall through
            
            elif action == "choose_lesson_type":
                # Check if they specified a type
                if re.search(r"\b(vocab|vocabulary|words|terms)\b", lower):
                    session["pending_action"] = None
                    
                    words = random.sample(self.dictionary["lexicon"], 3)
                    session["lesson"] = LessonManager(words, parent=self, mode="vocab")
                    return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()
                    
                elif re.search(r"\b(grammar|structure|syntax|rules)\b", lower):
                    session["pending_action"] = None
                    
                    items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
                    session["lesson"] = GrammarLessonManager(items, parent=self)
                    return "📚 Starting a grammar lesson!\n\n" + session["lesson"].prompt()
                
                # Check if they'd rather not choose
                elif re.search(r"\b(neither|none|cancel|quit|exit|stop|never mind|back|return)\b", lower):
                    session["pending_action"] = None
                    return "No problem! What would you like to know about Woccon instead?"
                    
                # If they said something else, process it as a normal query
                else:
                    session["pending_action"] = None
                    # Continue with normal processing - fall through

        # 2️⃣ If a lesson is in progress, delegate straight to it
        if session["lesson"] is not None:
            resp, done = session["lesson"].handle(text)
            
            if done:
                # Save lesson state before clearing if it wasn't completed
                if hasattr(session["lesson"], "i") and hasattr(session["lesson"], "words") and \
                   session["lesson"].i < len(session["lesson"].words):
                    session["last_lesson_state"] = session["lesson"].get_progress()
                session["lesson"] = None
            
            return resp

        # 3️⃣ Handle continuation of previous lessons
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

        # 4️⃣ Process the query using RAG + LLM
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
        
        # 5️⃣ Determine if we should offer a lesson based on the context
        # Only offer lessons if:
        # - We have answered their question first
        # - They've asked multiple questions about the same topic
        # - We haven't offered recently
        # - They haven't declined multiple offers already
        should_offer_lesson = (
            not session["context"].get("suppress_lesson_offers", False) and
            session["question_count"] >= 3 and
            not self._is_help_request(lower) and
            random.random() < 0.4  # 40% chance to offer after the conditions are met
        )
        
        # Check what kind of topic they're asking about to offer the right lesson
        lesson_type = None
        if should_offer_lesson:
            if self._is_about_vocabulary(lower, answer):
                lesson_type = "vocab"
            elif self._is_about_grammar(lower, answer):
                lesson_type = "grammar"
            else:
                # If we can't determine which type is most relevant, we won't offer
                should_offer_lesson = False
        
        # If we should offer a lesson, append the offer to our answer
        if should_offer_lesson and lesson_type:
            lesson_name = "vocabulary" if lesson_type == "vocab" else "grammar"
            
            # Set up pending action for next message
            session["pending_action"] = "confirm_lesson_start"
            session["context"]["lesson_type"] = lesson_type
            
            # Add the offer to our response
            answer += f"\n\nWould you like to start a {lesson_name} lesson? This will be an interactive quiz to help you learn Woccon {lesson_name}.\n\nSay 'yes' to begin, or 'no' if you'd prefer to just ask questions about Woccon."
        
        return answer
    
    def _is_about_vocabulary(self, query: str, answer: str) -> bool:
        """Determine if the conversation is focused on vocabulary."""
        vocab_indicators = [
            r"\b(word|words|vocabulary|lexicon|lexeme|term|expression)\b",
            r"\b(meaning|definition|translate|translation)\b",
            r"\bhow to say\b",
            r"\bwhat does .+ mean\b",
        ]
        
        # Check both query and answer for indicators
        combined_text = (query + " " + answer).lower()
        return any(re.search(pattern, combined_text) for pattern in vocab_indicators)
    
    def _is_about_grammar(self, query: str, answer: str) -> bool:
        """Determine if the conversation is focused on grammar."""
        grammar_indicators = [
            r"\b(grammar|syntax|structure|rule|pattern|form)\b",
            r"\b(suffix|prefix|affix|infix|morpheme)\b",
            r"\b(conjugate|conjugation|decline|declension)\b", 
            r"\b(modify|modification|change|transform)\b",
        ]
        
        # Check both query and answer for indicators
        combined_text = (query + " " + answer).lower()
        return any(re.search(pattern, combined_text) for pattern in grammar_indicators)
    
    def _is_help_request(self, text: str) -> bool:
        """Check if user is asking for help with commands."""
        help_patterns = [
            r"\b(help|commands|what can you do|how do i|features|capabilities)\b",
            r"what (?:can you|do you) do",
            r"(?:show|list|tell me) (?:the )?commands",
        ]
        
        return any(re.search(pattern, text) for pattern in help_patterns)
    

    def _analyze_sound_patterns(self, word: str) -> str:
        """Analyze the sound patterns of a specific word."""
        try:
            if not hasattr(self.woccon, 'identify_sound_patterns'):
                return (
                    f"I'd like to analyze the sound patterns of '{word}', but the sound pattern "
                    f"analysis functionality isn't available. Would you like me to tell you about "
                    f"this word in another way?"
                )
                
            woc_entry = None
            eng_entry = None
            
            # Try to find the word in the dictionary
            if word in self.woccon.woc_to_eng:
                woc_entry = word
                woc = word
            elif word in self.woccon.eng_to_woc:
                eng_entry = word
                woc = self.woccon.eng_to_woc[word]["woccon"]
            else:
                # Search through English entries for partial matches
                for eng, entry in self.woccon.eng_to_woc.items():
                    if word in eng or eng in word:
                        eng_entry = eng
                        woc = entry["woccon"]
                        break
                        
                if not eng_entry:
                    # Search through Woccon entries for partial matches
                    for woc_word in self.woccon.woc_to_eng.keys():
                        if word in woc_word or woc_word in word:
                            woc_entry = woc_word
                            woc = woc_word
                            break
            
            if not woc_entry and not eng_entry:
                return (
                    f"I couldn't find '{word}' in my Woccon dictionary. Would you like me to analyze "
                    f"a different word, or tell you about Woccon phonology in general?"
                )
            
            # Now analyze the sound patterns
            sound_analysis = self.woccon.identify_sound_patterns(woc)
            
            # Get the English meaning if needed
            english = ""
            if woc_entry:
                english = self.woccon.woc_to_eng[woc_entry]["english"]
            elif eng_entry:
                english = eng_entry
                
            # Format the sound analysis
            result = [f"Sound pattern analysis of '{woc}'" + (f" ('{english}')" if english else "") + ":\n"]
            
            # Show syllables
            if sound_analysis["syllables"]:
                result.append(f"Syllables: {'-'.join(sound_analysis['syllables'])}")
                result.append(f"Syllable count: {len(sound_analysis['syllables'])}")
                result.append("")
            
            # Show vowel distribution
            if sound_analysis["vowel_distribution"]:
                result.append("Vowel distribution:")
                for vowel, count in sound_analysis["vowel_distribution"].items():
                    if count > 0:
                        result.append(f"- {vowel}: {count} occurrences")
                
                if sound_analysis["dominant_vowel"]:
                    result.append(f"\nDominant vowel: {sound_analysis['dominant_vowel']}")
                result.append("")
            
            # Show sound patterns if available
            if sound_analysis["sound_patterns"]:
                result.append("Sound correspondences:")
                for pattern in sound_analysis["sound_patterns"]:
                    result.append(f"- Woccon '{pattern['woccon']}' corresponds to Catawba '{pattern['catawba']}'")
                    if pattern.get("examples"):
                        example = pattern["examples"][0] if pattern["examples"] else ""
                        result.append(f"  Example: {example}")
            
            return "\n".join(result)
        except Exception as e:
            log.error(f"Error analyzing sound patterns: {e}")
            return (
                f"I encountered an error while analyzing the sound patterns of '{word}'. "
                f"Would you like me to try a different analysis approach?"
            )

    def _matches_any_pattern(self, text: str, patterns: List[str]) -> bool:
        """Helper method to check if text matches any of the given patterns."""
        return any(re.search(pattern, text) for pattern in patterns)
        
    def _is_continue_request(self, text: str) -> bool:
        """Check if user wants to continue a previous lesson."""
        continue_patterns = [
            r"\b(continue|resume|go back to|pickup|pick up|get back to) (?:the |my |our )?(lesson|learning|studies|practice)\b",
            r"\bwhere (?:was i|were we|did we leave off)\b",
            r"\bcontinue where (?:i|we) left off\b",
            r"\bpick up from where (?:i|we) (?:were|left off)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in continue_patterns)
    
        
    def _check_for_lesson_request(self, text: str) -> Optional[Dict]:
        """Check if user is requesting a lesson, and of what type."""
        # First check for specific lesson types
        vocab_patterns = [
            r"\b(vocab|vocabulary|words|lexicon|terms|phrases|expressions)\b",
            r"\bteach me (?:some )?words\b",
        ]
        
        grammar_patterns = [
            r"\b(grammar|structure|syntax|rules|patterns|forms)\b",
            r"\bteach me (?:some )?grammar\b",
        ]
        
        # General lesson patterns
        lesson_patterns = [
            r"\b(teach|learn|start|give|do|have) (?:me |us )?(a |another )?(lesson|tutorial|practice|exercise)\b",
            r"\blearn (?:some |about )?woccon\b",
            r"\b(?:i want to|let's|i'd like to) learn\b",
            r"\bstudy woccon\b",
        ]
        
        # Check for direct information requests that might be confused for lesson requests
        if self._is_direct_question_about_language(text):
            return None
            
        # Check for sound pattern analysis requests
        is_sound_request, _ = self._is_request_for_sound_analysis(text)
        if is_sound_request:
            return None
        
        # Check for specific types first
        if any(re.search(pattern, text) for pattern in vocab_patterns):
            return {"type": "vocab"}
            
        if any(re.search(pattern, text) for pattern in grammar_patterns):
            return {"type": "grammar"}
            
        # Then check for general lesson requests
        if any(re.search(pattern, text) for pattern in lesson_patterns):
            return {"type": "unspecified"}
            
        return None

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

    bot = WocconAssistant(model=args.model)
    print("\n🗣️  Woccon CLI — type 'control + C' to exit.\n")

    while True:
        try:
            msg = input("woccon> ").strip()
            #if msg.lower() in ("quit", "exit"):
                #break
            print("\n" + bot.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break