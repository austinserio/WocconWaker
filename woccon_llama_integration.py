import os, json, re, logging, random
from collections import deque
from typing import Dict, List, Tuple, Optional, Any
import ollama  # your local Llama server client
from main import WocconT5
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# Import the improved lesson managers
from lesson_manager import LessonManager
from grammar_lesson_manager import GrammarLessonManager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_assistant")


class WocconAssistant:
    """RAG-powered Woccon assistant with smarter context-aware lesson offers."""

    def __init__(self,
                dict_path="woccon_language/dictionary.json",
                rules_path="woccon_language/rules.json",
                model="llama3:8b",
                model_path=None,
                ctx_turns=6):
        # Core data & model
        self.woccon = WocconT5()
        self.dictionary = self._load_json(dict_path)
        self.rules = self._load_json(rules_path)
        self.model_name = model
        self.model_path = model_path or os.environ.get('LLAMA_MODEL_PATH', '/workspace/models/llama3-8b')
        self.ctx_turns = ctx_turns
        
        # Try to use Ollama first, fall back to HuggingFace
        self.use_ollama = False
        self.tokenizer = None
        self.model = None
        
        try:
            # Check if Ollama is available
            log.info("Trying to connect to Ollama...")
            ollama.list()
            self.use_ollama = True
            log.info("Successfully connected to Ollama - will use Ollama for text generation")
        except Exception as e:
            log.info(f"Ollama not available: {e}")
            log.info(f"Will use HuggingFace model from {self.model_path}")
            try:
                # After successfully loading the HuggingFace model
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,
                    device_map="auto"
                )

                # Add these lines to fix the tokenizer warnings:
                if self.tokenizer.pad_token is None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
                    log.info("Set pad_token to eos_token")

                log.info("Successfully loaded HuggingFace model")
            except Exception as e:
                log.error(f"Error loading HuggingFace model: {e}")
                raise

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
    
    def _format_messages_for_model(self, messages: List[Dict]) -> str:
        """Convert message format to a text prompt for the model."""
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                prompt += f"System: {content}\n\n"
            elif role == "user":
                prompt += f"User: {content}\n\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n\n"
        
        prompt += "Assistant: "
        return prompt

    def reply(self, user_id: str, text: str) -> str:
        """Enhanced reply method with smarter context-aware lesson offers."""
        # Initialize or get session
        session = self.sessions.setdefault(user_id, {
            "history": deque(maxlen=self.ctx_turns * 2 + 2),
            "lesson": None,
            "last_lesson_state": None,  # Store state of last incomplete lesson
            "last_interaction": None,   # Store last user input
            "pending_action": None,     # Store a pending action choice if needed
            "context": {},              # Store context between interactions
            "topic_sequence": [],       # Track recent topics discussed (sequence matters)
            "question_count": 0,        # Track how many questions about a topic  
            "direct_lesson_request": False,  # Track if the current query is a direct lesson request
        })

        # Store last interaction
        session["last_interaction"] = text
        lower = text.lower().strip()
        
        # Update question count and reset direct lesson request flag
        session["question_count"] += 1
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
        
        # 2️⃣ Handle pending actions (confirmations, choices, etc.)
        if session["pending_action"]:
            action = session["pending_action"]
            context = session["context"]
            
            if action == "choose_lesson_type":
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
            
            if action == "confirm_lesson_start":
                lesson_type = context.get("lesson_type", "vocab")
                
                # Use the LLM to evaluate the response
                evaluation_prompt = f"""
                Classify this user response to an offer about starting a language lesson:
                
                USER RESPONSE: "{text}"
                
                CLASSIFY AS:
                1. YES - If they clearly want to start the lesson
                2. NO - If they clearly decline the lesson
                3. QUESTION - If they're asking a different question instead of responding to the offer
                
                Return ONLY "YES", "NO", or "QUESTION" with no other text.
                """
                
                try:
                    # Get evaluation from LLM
                    if self.use_ollama:
                        evaluation_messages = [{"role": "user", "content": evaluation_prompt}]
                        raw_evaluation = ollama.chat(
                            model=self.model_name,
                            messages=evaluation_messages,
                            options={"temperature": 0.1}
                        )["message"]["content"].strip().upper()
                    else:
                        # Use HuggingFace model
                        inputs = self.tokenizer(evaluation_prompt, return_tensors="pt").to(self.model.device)
                        outputs = self.model.generate(
                            inputs["input_ids"],
                            max_new_tokens=20,
                            temperature=0.1
                        )
                        raw_evaluation = self.tokenizer.decode(
                            outputs[0][inputs["input_ids"].shape[1]:],
                            skip_special_tokens=True
                        ).strip().upper()
                    
                    if "YES" in raw_evaluation:
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
                            
                    elif "NO" in raw_evaluation:
                        session["pending_action"] = None
                        
                        # If they declined lessons repeatedly, stop offering for a while
                        if context.get("declined_count", 0) >= 2:
                            session["context"]["suppress_lesson_offers"] = True
                        else:
                            session["context"]["declined_count"] = context.get("declined_count", 0) + 1
                            
                        return "No problem! What would you like to know about Woccon instead?"
                    
                    else:  # QUESTION or any other response
                        # Clear pending action since they're asking something else
                        session["pending_action"] = None
                        # Continue with normal processing - fall through
                        
                except Exception as e:
                    log.error(f"Error evaluating response with LLM: {e}")
                    # Use regex fallback if LLM call fails
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

        # 6️⃣ Process the query using RAG + LLM with strict grounding

        # A) Meta/help queries → regular chat fallback
        if self._is_help_request(lower) or re.search(r'\b(what (?:do you know about|can you tell me about)|how (?:do|would) you)\b', lower):
            # Build chat prompt
            chat_msgs = list(session["history"]) + [{"role": "user", "content": text}]
            prompt = self._format_messages_for_model(chat_msgs)

            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.tokenizer.model_max_length
            ).to(self.model.device)

            outputs = self.model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                do_sample=True,
                temperature=0.7,
                top_p=0.8,
                repetition_penalty=1.1,
                max_new_tokens=256,
                eos_token_id=self.tokenizer.eos_token_id,
                pad_token_id=self.tokenizer.pad_token_id,
            )
            return self.tokenizer.decode(
                outputs[0][ inputs["input_ids"].shape[1] : ],
                skip_special_tokens=True
            ).strip()

        # B) Grammar queries → pull from rules.json
        if any(term in lower for term in ["grammar", "suffix", "prefix", "conjugation", "morphology", "syntax", "structure"]):
            docs = [f"{r['title']}: {r['description']}" for r in self.rules.get("rules", [])]
        else:
            docs = self._retrieve(text)

        if not docs:
            return "Sorry, I don't have enough information on that topic."

        # C) Build a hard‐guard system prompt
        doc_text = "\n".join(docs)
        prompt = (
            "<|system|>\n"
            "You are a Woccon assistant. Use ONLY the facts in DOCUMENTS below. "
            "If the answer is not in DOCUMENTS, reply with “I don’t know.”\n\n"
            f"DOCUMENTS:\n{doc_text}\n\n"
            f"<|user|>\n{text}\n<|assistant|>\n"
        )

        # D) Generate via Ollama or HF model
        if self.use_ollama:
            raw = ollama.chat(
                model=self.model_name,
                messages=[{"role":"user","content": prompt}],
                options={"temperature": 0.1}
            )["message"]["content"]
        else:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.tokenizer.model_max_length
            ).to(self.model.device)

            outputs = self.model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                do_sample=True,
                temperature=0.7,
                top_p=0.8,
                repetition_penalty=1.1,
                max_new_tokens=256,
                eos_token_id=self.tokenizer.eos_token_id,
                pad_token_id=self.tokenizer.pad_token_id,
            )
            raw = self.tokenizer.decode(
                outputs[0][ inputs["input_ids"].shape[1] : ],
                skip_special_tokens=True
            )

        # E) Verify grounding
        if not any(chunk.lower() in raw.lower() for chunk in docs):
            return "Sorry, I don't have reliable information on that topic."

        answer = raw.strip()
        
        # 7️⃣ Update topic tracking
        current_topic = self._determine_current_topic(lower, answer)
        if current_topic:
            # Add to topic sequence
            session["topic_sequence"].append(current_topic)
            # Keep only the last 5 topics
            if len(session["topic_sequence"]) > 5:
                session["topic_sequence"] = session["topic_sequence"][-5:]
                
        # 8️⃣ Determine if we should offer a lesson based on the context
        should_offer_lesson = (
            not session["context"].get("suppress_lesson_offers", False) and
            session["question_count"] >= 2 and
            not self._is_help_request(lower) and
            not session["direct_lesson_request"]  # Don't offer if they just explicitly declined
        )
        
        # Check what kind of topic they're asking about to offer the right lesson
        lesson_type = None
        if should_offer_lesson:
            # Look at recent topics for patterns
            recent_topics = session["topic_sequence"][-3:] if len(session["topic_sequence"]) >= 3 else session["topic_sequence"]
            
            # If they're consistently asking about one topic, offer that lesson type
            if recent_topics and recent_topics.count("vocab") >= 2:
                lesson_type = "vocab"
            elif recent_topics and recent_topics.count("grammar") >= 2:
                lesson_type = "grammar"
            elif "grammar" in lower or any(term in lower for term in ["suffix", "prefix", "conjugation", "declension", "morphology"]):
                # Direct grammar topic in current question
                lesson_type = "grammar"
            elif self._is_about_grammar(lower, answer):
                lesson_type = "grammar"
            elif self._is_about_vocabulary(lower, answer):
                lesson_type = "vocab"
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
    
    def _determine_current_topic(self, query: str, answer: str) -> Optional[str]:
        """Analyze the query and answer to determine the current topic of conversation."""
        combined_text = (query + " " + answer).lower()
        
        # Check for vocabulary focus
        if any(term in combined_text for term in ["vocabulary", "dictionary", "word", "lexicon", "meaning", "translate"]):
            return "vocab"
            
        # Check for grammar focus
        if any(term in combined_text for term in ["grammar", "suffix", "prefix", "conjugate", "syntax", "structure"]):
            return "grammar"
            
        # Check for phonology focus
        if any(term in combined_text for term in ["phonology", "pronunciation", "sound", "syllable", "vowel", "consonant"]):
            return "phonology"
            
        # Default to None if we can't determine
        return None
    
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
        
    def _is_about_vocabulary(self, query: str, answer: str) -> bool:
        """Determine if the conversation is focused on vocabulary."""
        vocab_indicators = [
            r"\b(word|words|vocabulary|lexicon|lexeme|term|expression)\b",
            r"\b(meaning|definition|translate|translation)\b",
            r"\bhow (?:do|would|to) say\b",
            r"\bwhat (?:does|do|is|are) .+ mean\b",
        ]
        
        # Check both query and answer for indicators
        combined_text = (query + " " + answer).lower()
        return any(re.search(pattern, combined_text) for pattern in vocab_indicators)
    
    def _is_about_grammar(self, query: str, answer: str) -> bool:
        """Determine if the conversation is focused on grammar, with enhanced patterns."""
        grammar_indicators = [
            # Original patterns
            r"\b(grammar|syntax|structure|rule|pattern|form)\b",
            r"\b(suffix|prefix|affix|infix|morpheme)\b",
            r"\b(conjugate|conjugation|decline|declension)\b", 
            r"\b(modify|modification|change|transform)\b",
            r"\b(word order|case|tense|aspect|mood|voice)\b",
            
            # New patterns based on updated linguistic knowledge
            r"\b(reduplication|intensity|frequentive)\b",
            r"\b(participial|imperative|interrogative)\b",
            r"\b(possession|possessive|inalienable|alienable)\b",
            r"\b(pronominal|subject|object|marking)\b",
            r"\b(independent mode|indicative mode)\b"
        ]
        
        # Check both query and answer for indicators
        combined_text = (query + " " + answer).lower()
        return any(re.search(pattern, combined_text) for pattern in grammar_indicators)
    
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
    parser.add_argument("--model-path", default=os.environ.get('LLAMA_MODEL_PATH', '/workspace/models/llama3-8b'))
    args = parser.parse_args()

    bot = WocconAssistant(model=args.model, model_path=args.model_path)
    print("\n🗣️  Woccon CLI — type 'control + C' to exit.\n")

    while True:
        try:
            msg = input("woccon> ").strip()
            print("\n" + bot.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break