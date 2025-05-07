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
        score_display = f"🏆 Score: {self.score} | 🔥 Streak: {self.streak}"
        
        if self.stage == "prompt":
            # Alternate between English->Woccon and Woccon->English (Quizlet style)
            if self.mode == "eng_to_woc":
                return (
                    f"{score_display}\n\n"
                    f"{emoji} Word {self.i + 1}/{len(self.words)}\n"
                    f"❓ What's the Woccon word for **{w['english']}**?\n"
                    "(Type your answer, ask for an explanation, or let me know if you're not sure.)"
                )
            else:  # woc_to_eng mode
                return (
                    f"{score_display}\n\n"
                    f"{emoji} Word {self.i + 1}/{len(self.words)}\n"
                    f"❓ What does the Woccon word **{w['woccon']}** mean in English?\n"
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

    def is_dont_know_response(self, text: str) -> bool:
        """Check if user response indicates they don't know the answer using natural language understanding."""
        text = text.lower()
        dont_know_patterns = [
            r"\b(i don't know|idk|not sure|no idea|no clue|uncertain|don't remember|forgot|unsure)\b",
            r"\b(can'?t remember|don'?t have a guess|skip|pass|next)\b",
            r"\b(what is it|what'?s the answer|tell me|reveal|show me)\b",
            r"\?(don'?t know|\?)",  # Question marks often indicate uncertainty
            r"\b(um|uh|hmm|err)\b",  # Hesitation markers
            r"\b(lol|haha)\b",  # Laughter often indicates uncertainty in this context
            r"\b(whatever|dunno|who knows|doesn't matter|don't care)\b",  # Dismissive responses
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
        ]
        
        return any(re.search(pattern, text) for pattern in exit_patterns)

    def is_explanation_request(self, text: str) -> bool:
        """Check if user is asking for an explanation about the current word/question."""
        text = text.lower()
        explain_patterns = [
            r"\b(explain|explanation|more info|tell me more|elaborate|details|why)\b",
            r"\b(how does|what does|can you explain|meaning of|what is|what are)\b",
            r"\b(curious about|background|context|help me understand)\b",
            r"\b(could you explain|would you explain|please explain)\b",
            r"\b(tell me about|what's the reason|don't understand|confused)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in explain_patterns)
    
    def is_continue_request(self, text: str) -> bool:
        """Check if user wants to continue with the lesson."""
        text = text.lower()
        continue_patterns = [
            r"\b(continue|resume|go on|next|proceed|keep going)\b",
            r"\b(let's continue|move on|move forward|next question)\b",
            r"\b(back to lesson|back to questions|go ahead)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in continue_patterns)

    def is_different_question_request(self, text: str) -> bool:
        """Check if user wants to ask a different question entirely."""
        text = text.lower()
        different_q_patterns = [
            r"\b(different question|another question|ask you something|something else)\b",
            r"\b(i have a |can i ask|wondering about|curious about)\b",
            r"\b(actually,|instead,|rather|unrelated)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in different_q_patterns)
    
    def is_previous_question_reference(self, text: str) -> bool:
        """Check if user is referring to a previous question."""
        text = text.lower()
        prev_patterns = [
            r"\b(previous|earlier|before|last|ago|that other|remember when|back to)\b",
            r"\b(what was the|go back|can we revisit|word \d+)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in prev_patterns)
    
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
                
        # Default to the most recent question if we can't determine
        if self.question_history:
            return self.question_history[-1]
            
        return None
        
    def handle(self, user_text: str) -> Tuple[str, bool]:
        """Handle user input with natural language understanding."""
        if self.i >= len(self.words):
            return (f"🎓 You've completed all the words! Final score: {self.score}", True)
            
        usr = user_text.strip()
        usr_lower = usr.lower()
        w = self.words[self.i]
        
        # Determine expected answer based on mode
        expected_answer = w['woccon'].lower() if self.mode == "eng_to_woc" else w['english'].lower()

        # Store last response
        self.last_response = usr
        
        # HANDLE EXIT REQUESTS - Enhanced with more patterns
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
            
            # More lenient matching for reinforcement stage
            if self._is_close_answer(usr_lower, expected_answer, threshold=0.6):
                # Toggle mode
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                self.off_topic_counter = 0
                
                return self._advance("✅ Great! On to the next one 👏")
                
            # Check if they want to skip reinforcement
            if re.search(r"\b(skip|next|continue|move on)\b", usr_lower):
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                self.off_topic_counter = 0
                return self._advance("Moving on to the next word!")
                
            return ("❌ Try typing it again, or say 'skip' to move on to the next word:", False)

        return ("⚠️ Something went wrong.", True)
    
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

    def get_progress(self) -> Dict:
        """Return the current lesson progress for serialization."""
        return {
            "type": self.lesson_type,
            "index": self.i,
            "score": self.score,
            "streak": self.streak,
            "stage": self.stage,
            "mode": self.mode,
            "total_words": len(self.words),
            "words": self.words
        }
    

    def _add_linguistic_context(self, word_entry: Dict) -> str:
        """Add linguistic context to a word based on morphological analysis"""
        word = word_entry['woccon']
        
        # Get analysis if parent exists and has woccon attribute
        analysis = {}
        if self.parent and hasattr(self.parent, 'woccon'):
            try:
                analysis = self.parent.woccon.analyze_word(word)
            except Exception as e:
                log.error(f"Error analyzing word {word}: {e}")
        
        context = []
        
        # Add root information
        if analysis.get("roots"):
            for root in analysis["roots"]:
                if root.get("confidence") not in ["low"]:
                    context.append(f"• Contains the root **{root['root']}** meaning '{root['meaning']}'")
                    break
        
        # Add affix information
        if analysis.get("affixes"):
            for affix in analysis["affixes"]:
                context.append(f"• Contains the {affix['type']} **{affix['form']}** ({affix['function']})")
        
        # Add reduplication information
        reduplication = self.parent.woccon._detect_reduplication(word) if hasattr(self.parent.woccon, '_detect_reduplication') else None
        if reduplication:
            context.append(f"• Shows {reduplication['type']} pattern indicating {reduplication['pattern']}")
        
        # Add inflectional mode information if relevant
        infl_mode = self.parent.woccon._identify_inflectional_mode(word) if hasattr(self.parent.woccon, '_identify_inflectional_mode') else None
        if infl_mode and infl_mode['mode'] != 'unknown':
            context.append(f"• Uses the {infl_mode['mode']} mode marked by {infl_mode['marker']}")
        
        if not context:
            context.append("• No additional morphological information available")
        
        return "\n".join(context)