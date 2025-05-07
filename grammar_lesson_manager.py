import random
from typing import List, Dict, Tuple, Optional, Any
from collections import deque
import re
import ollama
import logging

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

    def is_dont_know_response(self, text: str) -> bool:
        """Check if user response indicates they don't know using natural language understanding."""
        text = text.lower()
        dont_know_patterns = [
            r"\b(i don't know|idk|not sure|no idea|no clue|uncertain|don't remember|forgot|unsure)\b",
            r"\b(can'?t remember|don'?t have a guess|skip|pass|next)\b",
            r"\b(what is it|what'?s the answer|tell me|reveal|show me)\b",
            r"\?(don'?t know|\?)",  # Question marks often indicate uncertainty
            r"\b(um|uh|hmm|err)\b",  # Hesitation markers
            r"\b(lol|haha)\b",  # Laughter often indicates uncertainty in this context
            r"\b(whatever|dunno|who knows|doesn't matter|don't care)\b",  # Dismissive responses
            r"\b(no idea|haven'?t a clue|give up|stumped)\b",  # Additional expressions
            r"\b(beats me|beyond me|drawing a blank|lost|clueless)\b",  # More expressions
        ]
        
        return any(re.search(pattern, text) for pattern in dont_know_patterns)

    def is_exit_request(self, text: str) -> bool:
        """Check if user is trying to exit the lesson."""
        text = text.lower()
        exit_patterns = [
            r"\b(exit|quit|stop|end|leave|cancel)\b",
            r"\b(i'm done|that's enough|let's stop|finish|terminate)\b",
            r"\b(get me out|out of here|enough of this|let me out)\b",
            r"\b(nah |gimme out|gemme out|let's quit|want to quit)\b",
            r"\b(go back|return|main menu|different topic)\b",
            r"\b(not interested|don't want|no longer|anymore)\b",
            r"\b(tired of this|bored|change the topic|something else)\b",
            r"\b(stop the lesson|done with grammar|i give up|too hard)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in exit_patterns)

    def is_explanation_request(self, text: str) -> bool:
        """Check if user is asking for an explanation."""
        text = text.lower()
        explain_patterns = [
            r"\b(explain|explanation|more info|tell me more|elaborate|details|why)\b",
            r"\b(how does|what does|can you explain|meaning of|what is|what are)\b",
            r"\b(curious about|background|context|help me understand)\b",
            r"\b(could you explain|would you explain|please explain)\b",
            r"\b(tell me about|what's the reason|don't understand|confused)\b",
            r"\b(need help|how come|how so|give me a hint|confused)\b",
            r"\b(why is that|what's this about|enlighten me|educate me)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in explain_patterns)
        
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
        """Check if user is asking for a hint."""
        text = text.lower()
        hint_patterns = [
            r"\b(hint|clue|tip|help me out)\b",
            r"\b(give me a hint|need a clue|any hints|can you help)\b",
            r"\b(stuck|struggling|help with this|how do i)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in hint_patterns)
    
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
            r'\b(mode|marker|prefix|suffix|reduplication|possession|root|inflection)\b',
            r'\b(narrative|independent|imperative|subjunctive)\b',
            r'\b(intensity|frequency|iterative|continuous|progressive)\b',
            r'\b(meaning|cloth|hide|material|water|path|way|container|wood|tree)\b'
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

    def check_answer_with_llm(self, user_answer: str, correct_answer: str, question: str) -> Tuple[bool, float, str]:
        """
        Use the LLM to evaluate if the user's answer is correct or close
        Returns: (is_correct, confidence_score, explanation)
        """
        try:
            # Prepare the evaluation prompt
            prompt = f"""
            Evaluate if this user's answer is correct for a Woccon language grammar lesson.
            
            QUESTION: {question}
            CORRECT ANSWER: {correct_answer}
            USER'S ANSWER: {user_answer}
            
            TASK: Determine if the user's answer is:
            1. Correct (the answer contains the key information needed)
            2. Partially correct (has some correct elements but is missing information)
            3. Incorrect (answer is wrong or completely off-topic)
            
            First, identify the key concepts required in the correct answer.
            Then, check if the user's answer includes these key concepts.
            
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
            import json
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
                
                return is_correct, confidence, explanation, is_partial
            
            except (json.JSONDecodeError, ValueError) as e:
                log.error(f"Error parsing LLM response: {e} - Response: {response}")
                # Fall back to string similarity if JSON parsing fails
                similarity = self._string_similarity(self._normalize_answer(user_answer), 
                                                   self._normalize_answer(correct_answer))
                return similarity > 0.85, similarity, "Unable to parse detailed evaluation", similarity > 0.7
                
        except Exception as e:
            log.error(f"Error in LLM answer check: {e}")
            # Fall back to string similarity if LLM call fails
            similarity = self._string_similarity(self._normalize_answer(user_answer), 
                                               self._normalize_answer(correct_answer))
            return similarity > 0.85, similarity, "Unable to get detailed evaluation", similarity > 0.7

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
            
        # Increment attempts counter for the current question
        self.current_question_attempts += 1
        
        # Use LLM to evaluate the answer
        question = self.items[self.i]["question"]
        correct_answer = self.items[self.i]["answer"]
        
        is_correct, confidence, explanation, is_partial = self.check_answer_with_llm(
            usr, correct_answer, question
        )
        
        # Fallback to traditional similarity check if LLM confidence is low
        if confidence < 0.4:
            # Get normalized answers for comparison
            correct_norm = self._normalize_answer(self.items[self.i]["answer"])
            usr_normalized = self._normalize_answer(usr)
            
            # Fallback similarity checks
            exact_match = usr_normalized == correct_norm
            word_match = all(word in usr_normalized for word in correct_norm.split())
            high_similarity = self._string_similarity(usr_normalized, correct_norm) > 0.85
            partial_similarity = self._string_similarity(usr_normalized, correct_norm) > 0.7
            
            is_correct = exact_match or high_similarity
            is_partial = is_partial or word_match or partial_similarity
        
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
                
            resp = f"✅ Correct! **{correct_answer}**.{celebration}\n\n"
            # Advance to next question
            self.i += 1
            
            if self.i >= len(self.items):
                resp += f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}"
                return resp, True
            else:
                resp += self.prompt()
                return resp, False
        
        # PARTIALLY CORRECT ANSWER
        elif is_partial:
            resp = f"Almost! The correct answer is **{correct_answer}**.\n\n"
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
        
        # Check if the response seems completely off-topic 
        # We'll use a combination of our existing method and the LLM's assessment
        if confidence < 0.2 or (len(usr_lower.split()) > 3 and self._string_similarity(self._normalize_answer(usr), self._normalize_answer(correct_answer)) < 0.3):
            self.off_topic_counter += 1
            
            if self.off_topic_counter >= 2:
                # If multiple off-topic responses, offer to exit
                return (
                    "It seems like you might want to talk about something else. Would you like to:\n\n"
                    "1. Exit this lesson\n"
                    "2. Continue with the current question\n"
                    "3. Skip to the next question\n\n"
                    "Just type the number or your choice.",
                    False
                )
            else:
                # First off-topic response - just remind them
                return (
                    f"That doesn't seem related to the current question. The question is:\n\n"
                    f"❓ {self.items[self.i]['question']}\n\n"
                    f"You can type your answer, say 'I don't know', ask for a 'hint', or type 'exit' to leave the lesson.",
                    False
                )
                
        # Handle number responses for menu options
        if self.off_topic_counter >= 2 and usr_lower in ["1", "2", "3"]:
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
                    return (f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}", True)
                else:
                    return (f"Moving on to the next question.\n\n{self.prompt()}", False)
        
        # If we've had multiple attempts, offer more help
        if self.current_question_attempts >= 3:
            return (
                f"I can see you're having trouble with this question. Would you like to:\n\n"
                f"1. Get a hint\n"
                f"2. See the answer and move on\n"
                f"3. Get an explanation of this concept\n\n"
                f"Just type the number of your choice or try again with another answer.",
                False
            )
        
        # Handle responses to the "having trouble" menu
        if usr_lower == "1" and self.current_question_attempts >= 3:  # Hint
            hint = self.generate_hint()
            return (f"{hint}\n\nWould you like to try answering now?", False)
        elif usr_lower == "2" and self.current_question_attempts >= 3:  # See answer
            self.streak = 0
            resp = f"The answer is **{correct_answer}**.\n\n"
            self
            
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