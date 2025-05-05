import os, json, re, logging, random
from collections import deque
from typing import Dict, List, Tuple

import ollama  # local Llama server
from main import WocconT5  # your rule-based analyser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_assistant")


class LessonManager:
    def __init__(self, words, parent=None):
        self.words = words
        self.parent = parent  # Add this line to store parent reference
        self.i = 0
        self.stage = "prompt"
        self.score = 0  # Track score for gamification
        self.streak = 0  # Track correct answer streak
        self.mode = "eng_to_woc"  # Start with English to Woccon mode
        
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
            except Exception:
                # Fallback if any errors occur
                pass
        
        # Show score and streak information
        score_display = f"🏆 Score: {self.score} | 🔥 Streak: {self.streak}"
        
        if self.stage == "prompt":
            # Alternate between English->Woccon and Woccon->English (Quizlet style)
            if self.mode == "eng_to_woc":
                return (
                    f"{score_display}\n\n"
                    f"{emoji} Word {self.i + 1}/{len(self.words)}\n"
                    f"❓ What's the Woccon word for **{w['english']}**?\n"
                    "(Type it, or 'I don't know' to reveal.)"
                )
            else:  # woc_to_eng mode
                return (
                    f"{score_display}\n\n"
                    f"{emoji} Word {self.i + 1}/{len(self.words)}\n"
                    f"❓ What does the Woccon word **{w['woccon']}** mean in English?\n"
                    "(Type it, or 'I don't know' to reveal.)"
                )
        
        if self.stage == "reinforce":
            if self.mode == "eng_to_woc":
                return (
                    f"{score_display}\n\n"
                    f"✍️ Please type **{w['woccon']}** again to reinforce the spelling:"
                )
            else:  # woc_to_eng mode
                return (
                    f"{score_display}\n\n"
                    f"✍️ Please type **{w['english']}** again to reinforce the meaning:"
                )
        
        return "⚠️ Unexpected stage."

    def handle(self, user_text: str) -> Tuple[str, bool]:
        usr = user_text.strip().lower()
        w = self.words[self.i]
        
        # Determine expected answer based on mode
        expected_answer = w['woccon'].lower() if self.mode == "eng_to_woc" else w['english'].lower()

        # allow exit
        if usr in ("exit", "quit", "stop", "cancel"):
            return (f"👋 Lesson exited. Final score: {self.score}. Type 'lesson' to start another.", True)

        # 1️⃣  Initial prompt – expect the answer
        if self.stage == "prompt":
            if usr == expected_answer:
                # Correct answer - increase score and streak
                self.score += 10 + (self.streak * 2)  # Bonus points for streak
                self.streak += 1
                
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
                    except Exception:
                        # Fallback if any errors
                        pass
                
                # Toggle the mode for quizlet-like experience
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                
                return self._advance(f"✅ Correct! {celebration} +{10 + (self.streak * 2)} points!{fun_fact}")
            
            elif any(t in usr for t in ("i don't know", "idk", "dont know")):
                # Reset streak on giving up
                self.streak = 0
                
                self.stage = "reinforce"
                return (
                    f"ℹ️ No worries — the answer is **{expected_answer}**.\n\n" +
                    self.prompt(),
                    False
                )
            else:
                # Check for close answers
                close_enough = False
                if self.mode == "woc_to_eng":
                    # For English answers, accept partial matches
                    if (expected_answer in usr or usr in expected_answer or
                        any(word in usr for word in expected_answer.split())):
                        close_enough = True
                
                if close_enough:
                    # Half points for close answers
                    self.score += 5
                    self.streak += 1
                    
                    # Toggle mode
                    self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                    
                    return self._advance(f"✅ Close enough! The exact answer is **{expected_answer}**. +5 points!")
                else:
                    # Reset streak on wrong answer
                    self.streak = 0
                    
                    self.stage = "reinforce"
                    return (
                        f"❌ Not quite. The correct answer is **{expected_answer}**.\n\n" +
                        self.prompt(),
                        False
                    )

        # 2️⃣  Reinforce – learner must type the revealed word exactly
        if self.stage == "reinforce":
            if usr == expected_answer:
                # Toggle mode
                self.mode = "woc_to_eng" if self.mode == "eng_to_woc" else "eng_to_woc"
                
                return self._advance("✅ Great! On to the next one 👏")
            return ("❌ Try again:", False)

        return ("⚠️ Something went wrong.", True)

    def _advance(self, message: str) -> Tuple[str, bool]:
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


