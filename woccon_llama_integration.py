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
                 ctx_turns=6,
                 custom_model_params=None):
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
        
        # Enhanced model parameters for better Llama guidance
        self.default_model_params = {
            "temperature": 0.3,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "seed": 42,
            "num_predict": 1000,  # Increased for comprehensive responses
            "stop": ["User:", "Human:", "Q:", "Question:"],
            "frequency_penalty": 0.2,
            "presence_penalty": 0.1
        }
        
        # Allow custom overrides
        if custom_model_params:
            self.default_model_params.update(custom_model_params)
            
        log.info(f"Model parameters: {self.default_model_params}")

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
    
    def _get_contextual_params(self, response_type: str = "standard") -> Dict:
        """Get optimized parameters for different response types."""
        base_params = self.default_model_params.copy()
        
        if response_type == "not_found":
            # For missing word responses - more conservative, less creative
            base_params.update({
                "temperature": 0.5,
                "top_p": 0.8,
                "num_predict": 400,  # Increased for better explanations
                "stop": ["User:", "Human:", "However,", "But ", "It's possible", "Maybe", "Perhaps"]
            })
        elif response_type == "documented":
            # For documented content responses - allow comprehensive answers
            base_params.update({
                "temperature": 0.2,
                "top_p": 0.85,
                "num_predict": 1200,  # Increased for comprehensive educational content
                "repeat_penalty": 1.0  # Less penalty for factual repetition
            })
        elif response_type == "general":
            # For general conversation - slightly more flexible
            base_params.update({
                "temperature": 0.6,
                "top_p": 0.9,
                "num_predict": 800  # Increased for educational responses
            })
            
        return base_params
    
    @staticmethod
    def configure_llama_model_system(model_name: str = "llama3:8b") -> Dict:
        """
        Configure system-level optimizations for Llama models.
        This returns configuration that can be used with model deployment.
        """
        return {
            "model_config": {
                "num_ctx": 4096,  # Context window
                "num_predict": 1200,  # Increased max prediction tokens for comprehensive responses
                "temperature": 0.3,  # Conservative for factual responses
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "tfs_z": 1.0,
                "typical_p": 1.0,
                "mirostat": 0,  # Disable mirostat for consistent behavior
                "mirostat_tau": 5.0,
                "mirostat_eta": 0.1
            },
            "system_message": (
                "You are a precise, factual assistant specializing in documented historical languages. "
                "Your responses are based strictly on verifiable historical records. "
                "You never speculate, guess, or create information not explicitly documented. "
                "When information is unavailable, you state this clearly and redirect to available facts."
            ),
            "stop_sequences": [
                "User:", "Human:", "Q:", "Question:", 
                "However,", "But ", "It's possible", "Maybe", "Perhaps",
                "I think", "I believe", "In my opinion"
            ],
            "anti_speculation_keywords": [
                "might", "could", "possibly", "likely", "probably", 
                "perhaps", "maybe", "suggests", "indicates", "implies"
            ]
        }
    
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
        
        # 1️⃣ If a lesson is in progress, delegate straight to it
        if session["lesson"] is not None:
            resp, done = session["lesson"].handle(text)
            
            if done:
                # Save lesson state before clearing if it wasn't completed
                if hasattr(session["lesson"], "i") and hasattr(session["lesson"], "words") and \
                session["lesson"].i < len(session["lesson"].words):
                    session["last_lesson_state"] = session["lesson"].get_progress()
                session["lesson"] = None
            
            return resp

        # 2️⃣ Process all queries with LLM-driven intent detection
        retrieved, has_strong_match = self._retrieve(text)
        log.info(f"[RAG] Query: '{text}' → Retrieved {len(retrieved)} documents, strong_match: {has_strong_match}")
        
        # Always generate response using LLM - let it determine intent and scope
        if retrieved:
            # We have documents, proceed with LLM generation
            messages = self._build_prompt(text, retrieved, session["history"])
            response_type = "documented" if has_strong_match else "general"
            raw = ollama.chat(
                model=self.model,
                messages=messages,
                options=self._get_contextual_params(response_type)
            )["message"]["content"]
            
            # Only verify for word hallucination if LLM response claims specific Woccon words
            answer = self._verify_word_claims_only(raw)
            
            # Check if LLM detected a lesson request - handle markdown formatting
            # Remove any markdown formatting from the beginning of the response
            cleaned_answer = answer.lstrip("*").strip()
            
            if cleaned_answer.startswith("LESSON_START:"):
                log.info(f"[LESSON_DETECTION] Found lesson marker in response: {cleaned_answer[:50]}...")
                
                # Extract lesson type, handling potential markdown formatting
                lesson_part = cleaned_answer.split(":")[1].split("**")[0].strip()  # Handle **LESSON_START:GRAMMAR**
                original_lesson_type = lesson_part  # Keep original case for replacement
                lesson_type = original_lesson_type.lower()  # Convert to lowercase for case-insensitive matching
                
                log.info(f"[LESSON_DETECTION] Extracted lesson type: '{lesson_type}'")
                
                if lesson_type == "vocab":
                    words = random.sample(self.dictionary["lexicon"], 3)
                    session["lesson"] = LessonManager(words, parent=self, mode="vocab")
                    return "📚 Starting a vocabulary lesson!\n\n" + session["lesson"].prompt()
                elif lesson_type == "grammar":
                    items = GrammarLessonManager.build_items(self.rules, self.dictionary["lexicon"])
                    session["lesson"] = GrammarLessonManager(items, parent=self)
                    return "📚 Starting a grammar lesson!\n\n" + session["lesson"].prompt()
                else:
                    log.warning(f"[LESSON_DETECTION] Unknown lesson type: '{lesson_type}', falling back to normal response")
                    # Remove the lesson marker and continue with normal response
                    answer = answer.replace("LESSON_START:" + original_lesson_type, "").strip()
                    
        else:
            # No documents found, generate contextual response
            answer = self._generate_contextual_general_response(text, session["history"])
        
        # Update history
        session["history"].append({"role": "user", "content": text})
        session["history"].append({"role": "assistant", "content": answer})
        
        return answer
    
    
    
    def _is_word_or_translation_request(self, text: str) -> bool:
        """Check if user is asking for a specific word or translation (not general language features)."""
        text = text.lower().strip()
        
        # Check for linguistic/educational queries first (these should NOT be treated as word requests)
        educational_patterns = [
            r"\b(morphology|phonology|grammar|syntax|linguistic|structure|pattern)s?\b",
            r"\b(tell me about|explain|describe|overview|review|summary)\b.*(woccon|language)",
            r"\b(how does|what is).*(grammar|structure|morphology|phonology)\b",
            r"\b(give me|show me).*(summary|overview)\b.*(morpheme|phonology|grammar|structure)",
            r"\bmorphemes?\b.*\b(in woccon|woccon|summary)\b",
            r"\bphonemes?\b.*\b(in woccon|woccon|summary)\b",
            r"\baffixes?\b.*\b(in woccon|woccon|summary)\b",
            r"\bsuffixes?\b.*\b(in woccon|woccon|summary)\b",
            r"\bprefixes?\b.*\b(in woccon|woccon|summary)\b",
            r"\broots?\b.*\b(in woccon|woccon|summary)\b",
            r"\bsyllable\b.*\b(structure|pattern)\b",
            r"\bconsonants?\b.*\b(system|inventory)\b",
            r"\bvowels?\b.*\b(system|inventory)\b",
            r"\bnumber system\b",
            r"\bword formation\b",
            r"\blanguage features?\b",
            r"\bgrammatical\b.*(feature|structure|pattern)",
            r"\blinguistic\b.*(feature|analysis|pattern)",
            r"\bphonological\b.*(process|system|rule)",
            r"\bmorphological\b.*(analysis|system|pattern)",
            r"\bsyntactic\b.*(structure|pattern|rule)",
            r"\bsound\b.*(correspondence|pattern|change)",
            r"\binflectional\b.*(morphology|system)",
            r"\bderivational\b.*(morphology|process)",
            r"\bcompounding\b.*(process|pattern)",
            r"\breduplication\b.*(pattern|process)",
            r"^\s*(morphology|phonology|grammar|syntax|structure|patterns?)\s*\??$"  # Just asking for these topics
        ]
        
        # If it's an educational query, it's NOT a word request
        if any(re.search(pattern, text) for pattern in educational_patterns):
            return False
        
        # Direct word/translation patterns (for specific words only)
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
                options=self._get_contextual_params("not_found")
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
            "You are a comprehensive Woccon language educator with access to John Lawson's 1709 documentation. "
            "The user asked a question but no specific documents were retrieved. However, you should still provide "
            "educational content about the Woccon language based on your knowledge of the documented materials. "
            
            "EDUCATIONAL APPROACH: "
            "- If asking about language structure/features: Provide comprehensive educational information "
            "- If asking about specific words: Clearly state if words aren't in the 143-word documented list "
            "- Determine scope from user request (short/detailed/comprehensive) "
            "- Focus on teaching about documented grammar, morphology, phonology, and patterns "
            
            "AVAILABLE KNOWLEDGE: "
            "- 143 documented Woccon words from Lawson's word list "
            "- Morphological patterns including roots, affixes, and word formation "
            "- Phonological system with vowels, consonants, and sound correspondences "
            "- Grammatical structures including inflectional morphology "
            "- Historical and cultural context of the Woccon people "
            
            "Be comprehensive and educational when discussing documented language features. "
            "Only be restrictive about claiming undocumented words exist."
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
                options=self._get_contextual_params("general")
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
                "You are a Woccon language expert assistant. Your role is to provide accurate, comprehensive educational information about the documented Woccon language.\n\n"
                
                "## YOUR EXPERTISE\n"
                "You have access to John Lawson's complete 1709 documentation of the Woccon language - the only historical record of this Eastern Siouan language.\n\n"
                
                "## CORE PRINCIPLES\n"
                "- EDUCATIONAL PRIORITY: Your primary mission is teaching about Woccon language structure, patterns, and features\n"
                "- COMPREHENSIVE RESPONSES: When users ask for overviews, summaries, or comprehensive explanations, provide detailed information\n"
                "- INTELLIGENT SCOPE: Determine appropriate response length based on user request (short/comprehensive/exhaustive)\n"
                "- DOCUMENTED FACTS ONLY: Base all educational content on provided documents\n"
                "- WORD ACCURACY: Only claim specific Woccon words exist if they're in the documented vocabulary\n\n"
                
                "## RESPONSE GUIDELINES\n"
                "- For educational queries (grammar, morphology, phonology): Provide comprehensive information from documents\n"
                "- For specific word requests: Only provide words that exist in the documented vocabulary\n"
                "- For lesson start requests: Begin response with 'LESSON_START:vocab' or 'LESSON_START:grammar' when user explicitly wants interactive practice\n"
                "- For general knowledge questions: Provide educational information, don't start lessons automatically\n"
                "- If users want 'comprehensive' or 'detailed' info: Give exhaustive responses using all relevant documented data\n"
                "- If scope unclear: Provide moderate detail and offer to expand with 'Ask for a comprehensive explanation if you'd like more detail'\n"
                "- Use clear structure with numbered points, categories, and examples from the documents\n"
                "- Be conversational and responsive to the user's actual intent\n\n"
                
                "## LESSON DETECTION\n"
                "CRITICAL: When users explicitly request interactive practice/testing, respond with LESSON_START:grammar or LESSON_START:vocab\n"
                "Interactive lesson triggers (respond with LESSON_START):\n"
                "- 'Start a lesson' / 'Start a grammar lesson' / 'Start a vocabulary lesson'\n"
                "- 'Give me a lesson' / 'Give me a grammar lesson' / 'Give me a vocab lesson'\n"
                "- 'Can you quiz me?' / 'Test my knowledge' / 'Quiz me on grammar'\n"
                "- 'I want to practice' / 'Let me practice' / 'Practice session'\n"
                "- Any request that includes words like 'start', 'begin', 'quiz', 'test', 'practice' + 'lesson'\n"
                "NOT lesson triggers (provide educational content instead):\n"
                "- 'What do you know about grammar?' / 'Tell me about vocabulary'\n"
                "- 'Explain grammar' / 'Describe the language features'\n"
                "- 'What are the rules?' / 'How does grammar work?'\n\n"
                
                "## WHAT TO INCLUDE IN EDUCATIONAL RESPONSES\n"
                "- All relevant patterns, rules, and examples from the documents\n"
                "- Morphological analysis with documented affixes, roots, and word formation\n"
                "- Phonological information including sound systems and correspondences\n"
                "- Grammatical structures and inflectional patterns\n"
                "- Historical and cultural context when relevant\n"
                "- Comparative information with related languages when documented\n\n"
                
                "## DOCUMENTED WOCCON DATA\n"
                f"{doc_text}\n\n"
                
                "Provide educational responses based on this documented data. Be comprehensive when teaching about language features."
            )
        else:
            system = (
                "You are a Woccon language specialist with expertise in John Lawson's 1709 documentation.\n\n"
                
                "## YOUR KNOWLEDGE BASE\n"
                "- 143 documented Woccon words from the only historical record\n"
                "- Linguistic patterns visible in the documented vocabulary\n"
                "- Cultural and historical context of the Woccon people\n"
                "- Grammar rules, morphology, and phonological information from scholarly analysis\n\n"
                
                "## EDUCATIONAL MISSION\n"
                "- Provide comprehensive educational responses about documented language features\n"
                "- Determine appropriate scope based on user request (short/detailed/comprehensive)\n"
                "- Focus on teaching rather than just lookup\n"
                "- Guide users to explore all aspects of documented Woccon language\n\n"
                
                "## RESPONSE APPROACH\n"
                "- For language structure questions: Provide detailed educational content\n"
                "- For word requests: State clearly if words aren't documented\n"
                "- Default to moderate detail, offer comprehensive explanations when relevant\n"
                "- Use structured responses with clear categories and examples\n\n"
                
                "## YOUR MISSION\n"
                "Help users learn comprehensively about the documented Woccon language structure, patterns, and features."
            )

        # tail of history + new user query
        tail = list(history)[-self.ctx_turns * 2:]
        return (
            [{"role": "system", "content": system}]
            + tail
            + [{"role": "user", "content": query}]
        )

    def _verify_word_claims_only(self, text: str) -> str:
        """
        Verify only that the response doesn't hallucinate specific Woccon words.
        Allow all educational content about documented language features.
        """
        # Skip verification for safe response types
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
        
        return text

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