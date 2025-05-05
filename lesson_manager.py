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
    """Handles mini-lessons of N words: practice meaning, pronunciation, then spelling."""

    def __init__(self, words: List[Dict]):
        self.words = words
        self.i = 0
        self.stage = "prompt"  # stages: meaning -> pronunciation -> spelling

    def prompt(self) -> str:
        w = self.words[self.i]
        if self.stage == "prompt":
            return (
                f"🆕 Word {self.i + 1}/{len(self.words)}\n"
                f"❓ What’s the Woccon word for **{w['english']}**?\n"
                "(Type it, or “I don’t know” to reveal.)"
            )
        if self.stage == "reinforce":
            return (
                f"✍️ Please type **{w['woccon']}** again to reinforce the spelling:"
            )
        return "⚠️ Unexpected stage."


    def handle(self, user_text: str) -> Tuple[str, bool]:
        usr = user_text.strip().lower()
        w = self.words[self.i]
        exp_woc = w['woccon'].lower()

        # allow exit
        if usr in ("exit", "quit", "stop", "cancel"):
            return ("👋 Lesson exited. Type 'lesson' to start another.", True)

        # 1️⃣  Initial prompt – expect the Woccon word
        if self.stage == "prompt":
            if usr == exp_woc:
                return self._advance("✅ Correct! 🎉")
            elif any(t in usr for t in ("i don't know", "idk", "dont know")):
                self.stage = "reinforce"
                return (
                    f"ℹ️ No worries — the word is **{w['woccon']}**.\n\n" +
                    self.prompt(),
                    False
                )
            else:
                self.stage = "reinforce"
                return (
                    f"❌ Not quite. The correct word is **{w['woccon']}**.\n\n" +
                    self.prompt(),
                    False
                )

        # 2️⃣  Reinforce – learner must type the revealed word exactly
        if self.stage == "reinforce":
            if usr == exp_woc:
                return self._advance("✅ Great! On to the next one 👏")
            return ("❌ Try again:", False)

        return ("⚠️ Something went wrong.", True)

    def _advance(self, success_msg: str) -> Tuple[str, bool]:
        """Move to the next word or finish the lesson."""
        if self.i >= len(self.words) - 1:
            return (
                success_msg +
                "\n\n🎉 Lesson complete! Type 'lesson' to start another.",
                True
            )
        self.i += 1
        self.stage = "prompt"
        return (success_msg + "\n\n" + self.prompt(), False)

    def _current(self):
        return self.words[self.i]

    @staticmethod
    def _phonetic(word: str) -> str:
        # simple char-by-char phonetic representation
        cleaned = word.replace("-", "")
        return '-'.join(list(cleaned.lower()))


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