class WocconAssistant:
    """RAG-powered Woccon assistant with mini-lessons."""

    def __init__(self,
                 dict_path="woccon_language/dictionary.json",
                 rules_path="woccon_language/rules.json",
                 model="llama3:8b",
                 ctx_turns=6):
        self.woccon = WocconT5()
        self.dictionary = self._load_json(dict_path)
        self.rules = self._load_json(rules_path)
        self.model = model
        self.ctx_turns = ctx_turns

        self.documented_words = {e['woccon'].lower() for e in self.dictionary.get('lexicon', [])}
        self.chunks = [
            f"Woccon: {e['woccon']} | English: {e['english']} | POS: {e['pos']}"
            for e in self.dictionary.get('lexicon', [])
        ]
        log.info("RAG ready: %d chunks (%d words)", len(self.chunks), len(self.documented_words))

        self.sessions: Dict[str, Dict] = {}

    def reply(self, user_id: str, text: str) -> str:
        session = self.sessions.setdefault(user_id, {
            'history': deque(maxlen=self.ctx_turns * 2 + 2),
            'lesson': None
        })
        lower = text.lower().strip()

        # lesson mode
        if session['lesson'] is not None:
            resp, done = session['lesson'].handle(text)
            if done:
                session['lesson'] = None
            return resp

        # start lesson
        if any(k in lower for k in ('lesson', 'vocab', 'teach me', 'learn')):
            words = random.sample(self.dictionary['lexicon'], 3)
            session['lesson'] = LessonManager(words)
            return '📚 Starting a mini-lesson!\n\n' + session['lesson'].prompt()

        # RAG + Llama
        retrieved = self._retrieve(text)
        messages = self._build_prompt(text, retrieved, session['history'])
        raw = ollama.chat(
            model=self.model,
            messages=messages,
            options={'temperature': 0.3}
        )['message']['content']
        answer = self._minimal_verify(raw)

        session['history'].append({'role': 'user', 'content': text})
        session['history'].append({'role': 'assistant', 'content': answer})
        return answer

    def _retrieve(self, query: str, k: int = 12) -> List[str]:
        tokens = set(re.findall(r"[a-z]+", query.lower()))
        scored = [(sum(t in ch.lower() for t in tokens), ch) for ch in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ch for s, ch in scored[:k] if s]

    def _build_prompt(self, query: str, docs: List[str], history: deque) -> List[Dict]:
        doc_text = '\n'.join(docs) if docs else 'NO MATCHES IN CORPUS.'
        system = (
            'You are a helpful assistant for the documented Woccon language.\n'
            'Use ONLY facts from the provided documents. If you don\'t know, say so.\n\n'
            f'DOCUMENTS:\n{doc_text}'
        )
        tail = list(history)[-self.ctx_turns * 2:]
        return ([{'role':'system','content':system}] + tail + [{'role':'user','content':query}])

    def _minimal_verify(self, txt: str) -> str:
        patt = re.compile(r"woccon (?:word|for).*?['\"]?([a-z\-]+)['\"]?", re.I)
        for m in patt.finditer(txt):
            cand = m.group(1).lower()
            if cand not in self.documented_words:
                return (f"⚠️ Note: “{cand}” isn’t in the 1709 list; may be speculative.\n\n" + txt)
        return txt

    @staticmethod
    def _load_json(path: str) -> Dict:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='llama3:8b')
    args = parser.parse_args()

    bot = WocconAssistant(model=args.model)
    print("\n🗣️  Woccon CLI — type 'quit' to exit.\n")

    while True:
        try:
            msg = input('woccon> ').strip()
            if msg.lower() in ('quit', 'exit'):
                break
            print('\n' + bot.reply('cli_user', msg) + '\n')
        except KeyboardInterrupt:
            break
