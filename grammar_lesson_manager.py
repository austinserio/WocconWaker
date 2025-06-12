import random
from typing import List, Dict, Tuple, Optional, Any
from collections import deque
import re
import ollama
import logging
import json

log = logging.getLogger("woccon_assistant")

class GrammarLessonManager:
    """Gamified mini‐lessons for Woccon grammar rules with enhanced conversational capabilities."""
    def __init__(self, items: List[Dict], parent: Any):
        self.items = items
        random.shuffle(self.items)
        self.i = 0
        self.parent = parent
        self.stage = "question"   # stages: question -> reveal -> reinforce
        self.score = 0
        self.streak = 0
        self.question_history = []  # Track question history
        self.last_response = None   # Last user response
        self.paused = False         # Track if lesson is paused for explanations
        self.current_explanation = None  # Current explanation if any
        self.exit_attempts = 0      # Track how many times user tried to exit
        self.off_topic_counter = 0  # Track off-topic responses
        self.current_question_attempts = 0  # Track attempts on current question
        self.last_question_index = -1  # Track last question index to detect repetition
        self.repeated_explanation_requests = 0  # Track repeated explanation requests
        
        # Store alternative acceptable answers for common question types
        self.alternative_answers = {}
        
        # Set up common alternatives for different question types
        self._setup_common_alternatives()
        
    def _setup_common_alternatives(self):
        """Set up common alternative answers based on question types."""
        # This will be populated per-question in the prompt method
        self.alternative_answers = {}

    @staticmethod
    def build_items(rules_json: Dict, lexicon: List[Dict]) -> List[Dict]:
        """Build a list of grammar lesson items from the rules and lexicon."""
        items = []
        
        # Add inflectional mode questions
        if "inflectional_morphology" in rules_json.get("morphology", {}):
            modes = rules_json["morphology"]["inflectional_morphology"].get("modes", [])
            for mode in modes:
                items.append({
                    "type": "inflection_mode",
                    "question": f"What does the suffix **{mode['marker']}** indicate in Woccon?",
                    "answer": f"{mode['name']} mode ({mode['description']})"
                })
                
                # Add example-based questions
                for example in mode.get("examples", []):
                    items.append({
                        "type": "mode_identify",
                        "question": f"What inflectional mode is used in the Woccon word **{example['form']}** ({example['gloss']})?",
                        "answer": f"{mode['name']} mode, marked by {mode['marker']}"
                    })
        
        # Add reduplication questions
        if "reduplication" in rules_json.get("morphology", {}):
            items.append({
                "type": "reduplication",
                "question": "What grammatical function does reduplication serve in Woccon?",
                "answer": "Reduplication signals frequency or intensity"
            })
            
            for example in rules_json["morphology"]["reduplication"].get("examples", []):
                items.append({
                    "type": "reduplication_example",
                    "question": f"The Woccon word **{example['word']}** ({example['gloss']}) shows what morphological pattern?",
                    "answer": f"Reduplication - {example['derivation']}"
                })
        
        # Add possession pattern questions
        if "possession" in rules_json.get("morphology", {}).get("inflectional_morphology", {}):
            items.append({
                "type": "possession",
                "question": "How are possessors marked in Woccon?",
                "answer": "Inalienably possessed nouns mark possessor with prefix; alienably possessed nouns mark possessor with suffix"
            })
        
        # Add questions about common roots
        if "common_roots" in rules_json.get("morphology", {}):
            for root in rules_json["morphology"]["common_roots"]:
                items.append({
                    "type": "root_meaning",
                    "question": f"What is the meaning of the Woccon root **{root['root']}**?",
                    "answer": root['meaning']
                })
                
                # Add derivative questions
                for derivative in root.get("derivatives", [])[:1]:  # Just one example per root
                    items.append({
                        "type": "root_derivative",
                        "question": f"The Woccon word **{derivative['form']}** contains which root?",
                        "answer": f"{root['root']} meaning '{root['meaning']}'"
                    })

        return items

    def explain(self, specific_query: str = None) -> str:
        """Ask the LLM to explain this grammar rule or word form."""
        if self.i >= len(self.items):
            return "I don't have any more questions to explain. Would you like to start a new lesson?"
            
        itm = self.items[self.i]
        
        # Use the specific query if provided, otherwise generate a default one
        if not specific_query:
            query = f"Explain the grammar behind: {itm['question']}. The correct answer is: {itm['answer']}."
        else:
            query = f"Question about Woccon grammar: '{specific_query}' related to {itm['question']} (answer: {itm['answer']})."
            
        try:
            retrieved = self.parent._retrieve(query)
            messages = self.parent._build_prompt(query, retrieved, deque())  # no convo history
            resp = ollama.chat(model=self.parent.model, messages=messages)["message"]["content"]
            return resp
        except Exception as e:
            # Fallback explanation if LLM call fails
            log.error(f"Error getting explanation: {e}")
            return (
                f"I'd like to explain more about this grammar point, but I'm having trouble accessing detailed information. "
                f"The basic answer is: {itm['answer']}. Would you like to continue with the lesson?"
            )

    def prompt(self) -> str:
        """Generate the current prompt to show to the user."""
        if self.paused:
            # If we're paused for an explanation, return that instead
            if self.current_explanation:
                return self.current_explanation
            else:
                return "What would you like me to explain about this question?"
        
        if self.i >= len(self.items):
            return f"🎓 You've finished all the questions! Final score: {self.score}/{len(self.items)}"
                
        itm = self.items[self.i]
        
        # Check if this is a new question
        if self.last_question_index != self.i:
            self.current_question_attempts = 0
            self.last_question_index = self.i
            
            # Set up alternative answers for this specific question
            self._setup_question_alternatives(itm)
        
        # Add current question to history
        if len(self.question_history) <= self.i or self.question_history[self.i]["question"] != itm["question"]:
            self.question_history.append({
                "index": self.i,
                "question": itm["question"],
                "answer": itm["answer"],
                "item": itm
            })
            
        # Format based on streak and score
        streak_bonus = ""
        if self.streak >= 3:
            streak_bonus = f" | 🔥 Streak: {self.streak}"
            
        progress = f"{self.i+1}/{len(self.items)}"
        
        # Provide adaptive hints based on attempts
        hint = ""
        if self.current_question_attempts >= 2:
            # Generate hint based on question type
            q_type = itm.get("type", "")
            if "root_meaning" in q_type:
                hint = "\n💡 Hint: Think about common elements in nature or basic concepts."
            elif "root_derivative" in q_type:
                hint = f"\n💡 Hint: Look at the first part of the word and compare it to common Woccon roots."
            elif "inflection" in q_type:
                hint = "\n💡 Hint: This relates to how verbs change to express tense, mood, or aspect."
            elif "reduplication" in q_type:
                hint = "\n💡 Hint: Think about patterns where parts of words are repeated."
            else:
                hint = "\n💡 Hint: If you're stuck, try typing 'explain' for more information."
        
        return (
            f"🏷️ Grammar Q {progress} | 🏆 Score: {self.score}{streak_bonus}\n"
            f"❓ {itm['question']}{hint}\n"
            f"(Type your answer, ask for an explanation, or let me know if you're not sure.)"
        )
        
    def _setup_question_alternatives(self, question_item: Dict):
        """Set up alternative acceptable answers for a specific question."""
        self.alternative_answers = {}
        
        question_type = question_item.get("type", "")
        answer = question_item.get("answer", "")
        
        # Add common alternatives based on question type
        if "inflection_mode" in question_type or "mode_identify" in question_type:
            # For mode questions, allow just the mode name or just the description
            if "imperative mode" in answer.lower():
                self.alternative_answers = {
                    "imperative": "imperative mode",
                    "command": "imperative mode (command)",
                    "commands": "imperative mode (commands)",
                    "command form": "imperative mode (command form)",
                    "instruction": "imperative mode (instruction)"
                }
            elif "narrative mode" in answer.lower():
                self.alternative_answers = {
                    "narrative": "narrative mode",
                    "story": "narrative mode (storytelling)",
                    "storytelling": "narrative mode (storytelling)"
                }
            elif "participial mode" in answer.lower():
                self.alternative_answers = {
                    "participial": "participial mode",
                    "participle": "participial mode"
                }
            elif "independent mode" in answer.lower():
                self.alternative_answers = {
                    "independent": "independent mode",
                    "primary": "independent mode (primary action)"
                }
        
        elif "reduplication" in question_type:
            # For reduplication questions
            self.alternative_answers = {
                "repetition": "reduplication (repetition)",
                "repetition for emphasis": "reduplication (repetition for emphasis)",
                "emphasis": "reduplication (emphasis)",
                "intensity": "reduplication (intensity)",
                "frequency": "reduplication (frequency)",
                "repeating sounds": "reduplication (repeating sounds)",
                "repeated syllables": "reduplication (repeated syllables)",
                "repeat": "reduplication (repeating)",
                "repeated": "reduplication (repeated)",
                "intensive": "reduplication - intensive"
            }
            
        elif "root_meaning" in question_type:
            # For root meaning questions, accept any of the meanings
            parts = answer.split(", ")
            for part in parts:
                self.alternative_answers[part] = answer
                
        elif "root_derivative" in question_type:
            # For root questions, accept just the root
            root_match = re.search(r"([a-z]+)-", answer)
            if root_match:
                root = root_match.group(1)
                self.alternative_answers[root] = f"{root}- root"
                self.alternative_answers[f"{root}-"] = f"{root}- root"
                self.alternative_answers[f"{root} root"] = f"{root}- root"
    
    def is_answer_attempt(self, text: str) -> bool:
        """Check if the text is likely a genuine attempt to answer the question."""
        text_lower = text.lower()
        
        # Check for common patterns indicating this is NOT an answer attempt
        non_answer_patterns = [
            r"^\s*(idk|not sure|no idea|no clue|confused|don'?t know)\s*$",  # Just expressions of uncertainty
            r"^\s*(help|hint|clue|explain|what is it|tell me)\s*$",  # Requests for help
            r"^\s*(next|skip|pass|continue|go on)\s*$",  # Navigation requests
            r"^\s*(exit|quit|stop|end)\s*$",  # Exit requests
            r"^\s*(what|who|when|where|why|how)\s*\?",  # Just questions
            r"^\s*([hm]+|[um]+|[er]+)\s*$",  # Just hesitation noises
            r"^\s*(lol|lmao|wtf|omg)\s*$"  # Just reactions
        ]
        
        # If it matches any non-answer pattern, it's not an answer attempt
        if any(re.search(pattern, text_lower) for pattern in non_answer_patterns):
            return False
            
        # If it contains "it's" or "it is" or other answer-like phrases, it's likely an answer attempt
        answer_indicators = [
            r"^\s*it'?s\s",
            r"^\s*that'?s\s",
            r"^\s*they'?re\s",
            r"^\s*i\s*think\s*it'?s\s",
            r"^\s*maybe\s*it'?s\s",
            r"^\s*probably\s",
            r"\b(used|means|indicates|shows|expresses|denotes)\b",
            r"^\s*the\s*answer\s*is\s",
            r"answer",
            r"told you",
            r"already said",
            r"said",
            r"mentioned"
        ]
        
        # Extract the answer from the current question
        if self.i < len(self.items):
            correct_answer = self._normalize_answer(self.items[self.i]["answer"])
            
            # If the text contains any part of the correct answer, it's likely an answer attempt
            for word in correct_answer.split():
                if len(word) > 3 and word in text_lower:  # Only consider words longer than 3 chars
                    return True
                    
        # If the text contains any answer indicator, it's likely an answer attempt
        return any(re.search(pattern, text_lower) for pattern in answer_indicators)

    def is_dont_know_response(self, text: str) -> bool:
        """Check if user response indicates they don't know using natural language understanding."""
        text = text.lower().strip()
        dont_know_patterns = [
            r"\b(i don't know|idk|not sure|no idea|no clue|uncertain|don't remember|forgot|unsure)\b",
            r"\b(can'?t remember|don'?t have a guess|skip|pass|next)\b",
            r"\b(what is it|what'?s the answer|tell me|reveal|show me)\b",
            r"\b(um|uh|hmm|err)\b",  # Hesitation markers
            r"\b(lol|haha)\b",  # Laughter often indicates uncertainty in this context
            r"\b(whatever|dunno|who knows|doesn't matter|don't care)\b",  # Dismissive responses
            r"\b(not positive|not confident|not certain|not really sure)\b",  # More natural uncertainty
            r"\b(i'm not|im not).*(sure|positive|certain|confident)\b",  # "I'm not sure/positive"
            r"\b(kind of|kinda|maybe|probably|possibly).*(unsure|uncertain)\b",  # Hedging language
            r"\b(no idea|haven'?t a clue|give up|stumped)\b",  # Additional expressions
            r"\b(beats me|beyond me|drawing a blank|lost|clueless)\b",  # More expressions
        ]
        
        # Check if text is just a negative response
        if text in ["no", "nope", "not", "negative", "nah"]:
            return True
            
        return any(re.search(pattern, text) for pattern in dont_know_patterns)

    def is_exit_request(self, text: str) -> bool:
        """Check if user is trying to exit the lesson using LLM contextual understanding."""
        # Quick keyword check for very obvious cases
        obvious_exit_words = ['exit', 'quit', 'stop', 'end', 'leave', 'cancel']
        if any(word in text.lower() for word in obvious_exit_words):
            return True
            
        # For ambiguous cases, use LLM to understand intent
        try:
            prompt = f"""
            Analyze this user message in the context of a grammar lesson to determine if they want to exit/leave the lesson.

            USER MESSAGE: "{text}"
            CONTEXT: The user is currently in the middle of a grammar learning lesson.

            Determine if the user wants to:
            - EXIT the lesson (stop doing the lesson entirely)
            - CONTINUE with the lesson (stay in the lesson)

            Consider expressions like:
            - "I'm done" = EXIT
            - "That's enough" = EXIT  
            - "This is hard" = CONTINUE (they're expressing difficulty, not wanting to leave)
            - "Uhhhhhhhhhhhhh got a suggestion?" = CONTINUE (asking for help, not leaving)
            - "I give up" = EXIT
            - "Can you help me?" = CONTINUE

            Respond with only: EXIT or CONTINUE
            """
            
            messages = [{"role": "user", "content": prompt}]
            response = ollama.chat(
                model=self.parent.model,
                messages=messages,
                options={"temperature": 0.1, "num_predict": 10}
            )["message"]["content"].strip().upper()
            
            return "EXIT" in response
            
        except Exception as e:
            log.error(f"Error in LLM exit detection: {e}")
            # Fallback to conservative approach - only obvious exit words
            return any(word in text.lower() for word in obvious_exit_words)

    def is_explanation_request(self, text: str) -> bool:
        """Check if user is asking for an explanation using LLM contextual understanding."""
        # Quick keyword check for very obvious cases
        obvious_explain_words = ['explain', 'explanation', 'why', 'how', 'what', 'help', 'suggestion', 'hint']
        if any(word in text.lower() for word in obvious_explain_words):
            # Use LLM to distinguish between explanation requests and other types of questions
            try:
                prompt = f"""
                Analyze this user message in the context of a grammar lesson to determine their intent.

                USER MESSAGE: "{text}"
                CONTEXT: The user is currently in a grammar learning lesson and just encountered a question.

                Determine if the user wants:
                - EXPLANATION (they want more information about the current grammar concept)
                - HELP (they want assistance with the current question)
                - OTHER (they're asking something unrelated or just answering)

                Examples:
                - "explain this grammar rule" = EXPLANATION
                - "Uhhhhhhhhhhhhh got a suggestion?" = HELP
                - "help me" = HELP
                - "what does this suffix mean?" = EXPLANATION
                - "I don't know what this is" = HELP
                - "can you tell me more?" = EXPLANATION
                - "imperative" = OTHER (just an answer)

                Respond with only: EXPLANATION, HELP, or OTHER
                """
                
                messages = [{"role": "user", "content": prompt}]
                response = ollama.chat(
                    model=self.parent.model,
                    messages=messages,
                    options={"temperature": 0.1, "num_predict": 15}
                )["message"]["content"].strip().upper()
                
                return "EXPLANATION" in response or "HELP" in response
                
            except Exception as e:
                log.error(f"Error in LLM explanation detection: {e}")
                # Fallback to keyword check
                return any(word in text.lower() for word in obvious_explain_words)
        
        return False
        
    def is_continue_request(self, text: str) -> bool:
        """Check if user wants to continue with the lesson."""
        text = text.lower()
        continue_patterns = [
            r"\b(continue|resume|go on|next|proceed|keep going)\b",
            r"\b(let's continue|move on|move forward|next question)\b",
            r"\b(back to lesson|back to questions|go ahead)\b",
            r"\b(let's go|onward|forward|carry on|next one|another)\b",
            r"\b(more questions|give me another|another one|next one please)\b",
            r"\b(continue lesson|let's do more|ready for more)\b",
            r"\b(sure|okay|ok|yeah|yes|yep|yup)\b" # Add affirmative responses
        ]
        
        return any(re.search(pattern, text) for pattern in continue_patterns)

    def is_different_question_request(self, text: str) -> bool:
        """Check if user wants to ask a different question entirely."""
        text = text.lower()
        different_q_patterns = [
            r"\b(different question|another question|ask you something|something else)\b",
            r"\b(i have a |can i ask|wondering about|curious about)\b",
            r"\b(actually,|instead,|rather|unrelated)\b",
            r"\b(by the way|off topic|side note|random question)\b",
            r"\b(quick question|just curious|while we're here)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in different_q_patterns)
        
    def is_previous_question_reference(self, text: str) -> bool:
        """Check if user is referring to a previous question."""
        text = text.lower()
        prev_patterns = [
            r"\b(previous|earlier|before|last|ago|that other|remember when|back to)\b",
            r"\b(what was the|go back|can we revisit|question \d+)\b",
            r"\b(earlier question|prior question|first question)\b",
            r"\b(question (one|two|three|four|five|six|seven|eight|nine|ten))\b",
        ]
        
        return any(re.search(pattern, text) for pattern in prev_patterns)
    
    def is_repeat_request(self, text: str) -> bool:
        """Check if user is asking to repeat the question."""
        text = text.lower()
        repeat_patterns = [
            r"\b(repeat|say again|once more|what was the question)\b",
            r"\b(didn't catch that|didn't hear|what did you say|what was that)\b",
            r"\b(remind me|tell me again|one more time|read it again)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in repeat_patterns)
    
    def is_hint_request(self, text: str) -> bool:
        """Check if user is asking for a hint using LLM contextual understanding."""
        # Check for obvious hint words
        hint_words = ['hint', 'clue', 'tip', 'stuck', 'struggling', 'suggestion']
        if any(word in text.lower() for word in hint_words):
            return True
            
        # For less obvious cases, check if it's a request for help with the current question
        help_indicators = ['help', 'how', 'what', 'uhh', 'umm', 'err']
        if any(indicator in text.lower() for indicator in help_indicators):
            try:
                prompt = f"""
                Analyze this user message in a grammar lesson context.

                USER MESSAGE: "{text}"
                CONTEXT: User is answering a grammar question and seems to need assistance.

                Is this a request for a HINT/HELP with the current question?

                Examples:
                - "Uhhhhhhhhhhhhh got a suggestion?" = YES (asking for help)
                - "help me" = YES
                - "I'm stuck" = YES  
                - "what should I do?" = YES
                - "imperative" = NO (just an answer)
                - "I don't know" = NO (giving up, not asking for hint)

                Respond with only: YES or NO
                """
                
                messages = [{"role": "user", "content": prompt}]
                response = ollama.chat(
                    model=self.parent.model,
                    messages=messages,
                    options={"temperature": 0.1, "num_predict": 5}
                )["message"]["content"].strip().upper()
                
                return "YES" in response
                
            except Exception as e:
                log.error(f"Error in LLM hint detection: {e}")
                return any(word in text.lower() for word in hint_words)
        
        return False
    
    def get_referenced_question(self, text: str) -> Optional[Dict]:
        """Try to determine which previous question the user is referring to."""
        text = text.lower()
        
        # Check for numeric references
        number_match = re.search(r"question (\d+)", text)
        if number_match:
            q_num = int(number_match.group(1))
            if 0 < q_num <= len(self.question_history):
                return self.question_history[q_num - 1]
        
        # Check for "previous" or "last" references
        if re.search(r"\b(previous|last|before)\b", text):
            if len(self.question_history) > 1:
                return self.question_history[-2]  # Return the question before the current one
        
        # Check for "X questions ago"
        ago_match = re.search(r"(\d+) questions? ago", text)
        if ago_match:
            steps_back = int(ago_match.group(1))
            if steps_back < len(self.question_history):
                return self.question_history[-(steps_back + 1)]
        
        # Check for spelled-out numbers
        word_to_num = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }
        for word, num in word_to_num.items():
            if re.search(fr"question {word}", text):
                if 0 < num <= len(self.question_history):
                    return self.question_history[num - 1]
                
        # Default to the most recent question if we can't determine
        if self.question_history:
            return self.question_history[-1]
            
        return None
    
    def generate_hint(self) -> str:
        """Generate a hint for the current question."""
        if self.i >= len(self.items):
            return "There are no more questions to hint about."
            
        itm = self.items[self.i]
        answer = itm["answer"]
        q_type = itm.get("type", "")
        
        # Generate hint based on question type and answer
        if "root_meaning" in q_type:
            words = answer.split()
            if len(words) > 1:
                return f"💡 This root is related to {words[0]}."
            return "💡 Think about basic elements or common concepts in language."
        
        elif "root_derivative" in q_type:
            # For root derivatives, hint at the first few characters
            root_match = re.search(r"([a-z]+)-", answer)
            if root_match:
                root = root_match.group(1)
                if len(root) > 2:
                    return f"💡 The root starts with '{root[:2]}'..."
            return "💡 Look at the first part of the word before any suffixes."
            
        elif "inflection_mode" in q_type:
            if "marker" in answer:
                return "💡 This relates to how verbs change to express grammatical categories."
            return "💡 Think about how words are modified to change their meaning."
            
        elif "mode_identify" in q_type:
            if "mode" in answer:
                return "💡 This is about a specific grammatical mood or mode."
            return "💡 Look at the ending of the word for clues."
            
        elif "reduplication" in q_type:
            return "💡 Notice any repeated patterns or sounds in the word."
            
        # Generic hint
        return "💡 The answer is related to how Woccon words are formed or modified."
        
    def _string_similarity(self, a: str, b: str) -> float:
        """Calculate string similarity ratio using Levenshtein distance."""
        # Simple implementation without requiring additional libraries
        if len(a) > len(b):
            a, b = b, a
            
        distances = range(len(a) + 1)
        for i2, c2 in enumerate(b):
            distances_ = [i2+1]
            for i1, c1 in enumerate(a):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
            
        # Convert to similarity ratio (0 to 1)
        max_len = max(len(a), len(b))
        if max_len == 0:
            return 1.0  # Both strings empty
        return 1 - (distances[-1] / max_len)
    
    def _normalize_answer(self, text: str) -> str:
        """Normalize text for better comparison."""
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation and extra spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove common filler words for comparing answers
        fillers = ['the', 'a', 'an', 'is', 'are', 'that', 'this', 'these', 'those']
        for filler in fillers:
            text = re.sub(fr'\b{filler}\b', '', text)
        
        return re.sub(r'\s+', ' ', text).strip()
        
    def extract_key_concepts(self, text: str) -> List[str]:
        """Extract key concepts from an answer to compare against user input."""
        # Use regex to find key terms like:
        # - Root words (like "roo-")
        # - Grammatical terms (like "mode", "marker", "prefix", "suffix")
        # - Concepts (like "reduplication", "possession")
        
        text = text.lower()
        
        # Extract roots (words with hyphens like "roo-", "ya-")
        roots = re.findall(r'([a-z]+)-', text)
        
        # Extract quoted words 
        quoted = re.findall(r'"([^"]+)"|\*\*([^*]+)\*\*|\'([^\']+)\'', text)
        quoted_words = []
        for match in quoted:
            # Combine all capturing groups and take non-empty ones
            for group in match:
                if group:
                    quoted_words.append(group.lower())
        
        # Extract grammatical terms
        grammatical_terms = []
        grammar_patterns = [
            r'\b(mode|marker|prefix|suffix|reduplication|possession|root|inflection|command|imperative)\b',
            r'\b(narrative|independent|imperative|subjunctive)\b',
            r'\b(intensity|intensive|frequency|iterative|continuous|progressive|repetition|emphasis)\b',
            r'\b(meaning|cloth|hide|material|water|path|way|container|wood|tree)\b',
            r'\b(ya|yau|watta|yon|roo)\b'  # Common Woccon roots without hyphens
        ]
        
        for pattern in grammar_patterns:
            terms = re.findall(pattern, text)
            grammatical_terms.extend(terms)
        
        # Combine all key concepts
        key_concepts = roots + quoted_words + grammatical_terms
        
        # Remove duplicates and return
        return list(set(key_concepts))
        
    def compare_key_concepts(self, user_answer: str, correct_answer: str) -> Tuple[float, List[str], List[str]]:
        """
        Compare key concepts between user answer and correct answer.
        Returns: (match_ratio, matched_concepts, missing_concepts)
        """
        # Quick check for non-answers
        non_answer_markers = ['errr', 'umm', 'idk', 'wtf', 'lmao', 'lol', 'clue', 'shit', 'fuck']
        if any(marker in user_answer.lower() for marker in non_answer_markers) and len(user_answer.split()) <= 3:
            # This is almost certainly not a real answer attempt
            return 0.0, [], self.extract_key_concepts(correct_answer.lower())
            
        # Extract key concepts from both answers
        user_concepts = self.extract_key_concepts(user_answer.lower())
        correct_concepts = self.extract_key_concepts(correct_answer.lower())
        
        # Find matched and missing concepts
        matched_concepts = [c for c in user_concepts if c in correct_concepts]
        missing_concepts = [c for c in correct_concepts if c not in user_concepts]
        
        # Calculate match ratio
        if not correct_concepts:
            return 1.0, matched_concepts, missing_concepts  # Avoid division by zero
            
        match_ratio = len(matched_concepts) / len(correct_concepts)
        
        return match_ratio, matched_concepts, missing_concepts
        
    def check_alternative_answers(self, user_answer: str) -> bool:
        """Check if the user's answer matches any of the alternative acceptable answers."""
        if not self.alternative_answers:
            return False
            
        normalized_user_answer = self._normalize_answer(user_answer)
        
        # First check for exact match with any alternative
        if normalized_user_answer in self.alternative_answers:
            return True
            
        # Then check for partial matches (one alternative is fully contained in the user's answer)
        for alt_key in self.alternative_answers.keys():
            # Check if alternative is a substantial part of the user's answer
            if len(alt_key) > 3 and alt_key in normalized_user_answer:
                return True
                
            # Check if user's answer is a substantial part of the alternative
            if len(normalized_user_answer) > 3 and normalized_user_answer in alt_key:
                return True
                
        # Finally check string similarity
        for alt_key in self.alternative_answers.keys():
            if self._string_similarity(normalized_user_answer, alt_key) > 0.8:
                return True
                
        return False
        
    def check_answer_with_llm(self, user_answer: str, correct_answer: str, question: str) -> Tuple[bool, float, str, bool]:
        """
        Use the LLM to evaluate if the user's answer is correct or close
        Returns: (is_correct, confidence_score, explanation, is_partial)
        """
        # Always check for alternative answers first
        if self.check_alternative_answers(user_answer):
            return True, 0.95, "Matches acceptable alternative answer", False
            
        try:
            # Check if this is even an answer attempt
            if not self.is_answer_attempt(user_answer):
                return False, 0.9, "Not a genuine answer attempt", False
                
            # Next use key concept extraction
            match_ratio, matched_concepts, missing_concepts = self.compare_key_concepts(user_answer, correct_answer)
            
            # Quick check for obvious wrong answers based on length and content
            if len(user_answer.split()) > 3 and match_ratio < 0.1 and any(
                nonsense_marker in user_answer.lower() 
                for nonsense_marker in ['err', 'errrr', 'umm', 'hmm', 'lol', 'lmao', 'clue',
                                      'uhh', 'ugh', 'wtf', 'idk', 'omg', 'shit']
            ):
                # This is almost certainly not an attempt at answering
                return False, 0.1, "Response contains expressions of uncertainty", False
            
            # If we have a very strong match based on key concepts, don't bother calling the LLM
            if match_ratio > 0.9 and len(matched_concepts) >= 2:
                return True, 0.95, "Answer contains all key concepts", False
            
            # Prepare a conversational evaluation prompt
            prompt = f"""
            Evaluate if this user's answer for a language learning exercise is correct.
            
            QUESTION: {question}
            CORRECT ANSWER: {correct_answer}
            USER'S ANSWER: {user_answer}
            
            Additional context: The user is learning grammar for a constructed language called Woccon.
            This is an informal learning context, so be forgiving of partial answers if they show understanding.
            
            TASK: Determine if the user's answer is:
            1. Correct - Contains the key concepts, even if expressed informally (e.g., saying "it's a command" for "imperative mode")
            2. Partially correct - Has some correct elements but is missing important information
            3. Incorrect - Wrong or completely off-topic
            
            Key considerations:
            - Accept informal language (e.g., "repetition for emphasis" for "reduplication")
            - Be understanding of users trying to insist on their answer being correct
            - Don't accept expressions like "idk", "not sure", random sounds "errr", etc.
            - If the user is clearly attempting to provide an answer, be generous
            
            RESPONSE FORMAT:
            {{
                "evaluation": "correct", "partially_correct", or "incorrect",
                "confidence": [0-1 scale, where 1 is highest confidence],
                "explanation": "Brief explanation of your reasoning",
                "key_concepts_present": [list of key concepts that were present in the user's answer],
                "key_concepts_missing": [list of key concepts that were missing]
            }}
            
            Return ONLY this JSON with no additional text.
            """
            
            # Get evaluation from LLM
            retrieved = self.parent._retrieve(prompt)
            messages = self.parent._build_prompt(prompt, retrieved, deque())  # no convo history
            response = ollama.chat(model=self.parent.model, messages=messages)["message"]["content"]
            
            # Parse the response
            # The response should be a JSON string, extract it and parse
            try:
                # Try to find JSON structure in the response
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    result = json.loads(json_str)
                else:
                    # Fallback if no JSON structure found
                    raise ValueError("No JSON structure found in LLM response")
                
                is_correct = result.get("evaluation") == "correct"
                is_partial = result.get("evaluation") == "partially_correct"
                confidence = float(result.get("confidence", 0.5))
                explanation = result.get("explanation", "")
                
                # Double check with our heuristics
                
                # 1. Check for expressions of ignorance/uncertainty as a safeguard
                uncertainty_markers = ['idk', 'not sure', 'no idea', 'no clue', 'umm', 'uhh', 'err', 
                                      'lol', 'lmao', 'wtf', 'ugh', 'help', 'plz', 'pls', 'hmm',
                                      'what', 'huh', 'eh', 'meh', 'dunno', 'help me']
                                      
                if any(marker in user_answer.lower() for marker in uncertainty_markers) and is_correct:
                    # Don't mark answers containing uncertainty markers as correct
                    log.warning(f"Overriding LLM evaluation: answer contains uncertainty markers but was marked correct")
                    return False, 0.2, "Response contains expressions of uncertainty", False
                
                # Use the LLM result, but log disagreements for monitoring
                if ((is_correct and match_ratio < 0.3) or 
                    (not is_correct and not is_partial and match_ratio > 0.7)):
                    log.warning(f"LLM and key concept evaluation disagree: LLM={is_correct}, concept_match={match_ratio}")
                
                return is_correct, confidence, explanation, is_partial
            
            except (json.JSONDecodeError, ValueError) as e:
                log.error(f"Error parsing LLM response: {e} - Response: {response}")
                # Fall back to alternatives and key concept matching if JSON parsing fails
                
                # Check for insistence that an answer is correct
                insistence_indicators = ["i told you", "my answer", "already said", "said", "that's what I said"]
                if any(indicator in user_answer.lower() for indicator in insistence_indicators) and matched_concepts:
                    # If user is insisting and they had some matched concepts, be generous
                    return matched_concepts and len(matched_concepts) >= 1, 0.6, "Accepted based on user insistence with partial match", True
                
                # Otherwise use key concept matching
                if match_ratio > 0.85:
                    return True, match_ratio, f"Contains key concepts: {', '.join(matched_concepts)}", False
                elif match_ratio > 0.5:
                    return False, match_ratio, f"Missing key concepts: {', '.join(missing_concepts)}", True
                else:
                    return False, match_ratio, "Answer lacks required key concepts", False
                
        except Exception as e:
            log.error(f"Error in LLM answer check: {e}")
            # Fall back to key concept matching and alternatives if LLM call fails completely
            
            # Check for insistence that an answer is correct
            insistence_indicators = ["i told you", "my answer", "already said", "said"]
            if any(indicator in user_answer.lower() for indicator in insistence_indicators):
                # If user is insisting, be more generous with matching
                if matched_concepts and len(matched_concepts) >= 1:
                    return True, 0.6, "Accepted based on user insistence", False
            
            if match_ratio > 0.85:
                return True, match_ratio, f"Contains key concepts: {', '.join(matched_concepts)}", False
            elif match_ratio > 0.5:
                return False, match_ratio, f"Missing key concepts: {', '.join(missing_concepts)}", True
            else:
                return False, match_ratio, "Answer lacks required key concepts", False
                
    def handle(self, user_text: str) -> Tuple[str, bool]:
        """Handle user input with natural language understanding."""
        if self.i >= len(self.items):
            return (f"🎓 You've finished all the questions! Final score: {self.score}/{len(self.items)}", True)
            
        usr = user_text.strip()
        usr_lower = usr.lower()
        
        # Store last response
        self.last_response = usr
        
        # HANDLE REPEAT REQUESTS
        if self.is_repeat_request(usr_lower):
            current_q = self.items[self.i]["question"]
            return (f"Sure, the current question is: ❓ {current_q}\n\n(Type your answer, ask for an explanation, or let me know if you're not sure.)", False)
        
        # HANDLE EXIT REQUESTS
        if self.is_exit_request(usr_lower):
            self.exit_attempts += 1
            self.paused = False  # Reset pause state
            
            # If they've tried to exit multiple times, just let them out
            if self.exit_attempts >= 2:
                return (f"👋 Grammar lesson exited. Final score: {self.score}/{len(self.items)}.", True)
            else:
                return (
                    f"Would you like to exit the lesson? Your current score is {self.score}/{len(self.items)}. "
                    f"Type 'yes' to confirm exit, or 'continue' to keep going with the lesson.", 
                    False
                )
                
        # Confirm exit if they previously wanted to exit
        if self.exit_attempts > 0 and re.search(r"\b(yes|yeah|yep|yup|correct|right|sure|ok|okay)\b", usr_lower):
            return (f"👋 Grammar lesson exited. Final score: {self.score}/{len(self.items)}.", True)
            
        # Reset exit counter if they want to continue
        if self.exit_attempts > 0 and self.is_continue_request(usr_lower):
            self.exit_attempts = 0
            return (f"Great! Let's continue with the lesson.\n\n{self.prompt()}", False)
            
        # HANDLE COMPLETELY DIFFERENT QUESTIONS
        if self.is_different_question_request(usr_lower):
            # If they want to ask something unrelated
            self.paused = True
            self.off_topic_counter += 1
            
            resp = (
                f"I see you have a different question. I'd be happy to help with that, "
                f"but it sounds unrelated to the current grammar lesson. Would you like to:"
                f"\n\n1. Exit the lesson and ask your question"
                f"\n2. Continue with the grammar lesson"
                f"\n\nJust let me know which you prefer."
            )
            self.current_explanation = resp
            return (resp, False)
        
        # HANDLE HINT REQUESTS
        if self.is_hint_request(usr_lower):
            hint = self.generate_hint()
            return (f"{hint}\n\nWould you like to try answering now, or do you need more help?", False)
        
        # HANDLE PAUSE FOR EXPLANATIONS
        if self.paused:
            # If user wants to continue the lesson
            if self.is_continue_request(usr_lower):
                self.paused = False
                self.current_explanation = None
                self.off_topic_counter = 0
                return (f"Alright, let's continue with the lesson!\n\n{self.prompt()}", False)
                
            # If they responded to our off-topic offer
            if self.off_topic_counter > 0 and re.search(r"\b(1|exit|ask|question)\b", usr_lower):
                return (f"Let's exit the lesson so I can help with your question. What would you like to know?", True)
                
            # Otherwise treat as a follow-up question and get explanation
            try:
                explanation = self.explain(usr)
                self.current_explanation = (
                    f"📚 {explanation}\n\n"
                    "Would you like to know anything else, or shall we continue with the lesson?"
                )
                return (self.current_explanation, False)
            except Exception as e:
                # Fallback if explanation fails
                log.error(f"Error in explanation: {e}")
                self.paused = False
                return (f"I couldn't get that specific information. Let's continue with the lesson.\n\n{self.prompt()}", False)

        # HANDLE REFERENCES TO PREVIOUS QUESTIONS
        if self.is_previous_question_reference(usr_lower):
            referenced_q = self.get_referenced_question(usr_lower)
            if referenced_q:
                response = (
                    f"📚 That question was: {referenced_q['question']}\n"
                    f"The answer was: **{referenced_q['answer']}**\n\n"
                    "Would you like me to explain more about this? Otherwise, we'll continue with the current question."
                )
                # Pause the lesson flow to allow follow-up questions
                self.paused = True
                return (response, False)
        
        # HANDLE EXPLANATION REQUESTS
        if self.is_explanation_request(usr_lower):
            self.paused = True
            self.off_topic_counter = 0
            self.repeated_explanation_requests += 1
            
            try:
                explanation = self.explain()
                
                # Additional encouragement if they're asking for multiple explanations
                encouragement = ""
                if self.repeated_explanation_requests > 1:
                    encouragement = (
                        "It looks like you're really trying to understand this concept, which is great! "
                        "Remember, language learning takes time, so don't worry if it's not clicking right away. "
                    )
                
                explanation_text = (
                    f"📚 {encouragement}Explanation for question: '{self.items[self.i]['question']}'\n\n"
                    f"{explanation}\n\n"
                    "Would you like to know anything else, or shall we continue with the lesson?"
                )
                self.current_explanation = explanation_text
                return (explanation_text, False)
            except Exception as e:
                log.error(f"Error in explanation: {e}")
                return (
                    "I'm having trouble generating a detailed explanation right now. "
                    "Let's continue with the lesson instead.\n\n" + self.prompt(),
                    False
                )

        # HANDLE "I DON'T KNOW" RESPONSES
        if self.is_dont_know_response(usr_lower):
            # Reset streak on giving up
            self.streak = 0
            correct_answer = self.items[self.i]["answer"]
            resp = f"ℹ️ No problem! The answer is **{correct_answer}**.\n\n"
            
            # Ask if they want an explanation
            self.paused = True
            explanation_offer = (
                f"{resp}Would you like me to explain this further, or shall we continue to the next question?"
            )
            self.current_explanation = explanation_offer
            return (explanation_offer, False)
            
        # CHECK FOR CORRECT ANSWER WITH ENHANCED NLP
        # Increment attempts counter for the current question
        self.current_question_attempts += 1
        
        # Use enhanced NLP to evaluate the answer
        question = self.items[self.i]["question"]
        correct_answer = self.items[self.i]["answer"]
        
        is_correct, confidence, explanation, is_partial = self.check_answer_with_llm(
            usr, correct_answer, question
        )
        
        # HANDLE USER INSISTENCE ON ANSWER BEING CORRECT
        # If user is insisting their answer is correct and we have a close match, be lenient
        if not is_correct and not is_partial and any(phrase in usr_lower for phrase in 
                                            ["told you", "my answer", "that's what", "just said", "already said"]):
            # Check if there's some evidence they might be right
            match_ratio, matched_concepts, _ = self.compare_key_concepts(usr, correct_answer)
            if matched_concepts and match_ratio > 0.3:
                # Override to partial credit if user is insistent and has some matching concepts
                is_partial = True
                log.info(f"Giving partial credit based on user insistence with match ratio {match_ratio}")
        
        # CORRECT ANSWER
        if is_correct:
            self.score += 1
            self.streak += 1
            self.off_topic_counter = 0
            self.current_question_attempts = 0
            self.repeated_explanation_requests = 0
            
            # Celebration based on streak
            celebration = ""
            if self.streak >= 5:
                celebration = " 🔥🔥🔥 Amazing streak! 🔥🔥🔥"
            elif self.streak >= 3:
                celebration = " 🔥 Great streak!"
                
            resp = f"✅ Correct! **{self.items[self.i]['answer']}**.{celebration}\n\n"
            # Advance to next question
            self.i += 1
            
            if self.i >= len(self.items):
                resp += f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}"
                return resp, True
            else:
                resp += self.prompt()
                return resp, False
            
        # PARTIALLY CORRECT ANSWER - using enhanced evaluation
        elif is_partial:
            resp = f"Almost! The correct answer is **{self.items[self.i]['answer']}**.\n\n"
            self.streak = 0
            self.off_topic_counter = 0
            self.current_question_attempts = 0
            self.repeated_explanation_requests = 0
            
            # Advance to next question
            self.i += 1
            
            if self.i >= len(self.items):
                resp += f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}"
                return resp, True
            else:
                resp += self.prompt()
                return resp, False
        
        # Check if response is a genuine answer attempt but incorrect
        if self.is_answer_attempt(usr) and not self.is_dont_know_response(usr):
            # It's a genuine attempt, provide feedback
            if self.current_question_attempts == 1:
                resp = (
                    f"❌ Not quite. Try again, or say 'I don't know' if you'd like the answer. "
                    f"You can also say 'explain' if you'd like more information about this question."
                )
            elif self.current_question_attempts == 2:
                resp = (
                    f"❌ That's not correct. Let me give you a hint: {self.generate_hint()} "
                    f"Try once more, or type 'explain' for more details, or 'idk' to see the answer."
                )
            else:
                resp = (
                    f"❌ Still not correct. Would you like to see the answer? Type 'yes' to see it, "
                    f"or try one more time."
                )
                
            self.streak = 0
            return resp, False
            
        # ——— HANDLE OFF-TOPIC OR NONSENSE RESPONSES ———
        self.off_topic_counter += 1

        # 1) First off-topic: remind them of the question
        if self.off_topic_counter < 2:
            return (
                "That doesn't seem related to the current question. The question is:\n\n"
                f"❓ {self.items[self.i]['question']}\n\n"
                "You can type your answer, say 'I don't know', ask for a 'hint', or type 'exit' to leave the lesson.",
                False
            )

        # 2) Second+ off-topic but they haven't chosen 1/2/3 yet: show the menu
        if usr_lower not in ["1", "2", "3"]:
            return (
                "It seems like you might want to talk about something else. Would you like to:\n\n"
                "1. Exit this lesson\n"
                "2. Continue with the current question\n"
                "3. Skip to the next question\n\n"
                "Just type the number or your choice.",
                False
            )

        # 3) Handle number responses after the menu is shown
        if usr_lower == "1":  # Exit
            return (f"👋 Grammar lesson exited. Final score: {self.score}/{len(self.items)}.", True)

        elif usr_lower == "2":  # Continue
            self.off_topic_counter = 0
            return (f"Let's continue with the current question.\n\n{self.prompt()}", False)

        elif usr_lower == "3":  # Skip
            self.i += 1
            self.off_topic_counter = 0
            self.current_question_attempts = 0

            if self.i >= len(self.items):
                return (
                    f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}",
                    True
                )
            return (f"Moving on to the next question.\n\n{self.prompt()}", False)

        # ——— HANDLE "HAVING TROUBLE" MENU RESPONSES ———
        # First, check if they responded to the having trouble menu
        if self.current_question_attempts >= 3 and usr_lower in ["1", "2", "3"]:
            if usr_lower == "1":
                # Hint
                hint = self.generate_hint()
                return (f"{hint}\n\nWould you like to try answering now?", False)
            elif usr_lower == "2":
                # Show answer and move on
                correct = self.items[self.i]["answer"]
                self.streak = 0
                resp = f"The answer is **{correct}**.\n\n"
                self.i += 1
                if self.i >= len(self.items):
                    resp += f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}"
                    return (resp, True)
                return (resp + self.prompt(), False)
            else:  # usr_lower == "3"
                # Explanation
                self.paused = True
                try:
                    explanation = self.explain()
                    explanation_text = (
                        f"📚 Explanation for '{self.items[self.i]['question']}':\n\n"
                        f"{explanation}\n\n"
                        "Would you like to try answering now, or shall we move on to the next question?"
                    )
                    self.current_explanation = explanation_text
                    return (explanation_text, False)
                except Exception as e:
                    log.error(f"Error in explanation: {e}")
                    return (
                        "I'm having trouble generating a detailed explanation. "
                        "Would you like to skip to the next question?",
                        False
                    )

        # ——— OFFER "HAVING TROUBLE" MENU ———
        if self.current_question_attempts >= 3:
            return (
                "I can see you're having trouble with this question. Would you like to:\n\n"
                "1. Get a hint\n"
                "2. See the answer and move on\n"
                "3. Get an explanation of this concept\n\n"
                "Just type the number of your choice or try again with another answer.",
                False
            )
            
    def get_progress(self) -> Dict:
        """Return the current lesson progress for serialization."""
        return {
            "type": "grammar",
            "index": self.i,
            "score": self.score,
            "streak": self.streak,
            "total_items": len(self.items),
            "current_question": self.items[self.i]["question"] if self.i < len(self.items) else None
        }