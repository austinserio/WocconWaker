# woccon_llama_assistant.py  (≈240 LOC)

import os, json, re, logging, random
from collections import deque
from typing import Dict, List
import ollama                        # <- you already have this
from main import WocconT5            # <- your rule‑based analyser

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_assistant")


class WocconAssistant:
    """Light‑weight RAG wrapper around WocconT5 + Llama"""

    def __init__(self,
                 dict_path="woccon_language/dictionary.json",
                 rules_path="woccon_language/rules.json",
                 model="llama3:8b-q4_0",         # safe default for 32 GB RAM
                 ctx_turns=6):
        self.woccon = WocconT5()

        self.dictionary = self._load_json(dict_path)
        self.rules      = self._load_json(rules_path)
        self.model      = model
        self.ctx_turns  = ctx_turns

        # pre‑compute documented words set
        self.documented_words = {e["woccon"].lower()
                                 for e in self.dictionary.get("lexicon", [])}

        # build naive “chunk” list for retrieval (one line per dict entry / rule)
        self.chunks = self._build_chunks()

        log.info("RAG ready: %s chunks   (%s words, %s grammar rules)",
                 len(self.chunks),
                 len(self.documented_words),
                 len(self.rules.get("grammar", [])))

        self.sessions: Dict[str, deque] = {}      # fifo history per user

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _load_json(path: str) -> Dict:
        with open(path, "r", encoding="utf‑8") as f:
            return json.load(f)

    def _build_chunks(self) -> List[str]:
        c = []
        for e in self.dictionary.get("lexicon", []):
            c.append(f"Woccon: {e['woccon']} | English: {e['english']} | POS: {e['pos']}")
        for r in self.rules.get("grammar", []):
            c.append(f"Rule: {r['name']} – {r['description']}")
        for g in self.rules.get("general_info", []):
            c.append(f"{g['topic']}: {g['content']}")
        return c

    # -------------------------------------------------- minimal hallucination check
    def _minimal_verify(self, text: str) -> str:
        patt = re.compile(r"woccon (word|for).*?['\"]?([a-z\-]+)['\"]?", re.I)
        for m in patt.finditer(text):
            candidate = m.group(2).lower()
            if candidate not in self.documented_words:
                disclaimer = ("⚠️ Heads‑up: Woccon is only attested in a 1709 "
                              "140‑word list; the name **{0}** isn’t in it. "
                              "Treat this as speculative.").format(candidate)
                return f"{disclaimer}\n\n{text}"
        return text

    # ------------------------------------------------------------- RAG plumbing
    def _retrieve(self, query: str, k=12) -> List[str]:
        q = set(re.findall(r"[a-z]+", query.lower()))
        scored = [(sum(t in ch.lower() for t in q), ch) for ch in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ch for score, ch in scored[:k] if score]

    def _rag_prompt(self, query: str, retrieved: List[str]) -> List[Dict]:
        docs = "\n".join(retrieved) if retrieved else "NO MATCHES IN CORPUS."
        system = (f"You are a helpful assistant for the documented Woccon language.\n"
                  f"Use ONLY facts in the documentation below. "
                  f"If you don’t know, say so.\n\nDOCUMENTS:\n{docs}")
        return [{"role": "system", "content": system},
                *self._context_messages(query)]

    # keep last ctx_turns exchanges
    def _context_messages(self, latest_user_msg: str) -> List[Dict]:
        hist = list(self.session_hist)[-self.ctx_turns*2:]  # user+assistant lines
        hist.append({"role": "user", "content": latest_user_msg})
        return hist

    # ---------------------------------------------------------- public API
    def reply(self, user_id: str, text: str) -> str:
        self.session_hist = self.sessions.setdefault(user_id, deque(maxlen=30))

        retrieved = self._retrieve(text)
        messages  = self._rag_prompt(text, retrieved)

        rsp_raw = ollama.chat(model=self.model,
                              messages=messages,
                              options={"temperature": 0.3})["message"]["content"]

        rsp = self._minimal_verify(rsp_raw)

        # update history
        self.session_hist.extend([{"role": "user", "content": text},
                                  {"role": "assistant", "content": rsp}])
        return rsp


# ------------------------------- simple CLI runner -----------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama3:8b-q4_0")
    args = parser.parse_args()

    bot = WocconAssistant(model=args.model)

    print("\n🗣️  Woccon CLI.  Type 'quit' to exit.")
    while True:
        try:
            msg = input("\nwoccon> ").strip()
            if msg.lower() in {"quit", "exit"}:
                break
            print("\n" + bot.reply("cli_user", msg))
        except KeyboardInterrupt:
            break