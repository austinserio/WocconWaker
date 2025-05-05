import random
from typing import List, Dict, Tuple, TYPE_CHECKING
from collections import deque  # For session history and context turns
import ollama                  # For calling your local LLaMA server

if TYPE_CHECKING:
    from woccon_llama_integration import WocconAssistant

class GrammarLessonManager:
    """Gamified mini‐lessons for Woccon grammar rules."""
    def __init__(self, items: List[Dict], parent: "WocconAssistant"):
        self.items = items
        random.shuffle(self.items)
        self.i = 0
        self.parent = parent
        self.stage = "question"   # stages: question -> reveal -> reinforce
        self.score = 0
        self.streak = 0

    @staticmethod
    def build_items(rules_json: Dict, lexicon: List[Dict]) -> List[Dict]:
        items = []
        # e.g. affix-function questions
        for aff in rules_json["morphology"]["affixes"]["suffixes"]:
            items.append({
                "type": "affix_fn",
                "question": f"What function does the suffix **{aff['form']}** serve?",
                "answer": aff["function"]
            })
        # numeral-pattern question
        items.append({
            "type": "number_fn",
            "question": "What pattern do Woccon speakers use to form the teens?",
            "answer": "Add **-pea** after the base number (ten + X)"
        })
        # affix-application questions
        for aff in rules_json["morphology"]["affixes"]["suffixes"]:
            root_entry = random.choice(lexicon)
            root = root_entry["woccon"]
            items.append({
                "type": "affix_apply",
                "question": f"Add suffix **{aff['form']}** to **{root}**. What is the resulting form?",
                "answer": root + aff["form"]
            })
        # compounding decomposition
        for comp in rules_json["morphology"]["compounding"]["patterns"]:
            items.append({
                "type": "decompose",
                "question": f"Decompose **{comp['example']}** into its root + suffix(es).",
                "answer": ", ".join(comp["components"])
            })
        return items

    def explain(self) -> str:
        """Ask the LLM to explain this grammar rule or word form."""
        itm = self.items[self.i]
        query = f"Explain the grammar behind: {itm['question']}. The correct answer is: {itm['answer']}."
        retrieved = self.parent._retrieve(query)
        messages = self.parent._build_prompt(query, retrieved, deque())  # no convo history
        resp = ollama.chat(model=self.parent.model, messages=messages)["message"]["content"]
        return resp

    def prompt(self) -> str:
        itm = self.items[self.i]
        return (
            f"🏷️ Grammar Q {self.i+1}/{len(self.items)}\n"
            f"❓ {itm['question']}\n"
            f"(Type it, or 'I don’t know' to reveal.)"
        )

    def handle(self, text: str) -> Tuple[str, bool]:
        itm = self.items[self.i]
        lower = text.strip().lower()
        correct = itm["answer"].lower()
        # simple match; you can make this more flexible

        if lower == correct:
            self.score += 1
            self.streak += 1
            resp = f"✅ Right! **{itm['answer']}**.\n\n"
            done = False
        elif lower in ("i don't know", "idk"):
            resp = f"ℹ️ The answer is **{itm['answer']}**.\n\n"
            self.streak = 0
            done = False
        elif lower == "explain":
            return self.explain(), False
        else:
            resp = f"❌ Nope – try again, or 'I don’t know' to reveal.\n"
            return resp, False

        # move on
        self.i += 1
        if self.i >= len(self.items):
            done = True
            resp += f"🎓 You’ve finished your grammar lesson! Score: {self.score}/{len(self.items)}"
        else:
            resp += self.prompt()
        return resp, done