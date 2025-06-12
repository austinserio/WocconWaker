import os, json, re, logging, random
from collections import deque
from typing import Dict, List, Tuple, Optional, Any
import ollama  # Assuming this is available

log = logging.getLogger("woccon_assistant")

class LessonManager:
    def __init__(self, words, parent=None, mode="vocab"):
        self.words = words
        self.parent = parent
        self.i = 0
        self.stage = "prompt"
        self.score = 0
        self.streak = 0
        self.mode = "eng_to_woc"  # Start with English to Woccon mode
        self.lesson_type = mode
        self.question_history = []  # Keep track of previous questions
        self.last_response = None   # Store the last response for context
        self.paused = False         # Track if lesson is paused for explanations
        self.current_explanation = None  # Track current explanation if any
        self.exit_attempts = 0      # Track how many times user tried to exit
        self.off_topic_counter = 0  # Track off-topic responses
        self.current_question_attempts = 0  # Track attempts on current question
        self.last_question_index = -1  # Track last question index to detect repetition
        self.repeated_explanation_requests = 0  # Track repeated explanation requests
        
        # Store alternative acceptable answers for common question types
        self.alternative_answers = {}
        
        # Emoji mapping for semantic domains
        self.emoji_map = {
            "water": "💧",
            "natural": "🌿",
            "path": "🛤️",
            "movement": "🚶",
            "container": "🏺",
            "vessel": "🏺",
            "wood": "🪵",
            "cloth": "👕",
            "clothing": "👕",
            "material": "🧵",
            "animal": "🐾",
            "people": "👥",
            "being": "🧍",
            "manufactured": "🏭",
            "phenomena": "🌪️",
            "food": "🍽️",
            "tool": "🔧",
            "unknown": "❓"
        }

    def prompt(self) -> str:
        """Generate the current prompt to show to the user."""
        if self.paused:
            # If we're paused for an explanation, return that instead
            if self.current_explanation:
                return self.current_explanation
            else:
                return "I'm waiting for your question. What would you like me to explain?"
        
        if self.i >= len(self.words):
            return f"🎓 You've completed all the words! Final score: {self.score}"
            
        w = self.words[self.i]
        
        # Check if this is a new question
        if self.last_question_index != self.i:
            self.current_question_attempts = 0
            self.last_question_index = self.i
            
            # Set up alternative answers for this specific question
            self._setup_question_alternatives(w)
        
        # Get emoji for the word if possible
        emoji = "📝"  # Default emoji
        if self.parent and hasattr(self.parent, 'woccon') and hasattr(self.parent.woccon, 'analyze_word_enhanced'):
            try:
                analysis = self.parent.woccon.analyze_word_enhanced(w['woccon'])
                if analysis.get("t5_insights", {}).get("probable_semantic_domain") != "unknown":
                    domain = analysis["t5_insights"]["probable_semantic_domain"]
                    for key, em in self.emoji_map.items():
                        if key in domain:
                            emoji = em
                            break
            except Exception as e:
                # Fallback if any errors occur
                log.error(f"Error getting emoji: {e}")
        
        # Store current question in history
        if self.stage == "prompt":
            if self.mode == "eng_to_woc":
                current_q = f"What's the Woccon word for '{w['english']}'?"
            else:
                current_q = f"What does the Woccon word '{w['woccon']}' mean in English?"
            
            self.question_history.append({
                "index": self.i,
                "question": current_q,
                "answer": w['woccon'] if self.mode == "eng_to_woc" else w['english'],
                "word": w
            })
        
        # Show score and streak information
        score_display = f"🏆 Score: {self.score}"
        if self.streak >= 3:
            score_display += f" | 🔥 Streak: {self.streak}"
            
        # Provide adaptive hints based on attempts
        hint = ""
        if self.current_question_attempts >= 2:
            if self.mode == "eng_to_woc":
                hint = f"\n💡 Hint: The word starts with '{w['woccon'][0]}' and has {len(w['woccon'])} letters."
            else:
                # For English hints, give the first letter and semantic domain if available
                first_letter = w['english'][0]
                domain = "unknown"
                if self.parent and hasattr(self.parent, 'woccon') and hasattr(self.parent.woccon, 'analyze_word_enhanced'):
                    try:
                        analysis = self.parent.woccon.analyze_word_enhanced(w['woccon'])
                        if analysis.get("t5_insights", {}).get("probable_semantic_domain") != "unknown":
                            domain = analysis["t5_insights"]["probable_semantic_domain"]
                    except Exception:
                        pass
                hint = f"\n💡 Hint: The English word starts with '{first_letter}' and relates to {domain}."
        
        if self.stage == "prompt":
            # Alternate between English->Woccon and Woccon->English (Quizlet style)
            if self.mode == "eng_to_woc":
                return (
                    f"{score_display}\n\n"
                    f"{emoji} Word {self.i + 1}/{len(self.words)}\n"
                    f"❓ What's the Woccon word for **{w['english']}**?{hint}\n"
                    "(Type your answer, ask for an explanation, or let me know if you're not sure.)"
                )
            else:  # woc_to_eng mode
                return (
                    f"{score_display}\n\n"
                    f"{emoji} Word {self.i + 1}/{len(self.words)}\n"
                    f"❓ What does the Woccon word **{w['woccon']}** mean in English?{hint}\n"
                    "(Type your answer, ask for an explanation, or let me know if you're not sure.)"
                )
        
        if self.stage == "reinforce":
            if self.mode == "eng_to_woc":
                return (
                    f"{score_display}\n\n"
                    f"✍️ Please type **{w['woccon']}** to reinforce the spelling.\n"
                    "(Or say 'skip' to move on to the next word.)"
                )
            else:  # woc_to_eng mode
                return (
                    f"{score_display}\n\n"
                    f"✍️ Please type **{w['english']}** to reinforce the meaning.\n"
                    "(Or say 'skip' to move on to the next word.)"
                )
        
        return "⚠️ Unexpected stage."

    def handle(self, user_text: str) -> Tuple[str, bool]:
        """Handle user input with natural language understanding."""
        if self.i >= len(self.words):
            return (f"🎓 You've completed all the words! Final score: {self.score}", True)
            
        usr = user_text.strip()
        usr_lower = usr.lower()
        w = self.words[self.i]
        
        # Determine expected answer based on mode
        expected_answer = w['woccon'].lower() if self.mode == "eng_to_woc" else w['english'].lower()
        
        # Determine question format
        current_question = ""
        if self.mode == "eng_to_woc":
            current_question = f"What's the Woccon word for '{w['english']}'?"
        else:
            current_question = f"What does the Woccon word '{w['woccon']}' mean in English?"

        # Store last response
        self.last_response = usr
        
        # HANDLE REPEAT REQUESTS
        if self.is_repeat_request(usr_lower):
            return (f"Sure, the current question is: ❓ {current_question}\n\n(Type your answer, ask for an explanation, or let me know if you're not sure.)", False)
            
        # HANDLE HINT REQUESTS
        if self.is_hint_request(usr_lower):
            hint = self.generate_hint()
            return (f"{hint}\n\nWould you like to try answering now, or do you need more help?", False)
        
        # HANDLE EXIT REQUESTS
        if self.is_exit_request(usr_lower):
            self.exit_attempts += 1
            self.paused = False  # Reset pause state
            
            # If they've tried to exit multiple times, just let them out
            if self.exit_attempts >= 2:
                return (f"👋 Vocabulary lesson exited. Final score: {self.score}. Type 'lesson' to start another.", True)
            else:
                return (
                    f"Would you like to exit the lesson? Your current score is {self.score}. "
                    f"Type 'yes' to confirm exit, or 'continue' to keep going with the lesson.", 
                    False
                )
                
        # Confirm exit if they previously wanted to exit
        if self.exit_attempts > 0 and re.search(r"\b(yes|yeah|yep|yup|correct|right|sure|ok|okay)\b", usr_lower):
            return (f"👋 Vocabulary lesson exited. Final score: {self.score}. Type 'lesson' to start another.", True)
            
        # Reset exit counter if they want to continue
        if self.exit_attempts > 0 and self.is_continue_request(usr_lower):
            self.exit_attempts = 0
            return (f"Great! Let's continue with the lesson.\n\n{self.prompt()}", False)
            
        # HANDLE COMPLETELY DIFFERENT QUESTIONS
        if self.is_different_question_request(usr_lower):
            # If they want to ask something unrelated
            self.paused = True
            self.off_topic_counter += 1
            
            response = (
                "I see you have a different question. I'd be happy to help with that, "
                "but it sounds unrelated to the current vocabulary lesson. Would you like to:"
                "\n\n1. Exit the lesson and ask your question"
                "\n2. Continue with the vocabulary lesson"
                "\n\nJust let me know which you prefer."
            )
            self.current_explanation = response
            return (response, False)
        
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
            if self.parent and hasattr(self.parent, 'woccon'):
                if hasattr(self.parent, '_retrieve') and hasattr(self.parent, '_build_prompt'):
                    try:
                        # Try to answer the specific follow-up question
                        query = f"Question about Woccon word '{w['woccon']}' meaning '{w['english']}': {usr}"
                        retrieved = self.parent._retrieve(query)
                        messages = self.parent._build_prompt(query, retrieved, deque())
                        explanation = ollama.chat(model=self.parent.model, messages=messages)["message"]["content"]
                        
                        self.current_explanation = (
                            f"📚 {explanation}\n\n"
                            "Would you like to know anything else, or shall we continue with the lesson?"
                        )
                        return (self.current_explanation, False)
                    except Exception as e:
                        # Fallback if any errors
                        log.error(f"Error getting explanation: {e}")
                        return (f"I'm sorry, I couldn't get that specific information. Let's continue with the lesson.\n\n{self.prompt()}", False)
            
            # If we can't get an explanation, resume the lesson
            self.paused = False
            self.current_explanation = None
            return (f"Let's continue with the lesson.\n\n{self.prompt()}", False)

        # HANDLE REFERENCES TO PREVIOUS QUESTIONS
        if self.is_previous_question_reference(usr_lower):
            referenced_q = self.get_referenced_question(usr_lower)
            if referenced_q:
                response = (
                    f"📚 That word was: {referenced_q['question']}\n"
                    f"The answer was: **{referenced_q['answer']}**\n\n"
                    "Would you like me to explain more about this word? Otherwise, we'll continue with the current word."
                )
                # Pause the lesson flow to allow follow-up questions
                self.paused = True
                return (response, False)
        
        # HANDLE EXPLANATION REQUESTS
        if self.is_explanation_request(usr_lower):
            if self.parent and hasattr(self.parent, 'woccon'):
                self.paused = True
                self.off_topic_counter = 0
                
                # Try to get word information
                word_info = f"Let me tell you more about **{w['woccon']}** ('{w['english']}').\n\n"
                
                # Add enhanced analysis if available
                if hasattr(self.parent.woccon, 'analyze_word_enhanced'):
                    try:
                        analysis = self.parent.woccon.analyze_word_enhanced(w['woccon'])
                        
                        # Add root information if available
                        if analysis.get("roots") and analysis["roots"][0].get("confidence") != "low":
                            root = analysis["roots"][0]
                            word_info += f"💡 The word '{w['woccon']}' contains the root '{root['root']}' meaning '{root['meaning']}'.\n\n"
                        
                        # Add semantic domain if available
                        if analysis.get("t5_insights", {}).get("probable_semantic_domain") != "unknown":
                            domain = analysis["t5_insights"]["probable_semantic_domain"]
                            word_info += f"🔍 This word belongs to the semantic domain of '{domain}'.\n\n"
                    except Exception as e:
                        log.error(f"Error in word analysis: {e}")
                
                # Try to get context from LLM
                if hasattr(self.parent, '_retrieve') and hasattr(self.parent, '_build_prompt'):
                    try:
                        query = f"Explain the Woccon word '{w['woccon']}' meaning '{w['english']}' with cultural and linguistic context."
                        retrieved = self.parent._retrieve(query)
                        messages = self.parent._build_prompt(query, retrieved, deque())
                        explanation = ollama.chat(model=self.parent.model, messages=messages)["message"]["content"]
                        
                        word_info += f"{explanation}\n\n"
                    except Exception as e:
                        log.error(f"Error getting word context: {e}")
                        word_info += "I don't have additional information about this word in my knowledge base.\n\n"
                
                word_info += "Would you like to know anything else, or shall we continue with the lesson?"
                self.current_explanation = word_info
                return (word_info, False)
            
            # Fallback if parent or woccon not available
            return (f"I'd like to explain more, but I don't have additional information about this word. Let's continue with the lesson.\n\n{self.prompt()}", False)

        # INITIAL PROMPT – EXPECT THE ANSWER
        if self.stage == "prompt":
            # Check if answer is correct (with flexible matching)
            if self._is_correct_answer(usr_lower, expected_answer):
                # Correct answer - increase score and streak
                self.score += 10 + (self.streak * 2)  # Bonus points for streak
                self.streak += 1
                self.off_topic_counter = 0
                
                # Add emoji and celebration based on streak
                celebration = "🎉"
                if self.streak >= 5:
                    celebration = "🔥🔥🔥 AMAZING STREAK! 🔥🔥🔥"
                elif self.streak >= 3:
                    celebration = "🔥🔥 Great streak! 🔥🔥"
                
                # Add a fun fact using T5 if available
                fun_fact = ""
                if self.parent and hasattr(self.parent, 'woccon') and hasattr(self.parent.woccon, 'analyze_word_enhanced'):
                    try:
                        analysis = self.parent.woccon.analyze_word_enhanced(w['woccon'])
                        if analysis.get("roots") and analysis["roots"][0].get("confidence") != "low":
                            root = analysis["roots"][0]
                            fun_fact = f"\n\n💡 Fun fact: '{w['woccon']}' contains the root '{root['root']}' meaning '{root['meaning']}'!"
                    except Exception as e:
                        # Fallback if any errors
                        log.error(f"Error getting fun fact: {e}")
                
                # Toggle the mode for quizlet-like experience
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                
                return self._advance(f"✅ Correct! {celebration} +{10 + (self.streak * 2)} points!{fun_fact}")
            
            elif self.is_dont_know_response(usr):
                # Reset streak on giving up
                self.streak = 0
                self.off_topic_counter = 0
                
                self.stage = "reinforce"
                return (
                    f"No worries! The answer is **{expected_answer}**.\n\n" +
                    self.prompt(),
                    False
                )
            else:
                # Check for close answers
                close_enough = self._is_close_answer(usr_lower, expected_answer)
                
                if close_enough:
                    # Half points for close answers
                    self.score += 5
                    self.streak += 1
                    self.off_topic_counter = 0
                    
                    # Toggle mode
                    self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                    
                    return self._advance(f"✅ Close enough! The exact answer is **{expected_answer}**. +5 points!")
                else:
                    # Reset streak on wrong answer
                    self.streak = 0
                    
                    # Check if the response is completely off-topic
                    similarity = self._string_similarity(usr_lower, expected_answer)
                    
                    if len(usr_lower.split()) > 3 and similarity < 0.3:
                        self.off_topic_counter += 1
                        
                        if self.off_topic_counter >= 2:
                            # If multiple off-topic responses, offer to exit
                            return (
                                "It seems like you might want to talk about something else. Would you like to:\n\n"
                                "1. Exit this lesson\n"
                                "2. Continue with the current word\n"
                                "3. Skip to the next word\n\n"
                                "Just type the number or your choice.",
                                False
                            )
                        else:
                            # Remind them and move to reinforce stage
                            self.stage = "reinforce"
                            return (
                                f"That doesn't seem like an answer to the current question. The correct answer is **{expected_answer}**.\n\n" +
                                self.prompt(),
                                False
                            )
                    else:
                        # Normal wrong answer
                        self.stage = "reinforce"
                        return (
                            f"❌ Not quite. The correct answer is **{expected_answer}**.\n\n" +
                            self.prompt(),
                            False
                        )

        # REINFORCE – LEARNER MUST TYPE THE REVEALED WORD
        if self.stage == "reinforce":
            # Handle number responses for menu options
            if self.off_topic_counter >= 2 and usr_lower in ["1", "2", "3"]:
                if usr_lower == "1":  # Exit
                    return (f"👋 Vocabulary lesson exited. Final score: {self.score}. Type 'lesson' to start another.", True)
                elif usr_lower == "2":  # Continue
                    self.off_topic_counter = 0
                    return (f"Let's continue with the current word.\n\n{self.prompt()}", False)
                elif usr_lower == "3":  # Skip
                    # Toggle mode
                    self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                    self.off_topic_counter = 0
                    return self._advance("Moving on to the next word!")
            
            # Check if they want to skip reinforcement
            if re.search(r"\b(skip|next|continue|move on)\b", usr_lower):
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                self.off_topic_counter = 0
                return self._advance("Moving on to the next word!")
                
            # During reinforcement, we need to be careful not to interpret typing the answer as an exit request
            # Check for exact match with expected answer first
            expected_answer_lower = expected_answer.lower()
            if usr_lower == expected_answer_lower or usr_lower == expected_answer_lower.replace(",", ""):
                # They typed the exact answer - advance to next word
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                self.off_topic_counter = 0
                return self._advance("✅ Great! On to the next one 👏")
                
            # More lenient matching for reinforcement stage
            if self._is_close_answer(usr_lower, expected_answer, threshold=0.6):
                # Toggle mode
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                self.off_topic_counter = 0
                return self._advance("✅ Great! On to the next one 👏")
            
            # Only check for exit request if it's not similar to the expected answer
            if self.is_exit_request(usr_lower) and self._string_similarity(usr_lower, expected_answer_lower) < 0.5:
                self.exit_attempts += 1
                
                # If they've tried to exit multiple times, just let them out
                if self.exit_attempts >= 2:
                    return (f"👋 Vocabulary lesson exited. Final score: {self.score}. Type 'lesson' to start another.", True)
                else:
                    return (
                        f"Would you like to exit the lesson? Your current score is {self.score}. "
                        f"Type 'yes' to confirm exit, or 'continue' to keep going with the lesson.", 
                        False
                    )
                
            return ("❌ Try typing it again, or say 'skip' to move on to the next word:", False)
            
    def _is_correct_answer(self, user_answer: str, expected_answer: str) -> bool:
        """Check if the user's answer is correct with natural language flexibility."""
        # Exact match
        if user_answer == expected_answer:
            return True
            
        # For English answers (woc_to_eng mode), be more flexible
        if expected_answer in user_answer or user_answer in expected_answer:
            # One is contained within the other
            return True
            
        # Check for close match using character similarity
        return self._string_similarity(user_answer, expected_answer) > 0.8

    def _is_close_answer(self, user_answer: str, expected_answer: str, threshold: float = 0.7) -> bool:
        """Check if the user's answer is close enough."""
        # For English answers (woc_to_eng mode), be very flexible
        if "to" in expected_answer and "woc" not in expected_answer:
            # Check if key words match
            user_words = set(user_answer.split())
            expected_words = set(expected_answer.split())
            common_words = user_words.intersection(expected_words)
            
            # If at least half the expected words are present, consider it close
            if len(common_words) >= len(expected_words) / 2:
                return True
        
        # Check for string similarity
        return self._string_similarity(user_answer, expected_answer) > threshold


    def _setup_question_alternatives(self, word_entry: Dict):
        """Set up alternative acceptable answers for a specific question."""
        self.alternative_answers = {}
        
        if self.mode == "eng_to_woc":
            # For Woccon words, mainly handle typos and variations
            woccon_word = word_entry.get('woccon', '')
            
            # Handle common typos or variations
            if len(woccon_word) > 2:
                # First letter wrong but rest correct
                self.alternative_answers[woccon_word[1:]] = woccon_word
                
                # Last letter wrong but rest correct
                self.alternative_answers[woccon_word[:-1]] = woccon_word
                
                # Missing a letter
                for i in range(len(woccon_word)):
                    self.alternative_answers[woccon_word[:i] + woccon_word[i+1:]] = woccon_word
        else:
            # For English translations, accept synonyms and related words
            english_word = word_entry.get('english', '').lower()
            
            # Simple synonym patterns based on common words
            if "water" in english_word:
                self.alternative_answers.update({
                    "liquid": english_word,
                    "fluid": english_word,
                    "aqua": english_word,
                    "h2o": english_word
                })
            elif "path" in english_word:
                self.alternative_answers.update({
                    "trail": english_word,
                    "route": english_word,
                    "way": english_word,
                    "road": english_word,
                    "track": english_word
                })
            elif "container" in english_word:
                self.alternative_answers.update({
                    "vessel": english_word,
                    "holder": english_word,
                    "receptacle": english_word,
                    "pot": english_word
                })
            elif "tool" in english_word:
                self.alternative_answers.update({
                    "implement": english_word,
                    "utensil": english_word,
                    "instrument": english_word,
                    "device": english_word
                })
                
            # Add plural/singular variations
            if english_word.endswith("s") and len(english_word) > 2:
                self.alternative_answers[english_word[:-1]] = english_word
            else:
                self.alternative_answers[english_word + "s"] = english_word
                
            # Add common variants with adjectives
            self.alternative_answers["the " + english_word] = english_word
            self.alternative_answers["a " + english_word] = english_word
            self.alternative_answers["an " + english_word] = english_word
            
            # Add "to X" for verbs
            self.alternative_answers["to " + english_word] = english_word

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
            Analyze this user message in the context of a vocabulary lesson to determine if they want to exit/leave the lesson.

            USER MESSAGE: "{text}"
            CONTEXT: The user is currently in the middle of a vocabulary learning lesson.

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
                Analyze this user message in the context of a vocabulary lesson to determine their intent.

                USER MESSAGE: "{text}"
                CONTEXT: The user is currently in a vocabulary learning lesson and just encountered a question.

                Determine if the user wants:
                - EXPLANATION (they want more information about the current word/concept)
                - HELP (they want assistance with the current question)
                - OTHER (they're asking something unrelated or just answering)

                Examples:
                - "explain this word" = EXPLANATION
                - "Uhhhhhhhhhhhhh got a suggestion?" = HELP
                - "help me" = HELP
                - "what does this mean?" = EXPLANATION
                - "I don't know what this is" = HELP
                - "can you tell me more?" = EXPLANATION
                - "yakau" = OTHER (just an answer)

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
            r"\b(what was the|go back|can we revisit|word \d+)\b",
            r"\b(earlier word|prior word|first word)\b",
            r"\b(word (one|two|three|four|five|six|seven|eight|nine|ten))\b",
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
                Analyze this user message in a vocabulary lesson context.

                USER MESSAGE: "{text}"
                CONTEXT: User is answering a vocabulary question and seems to need assistance.

                Is this a request for a HINT/HELP with the current question?

                Examples:
                - "Uhhhhhhhhhhhhh got a suggestion?" = YES (asking for help)
                - "help me" = YES
                - "I'm stuck" = YES  
                - "what should I do?" = YES
                - "yakau" = NO (just an answer)
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
            
        # If it contains answer-like phrases, it's likely an answer attempt
        answer_indicators = [
            r"it'?s\s",
            r"that'?s\s",
            r"they'?re\s",
            r"i\s*think\s*it'?s\s",
            r"maybe\s*it'?s\s",
            r"probably\s",
            r"\b(means|translates to|is|are|would be)\b",
            r"the\s*answer\s*is\s",
        ]
        
        # Extract the expected answer based on current mode
        if self.i < len(self.words):
            w = self.words[self.i]
            expected_answer = w['woccon'].lower() if self.mode == "eng_to_woc" else w['english'].lower()
            
            # If the text contains any part of the correct answer, it's likely an answer attempt
            for word in expected_answer.split():
                if len(word) > 3 and word in text_lower:  # Only consider words longer than 3 chars
                    return True
                    
        # If the text contains any answer indicator, it's likely an answer attempt
        if any(re.search(pattern, text_lower) for pattern in answer_indicators):
            return True
            
        # If text is very short (1-2 words), it's likely an answer attempt in this context
        if len(text_lower.split()) <= 3 and len(text_lower) > 1:
            return True
            
        return False

    def is_repeat_request(self, text: str) -> bool:
        """Check if user is asking to repeat the question."""
        text = text.lower()
        repeat_patterns = [
            r"\b(repeat|say again|once more|what was the question)\b",
            r"\b(didn't catch that|didn't hear|what did you say|what was that)\b",
            r"\b(remind me|tell me again|one more time|read it again)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in repeat_patterns)

    def generate_hint(self) -> str:
        """Generate a hint for the current question."""
        if self.i >= len(self.words):
            return "There are no more words to hint about."
            
        w = self.words[self.i]
        
        if self.mode == "eng_to_woc":
            # Hint for Woccon word
            woccon_word = w['woccon']
            if len(woccon_word) > 3:
                return f"💡 The Woccon word starts with '{woccon_word[:2]}' and has {len(woccon_word)} letters."
            else:
                return f"💡 The Woccon word has {len(woccon_word)} letters."
        else:
            # Hint for English meaning
            english_word = w['english']
            
            # Try to get semantic domain if available
            domain = "unknown"
            if self.parent and hasattr(self.parent, 'woccon') and hasattr(self.parent.woccon, 'analyze_word_enhanced'):
                try:
                    analysis = self.parent.woccon.analyze_word_enhanced(w['woccon'])
                    if analysis.get("t5_insights", {}).get("probable_semantic_domain") != "unknown":
                        domain = analysis["t5_insights"]["probable_semantic_domain"]
                except Exception:
                    pass
            
            if domain != "unknown":
                return f"💡 The English word relates to {domain} and starts with '{english_word[0]}'."
            else:
                return f"💡 The English word starts with '{english_word[0]}' and has {len(english_word)} letters."

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



    def _advance(self, message: str) -> Tuple[str, bool]:
        """Advance to the next word in the lesson."""
        self.i += 1
        self.stage = "prompt"
        
        if self.i >= len(self.words):
            # Lesson completed - add final score and encouragement
            final_message = f"{message}\n\n🎓 Great job! You've completed the lesson!"
            
            # Add different celebratory message based on score
            if self.score >= 50:
                final_message += f"\n\n🏆 Final score: {self.score} - Amazing work! You're a Woccon master!"
            elif self.score >= 30:
                final_message += f"\n\n🏆 Final score: {self.score} - Well done! You're getting very good at Woccon!"
            else:
                final_message += f"\n\n🏆 Final score: {self.score} - Good start! Keep practicing!"
            
            return (final_message, True)
        
        return (message + "\n\n" + self.prompt(), False)

    def get_referenced_question(self, text: str) -> Optional[Dict]:
        """Try to determine which previous question the user is referring to."""
        text = text.lower()
        
        # Check for numeric references
        number_match = re.search(r"word (\d+)", text)
        if number_match:
            q_num = int(number_match.group(1))
            if 0 < q_num <= len(self.question_history):
                return self.question_history[q_num - 1]
        
        # Check for "previous" or "last" references
        if re.search(r"\b(previous|last|before)\b", text):
            if len(self.question_history) > 1:
                return self.question_history[-2]  # Return the question before the current one
        
        # Check for "X questions ago"
        ago_match = re.search(r"(\d+) words? ago", text)
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
            if re.search(fr"word {word}", text):
                if 0 < num <= len(self.question_history):
                    return self.question_history[num - 1]
                
        # Default to the most recent question if we can't determine
        if self.question_history:
            return self.question_history[-1]
            
        return None

    def extract_key_concepts(self, text: str) -> List[str]:
        """Extract key concepts from an answer to compare against user input."""
        text = text.lower()
        
        # Split the text into words and remove common stopwords
        stopwords = ['the', 'a', 'an', 'is', 'are', 'that', 'this', 'to', 'in', 'of', 'for', 'with', 'on', 'at']
        words = [word for word in re.findall(r'\b\w+\b', text) if word not in stopwords and len(word) > 2]
        
        # Extract quoted words
        quoted = re.findall(r'"([^"]+)"|\*\*([^*]+)\*\*|\'([^\']+)\'', text)
        quoted_words = []
        for match in quoted:
            # Combine all capturing groups and take non-empty ones
            for group in match:
                if group:
                    quoted_words.append(group.lower())
        
        # Combine all key concepts and remove duplicates
        return list(set(words + quoted_words))
        
    def compare_key_concepts(self, user_answer: str, correct_answer: str) -> Tuple[float, List[str], List[str]]:
        """
        Compare key concepts between user answer and correct answer.
        Returns: (match_ratio, matched_concepts, missing_concepts)
        """
        # Quick check for non-answers
        non_answer_markers = ['errr', 'umm', 'idk', 'wtf', 'lmao', 'lol', 'clue']
        if any(marker in user_answer.lower() for marker in non_answer_markers) and len(user_answer.split()) <= 2:
            # This is almost certainly not a real answer attempt
            return 0.0, [], self.extract_key_concepts(correct_answer.lower())
            
        # Extract key concepts from both answers
        user_concepts = self.extract_key_concepts(user_answer.lower())
        correct_concepts = self.extract_key_concepts(correct_answer.lower())
        
        # Find matched and missing concepts
        matched_concepts = [c for c in user_concepts if c in correct_concepts or any(self._string_similarity(c, cc) > 0.8 for cc in correct_concepts)]
        missing_concepts = [c for c in correct_concepts if c not in user_concepts and not any(self._string_similarity(c, uc) > 0.8 for uc in user_concepts)]
        
        # Calculate match ratio
        if not correct_concepts:
            return 1.0, matched_concepts, missing_concepts  # Avoid division by zero
            
        match_ratio = len(matched_concepts) / len(correct_concepts)
        
        return match_ratio, matched_concepts, missing_concepts
    
    def generate_hint(self) -> str:
        """Generate a hint for the current question."""
        if self.i >= len(self.words):
            return "There are no more words to hint about."
            
        w = self.words[self.i]
        
        if self.mode == "eng_to_woc":
            # Hint for Woccon word
            woccon_word = w['woccon']
            if len(woccon_word) > 3:
                return f"💡 The Woccon word starts with '{woccon_word[:2]}' and has {len(woccon_word)} letters."
            else:
                return f"💡 The Woccon word has {len(woccon_word)} letters."
        else:
            # Hint for English meaning
            english_word = w['english']
            
            # Try to get semantic domain if available
            domain = "unknown"
            if self.parent and hasattr(self.parent, 'woccon') and hasattr(self.parent.woccon, 'analyze_word_enhanced'):
                try:
                    analysis = self.parent.woccon.analyze_word_enhanced(w['woccon'])
                    if analysis.get("t5_insights", {}).get("probable_semantic_domain") != "unknown":
                        domain = analysis["t5_insights"]["probable_semantic_domain"]
                except Exception:
                    pass
            
            if domain != "unknown":
                return f"💡 The English word relates to {domain} and starts with '{english_word[0]}'."
            else:
                return f"💡 The English word starts with '{english_word[0]}' and has {len(english_word)} letters."
            
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
        
    def _normalize_answer(self, text: str) -> str:
        """Normalize text for better comparison."""
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation and extra spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove common filler words for comparing answers
        fillers = ['the', 'a', 'an', 'is', 'are', 'that', 'this', 'these', 'those', 'to']
        for filler in fillers:
            text = re.sub(fr'\b{filler}\b', '', text)
        
        return re.sub(r'\s+', ' ', text).strip()
    


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
                                      'uhh', 'ugh', 'wtf', 'idk', 'omg']
            ):
                # This is almost certainly not an attempt at answering
                return False, 0.1, "Response contains expressions of uncertainty", False
            
            # If we have a very strong match based on key concepts, don't bother calling the LLM
            if match_ratio > 0.9 and len(matched_concepts) >= 1:
                return True, 0.95, "Answer contains all key concepts", False
                
            # For very short answers (likely Woccon words), use direct string similarity
            if len(user_answer.split()) <= 2 and len(correct_answer.split()) <= 2:
                similarity = self._string_similarity(user_answer.lower(), correct_answer.lower())
                if similarity > 0.85:
                    return True, similarity, "Close string match", False
                elif similarity > 0.65:
                    return False, similarity, "Partial string match", True
                else:
                    return False, similarity, "Low string similarity", False
            
            # Prepare a conversational evaluation prompt
            prompt = f"""
            Evaluate if this user's answer for a language learning exercise is correct.
            
            QUESTION: {question}
            CORRECT ANSWER: {correct_answer}
            USER'S ANSWER: {user_answer}
            
            Additional context: The user is learning vocabulary for a constructed language called Woccon.
            This is an informal learning context, so be forgiving of partial answers if they show understanding.
            
            TASK: Determine if the user's answer is:
            1. Correct - Contains the key concepts, even if expressed informally or with minor spelling errors
            2. Partially correct - Has some correct elements but is missing important information
            3. Incorrect - Wrong or completely off-topic
            
            Key considerations:
            - Accept informal language and synonyms (e.g., "vessel" for "container")
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
            # Fall back to string similarity if LLM call fails completely
            
            # For very short answers (likely Woccon words), use string similarity
            if len(user_answer.split()) <= 2 and len(correct_answer.split()) <= 2:
                similarity = self._string_similarity(user_answer.lower(), correct_answer.lower())
                if similarity > 0.85:
                    return True, similarity, "Close string match", False
                elif similarity > 0.65:
                    return False, similarity, "Partial string match", True
                else:
                    return False, similarity, "Low string similarity", False
            
            # For longer answers, use key concept matching
            if match_ratio > 0.85:
                return True, match_ratio, f"Contains key concepts: {', '.join(matched_concepts)}", False
            elif match_ratio > 0.5:
                return False, match_ratio, f"Missing key concepts: {', '.join(missing_concepts)}", True
            else:
                return False, match_ratio, "Answer lacks required key concepts", False