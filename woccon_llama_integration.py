# woccon_llama_integration.py

import os, json, re, logging, random
from collections import deque
from typing import Dict, List, Tuple

import ollama                     # your local Llama server client
from main import WocconT5         # the rule-based analyzer
from lesson_manager import LessonManager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_assistant")


class WocconAssistant:
    """RAG-powered Woccon assistant with mini-lessons."""

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

    def reply(self, user_id: str, text: str) -> str:
        # 1) grab or create session
        session = self.sessions.setdefault(user_id, {
            "history": deque(maxlen=self.ctx_turns * 2 + 2),
            "lesson": None
        })

        lower = text.lower().strip()

        # 2) if a lesson is active, delegate to it
        if session["lesson"] is not None:
            resp, done = session["lesson"].handle(text)
            if done:
                session["lesson"] = None
            return resp

        # 3) detect lesson start
        if any(k in lower for k in ("lesson", "vocab", "teach me", "learn")):
            # sample 3 words for a micro-lesson
            words = random.sample(self.dictionary["lexicon"], 3)
            session["lesson"] = LessonManager(words)
            return "📚 Starting a mini-lesson!\n\n" + session["lesson"].prompt()

        # 4) fallback: RAG + Llama
        retrieved = self._retrieve(text)
        messages = self._build_prompt(text, retrieved, session["history"])
        raw = ollama.chat(
            model=self.model,
            messages=messages,
            options={"temperature": 0.3}
        )["message"]["content"]
        answer = self._minimal_verify(raw)

        # record turn
        session["history"].append({"role": "user", "content": text})
        session["history"].append({"role": "assistant", "content": answer})

        return answer

    # ————————————— retrieval + prompting —————————————
    def _retrieve(self, query: str, k: int = 12) -> List[str]:
        tokens = set(re.findall(r"[a-z]+", query.lower()))
        scored = [(sum(t in chunk.lower() for t in tokens), chunk)
                  for chunk in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for score, chunk in scored[:k] if score]

    def _build_prompt(self,
                      query: str,
                      docs: List[str],
                      history: deque) -> List[Dict]:
        # system section with retrieved docs
        doc_text = "\n".join(docs) if docs else "NO MATCHES IN CORPUS."
        system = (
            "You are a helpful assistant for the documented Woccon language.\n"
            "Use ONLY facts from the provided documents. If you don't know, say so.\n\n"
            f"DOCUMENTS:\n{doc_text}"
        )

        # tail of history + new user query
        tail = list(history)[-self.ctx_turns * 2:]
        return (
            [{"role": "system", "content": system}]
            + tail
            + [{"role": "user", "content": query}]
        )

    # ————————————— minimal hallucination check —————————————
    def _minimal_verify(self, text: str) -> str:
        patt = re.compile(r"woccon (?:word|for).*?['\"]?([a-z\-]+)['\"]?", re.I)
        for m in patt.finditer(text):
            candidate = m.group(1).lower()
            if candidate not in self.documented_words:
                return (
                    f"⚠️ Note: “{candidate}” isn’t in the 1709 list; "
                    "this may be speculative.\n\n" + text
                )
        return text

    # ————————————— util —————————————
    @staticmethod
    def _load_json(path: str) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


# ————————————— CLI runner —————————————
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama3:8b")
    args = parser.parse_args()

    bot = WocconAssistant(model=args.model)
    print("\n🗣️  Woccon CLI — type 'quit' to exit.\n")

    while True:
        try:
            msg = input("woccon> ").strip()
            if msg.lower() in ("quit", "exit"):
                break
            print("\n" + bot.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break