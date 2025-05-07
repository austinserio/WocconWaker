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
        
        return (
            f"🏷️ Grammar Q {progress} | 🏆 Score: {self.score}{streak_bonus}\n"
            f"❓ {itm['question']}\n"
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
        """Check if user is asking for an explanation."""
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
            r"\b(what was the|go back|can we revisit|question \d+)\b",
        ]
        
        return any(re.search(pattern, text) for pattern in prev_patterns)
    
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
                
        # Default to the most recent question if we can't determine
        if self.question_history:
            return self.question_history[-1]
            
        return None
        
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

    def handle(self, user_text: str) -> Tuple[str, bool]:
        """Handle user input with natural language understanding."""
        if self.i >= len(self.items):
            return (f"🎓 You've finished all the questions! Final score: {self.score}/{len(self.items)}", True)
            
        usr = user_text.strip()
        usr_lower = usr.lower()
        
        # Store last response
        self.last_response = usr
        
        # HANDLE EXIT REQUESTS - Enhanced with more patterns
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
            
            response = (
                "I see you have a different question. I'd be happy to help with that, "
                "but it sounds unrelated to the current grammar lesson. Would you like to:"
                "\n\n1. Exit the lesson and ask your question"
                "\n2. Continue with the grammar lesson"
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
            try:
                explanation = self.explain()
                
                explanation_text = (
                    f"📚 Explanation for question: '{self.items[self.i]['question']}'\n\n"
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
            
        # CHECK FOR CORRECT ANSWER WITH FUZZY MATCHING
        correct = self.items[self.i]["answer"].lower()
        similarity = self._string_similarity(usr_lower, correct)
        
        if similarity > 0.8 or usr_lower == correct:  # Exact match or very close
            self.score += 1
            self.streak += 1
            self.off_topic_counter = 0
            
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
                
        elif similarity > 0.6:  # Close but not quite right
            resp = f"Almost! The correct answer is **{self.items[self.i]['answer']}**.\n\n"
            self.streak = 0
            self.off_topic_counter = 0
            
            # Advance to next question
            self.i += 1
            
            if self.i >= len(self.items):
                resp += f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}"
                return resp, True
            else:
                resp += self.prompt()
                return resp, False
        
        # Detect completely off-topic responses that aren't exit requests        
        if len(usr_lower.split()) > 3 and similarity < 0.3:
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
                    f"You can type your answer, say 'I don't know', or type 'exit' to leave the lesson.",
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
                if self.i >= len(self.items):
                    return (f"🎓 You've finished your grammar lesson! Final score: {self.score}/{len(self.items)}", True)
                else:
                    return (f"Moving on to the next question.\n\n{self.prompt()}", False)
        
        # Default case - not correct
        resp = (
            f"❌ Not quite. Try again, or say 'I don't know' if you'd like the answer. "
            f"You can also say 'explain' if you'd like more information about this question."
        )
        self.streak = 0
        return resp, False
            
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