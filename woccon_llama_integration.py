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


    # ————————————— Replacement code —————————————

    # Use these two methods as direct replacements in your WocconAssistant class

    def reply(self, user_id: str, text: str) -> str:
        session = self.sessions.setdefault(user_id, {
            "history": deque(maxlen=self.ctx_turns * 2 + 2),
            "lesson": None
        })

        lower = text.lower().strip()

        # 1. SHOW ALL WORDS - Handle with flexible patterns
        if self._matches_any_pattern(lower, [
            r"all (?:(?:the )?(?:legal )?)?forms of all(?: the)? words",
            r"what are all(?: the)? (?:(?:legal )?(?:possible )?)?forms of all(?: the)? words",
            r"what are all(?: the)? (?:possible )?words",  
            r"list all (?:woccon )?words",
            r"show (?:me )?all (?:woccon )?words",
            r"what (?:woccon )?words are there",
            r"(?:what|show me|list) all the words from lawsons list"
        ]):
            lines = []
            for root in sorted(self.woccon.woc_to_eng.keys()):
                forms = self.woccon.generate_all_forms(root)
                if forms:
                    lines.append(f"{root}: {', '.join(forms)}")
            return "\n".join(lines) or "⚠️ No roots attested."
                
        # Count words in lists
        if self._matches_any_pattern(lower, [
            r"how many words",
            r"count of words",
            r"number of words",
            r"word count"
        ]):
            total_words = len(self.documented_words)
            return f"There are {total_words} documented Woccon words in Lawson's list from 1709."


        # 2. TRANSLATE ENGLISH TO WOCCON - with safeguards
        m_eng = re.search(
            r"all (?:the )?(?:legal )?forms (?:of|for)\s+'?([a-z\-\s]+)'?\??",
            lower
        )
        if m_eng and "all" not in m_eng.group(1) and "words" not in m_eng.group(1):
            eng = m_eng.group(1).strip().lower()
            entry = self.woccon.eng_to_woc.get(eng)
            if not entry:
                return f"⚠️ No Woccon entry found for English '{eng}'."
            root = entry["woccon"]
            forms = self.woccon.generate_all_forms(root)
            if not forms:
                return f"⚠️ No forms generated for Woccon '{root}'."
            return f"{root}: {', '.join(forms)}"
        
        # T5-enhanced analysis command
        for pattern in [
            r"analyze\s+([a-z\-]+)",
            r"structure of\s+([a-z\-]+)",
            r"break down\s+([a-z\-]+)"
        ]:
            m = re.search(pattern, lower)
            if m:
                woc = m.group(1).strip().lower()
                # Use the enhanced analysis method
                analysis = self.woccon.analyze_word_enhanced(woc)
                
                # Format the analysis for display
                result = [f"Analysis of '{woc}':\n"]
                
                # Show T5 insights if available
                if "t5_insights" in analysis:
                    result.append("T5 Analysis:")
                    for key, value in analysis["t5_insights"].items():
                        result.append(f"- {key.replace('_', ' ').title()}: {value}")
                    result.append("")
                
                # Show affixes
                if analysis["affixes"]:
                    result.append("Affixes:")
                    for affix in analysis["affixes"]:
                        result.append(f"- {affix['type'].capitalize()} '{affix['form']}': {affix['function']}")
                
                # Show roots
                if analysis["roots"]:
                    result.append("\nRoots:")
                    for root in analysis["roots"]:
                        confidence = root.get("confidence", "unknown")
                        enhanced = " (T5 enhanced)" if root.get("t5_enhanced") else ""
                        result.append(f"- Root '{root['root']}' meaning '{root['meaning']}' ({confidence} confidence){enhanced}")
                
                # Show semantic groups if available
                if analysis.get("semantic_groups"):
                    result.append("\nSemantic Categories:")
                    for group, words in analysis["semantic_groups"].items():
                        result.append(f"- {group.replace('_', ' ').title()}: {len(words)} related words")
                
                return "\n".join(result)

        # Enhanced translation command
        for pattern in [
            r"how (?:do|would) (?:i|you|we) say '?([a-z\-\s]+)'? in woccon\??",
            r"translate '?([a-z\-\s]+)'? (?:in)?to woccon",
            r"what(?:'s| is) the woccon (?:word|term) for '?([a-z\-\s]+)'?\??"
        ]:
            m = re.search(pattern, lower)
            if m:
                eng = m.group(1).strip().lower()
                result = self.woccon.translate_to_woccon(eng)
                if result["woccon"]:
                    response = f"The Woccon word for '{eng}' is '{result['woccon']}' ({result['confidence']} confidence)."
                    if result.get("note"):
                        response += f" Note: {result['note']}"
                    if result["alternatives"]:
                        response += f"\nPossible alternatives: {', '.join(result['alternatives'])}"
                    return response
                else:
                    return f"⚠️ No Woccon translation found for '{eng}'."

        # Enhanced meaning lookup
        for pattern in [
            r"what does '?([a-z\-]+)'? mean",
            r"(?:meaning|translation|definition) of '?([a-z\-]+)'?",
            r"translate '?([a-z\-]+)'? to english"
        ]:
            m = re.search(pattern, lower)
            if m:
                woc = m.group(1).strip().lower()
                result = self.woccon.translate_to_english(woc)
                if result["english"]:
                    response = f"'{woc}' means '{result['english']}'"
                    if result.get("pos"):
                        response += f" ({result['pos']})"
                    response += f" ({result['confidence']} confidence)."
                    if result.get("note"):
                        response += f" Note: {result['note']}"
                    if result["alternatives"]:
                        response += f"\nPossible alternatives: {', '.join(result['alternatives'])}"
                    return response
                else:
                    return f"⚠️ '{woc}' is not recognized as a Woccon word."

        # Sound pattern analysis
        for pattern in [
            r"sound patterns (?:in|of) ([a-z\-]+)",
            r"phonology of ([a-z\-]+)",
            r"analyze sounds (?:in|of) ([a-z\-]+)"
        ]:
            m = re.search(pattern, lower)
            if m:
                woc = m.group(1).strip().lower()
                sound_analysis = self.woccon.identify_sound_patterns(woc)
                
                # Format the sound analysis
                result = [f"Sound pattern analysis of '{woc}':\n"]
                
                # Show syllables
                if sound_analysis["syllables"]:
                    result.append(f"Syllables: {'-'.join(sound_analysis['syllables'])}")
                    result.append(f"Syllable count: {len(sound_analysis['syllables'])}")
                    result.append("")
                
                # Show vowel distribution
                if sound_analysis["vowel_distribution"]:
                    result.append("Vowel distribution:")
                    for vowel, count in sound_analysis["vowel_distribution"].items():
                        if count > 0:
                            result.append(f"- {vowel}: {count} occurrences")
                    
                    if sound_analysis["dominant_vowel"]:
                        result.append(f"\nDominant vowel: {sound_analysis['dominant_vowel']}")
                    result.append("")
                
                # Show sound patterns if available
                if sound_analysis["sound_patterns"]:
                    result.append("Sound correspondences:")
                    for pattern in sound_analysis["sound_patterns"]:
                        result.append(f"- Woccon '{pattern['woccon']}' corresponds to Catawba '{pattern['catawba']}'")
                        if pattern.get("examples"):
                            example = pattern["examples"][0] if pattern["examples"] else ""
                            result.append(f"  Example: {example}")
                
                return "\n".join(result)

        # 3. SHOW FORMS OF SPECIFIC ROOT
        m_all = re.search(
            r"(?:all (?:legal )?forms (?:of|for))\s+([a-z\-]+)",
            lower
        )
        if m_all:
            root = m_all.group(1)
            forms = self.woccon.generate_all_forms(root)
            if not forms:
                return f"⚠️ {root} is not an attested Woccon root."
            return "\n".join(forms)

        # 4. HOW TO SAY X IN WOCCON
        for pattern in [
            r"how (?:do|would) (?:i|you|we) say '?([a-z\-\s]+)'? in woccon\??",
            r"translate '?([a-z\-\s]+)'? (?:in)?to woccon",
            r"what(?:'s| is) the woccon (?:word|term) for '?([a-z\-\s]+)'?\??"
        ]:
            m = re.search(pattern, lower)
            if m:
                eng = m.group(1).strip().lower()
                entry = self.woccon.eng_to_woc.get(eng)
                if not entry:
                    return f"⚠️ No Woccon entry found for English '{eng}'."
                return f"The Woccon word for '{eng}' is '{entry['woccon']}'."

        # 5. GENERATE WITH SUFFIXES
        m_gen = re.search(
            r"generate\s+([a-z\-]+)\s+with suffixes\s+(.+)",
            lower
        )
        if m_gen:
            root = m_gen.group(1)
            suffixes = [s.strip() for s in m_gen.group(2).split(",")]
            form = self.woccon.generate_form(root, suffixes)
            return form or f"⚠️ Illegal suffix chain for '{root}'."

        # 6. MEANING OF WOCCON WORD
        for pattern in [
            r"what does '?([a-z\-]+)'? mean",
            r"(?:meaning|translation|definition) of '?([a-z\-]+)'?",
            r"translate '?([a-z\-]+)'? to english"
        ]:
            m = re.search(pattern, lower)
            if m:
                woc = m.group(1).strip().lower()
                entry = self.woccon.woc_to_eng.get(woc)
                if not entry:
                    return f"⚠️ '{woc}' is not a documented Woccon word."
                return f"'{woc}' means '{entry['english']}' ({entry['pos']})."

        # 7. LESSON IN PROGRESS?
        if session["lesson"] is not None:
            resp, done = session["lesson"].handle(text)
            if done:
                session["lesson"] = None
            return resp

        # 8. START A NEW LESSON?
        if self._matches_any_pattern(lower, [
            r"(?:start|give me|do) a lesson",
            r"teach me (?:some )?(?:woccon|vocabulary)",
            r"learn woccon",
            r"(?:i want to|let's) learn"
        ]):
            words = random.sample(self.dictionary["lexicon"], 3)
            session["lesson"] = LessonManager(words)
            return "📚 Starting a mini-lesson!\n\n" + session["lesson"].prompt()

        # 9. HELP COMMAND
        if self._matches_any_pattern(lower, [
            r"help",
            r"what (?:can you|do you) do",
            r"(?:show|list|tell me) (?:the )?commands"
        ]):
            return (
                "🗣️ Woccon Assistant Help:\n\n"
                "- View all words: 'show all words' or 'what are all the words?'\n"
                "- Count words: 'how many words are there?'\n"
                "- Translate: 'how do you say X in Woccon?' or 'translate X to Woccon'\n"
                "- Word meaning: 'what does X mean?' or 'translate X to English'\n"
                "- View forms: 'all forms of X' or 'show forms for X'\n"
                "- Generate: 'generate X with suffixes Y, Z'\n"
                "- Learn: 'start a lesson' or 'teach me vocabulary'\n"
                "- Ask anything else about the Woccon language!"
            )

        # 10. FALLBACK: RAG + LLaMA
        retrieved = self._retrieve(text)
        messages = self._build_prompt(text, retrieved, session["history"])
        raw = ollama.chat(
            model=self.model,
            messages=messages,
            options={"temperature": 0.3}
        )["message"]["content"]
        answer = self._minimal_verify(raw)

        session["history"].append({"role": "user", "content": text})
        session["history"].append({"role": "assistant", "content": answer})
        return answer

    def _matches_any_pattern(self, text: str, patterns: List[str]) -> bool:
            """Helper method to check if text matches any of the given patterns."""
            return any(re.search(pattern, text) for pattern in patterns)

    def _retrieve(self, query: str, k: int = 12) -> List[str]:
        """
        Retrieval function for RAG.
        """
        tokens = set(re.findall(r"[a-z]+", query.lower()))
        scored = [(sum(t in chunk.lower() for t in tokens), chunk)
                  for chunk in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for score, chunk in scored[:k] if score]

    def _build_prompt(self, query: str, docs: List[str], history: deque) -> List[Dict]:
        """
        Build prompt for the LLM.
        """
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

    def _minimal_verify(self, text: str) -> str:
        """
        More lenient verification that doesn't flag common words or partial matches.
        """
        # Skip verification for certain response types
        if any(marker in text for marker in [
            "I don't know", 
            "not in the dictionary",
            "not enough information",
            "can't find"
        ]):
            return text
            
        # Look for statements that claim specific words are Woccon
        patt = re.compile(r"(?:woccon (?:word|for|term)|in woccon,?).*?['\"]?([a-z\-]+)['\"]?", re.I)
        
        for m in patt.finditer(text):
            candidate = m.group(1).lower()
            
            # Check if this is a common English word or a short word that might be part of examples
            if len(candidate) <= 2 or candidate in ["the", "and", "for", "is", "of", "to", "in"]:
                continue
                
            # Check for partial matches with documented words (might be a slight variation)
            close_match = False
            for word in self.documented_words:
                # If it's a substring of a documented word or vice versa
                if candidate in word or word in candidate:
                    close_match = True
                    break
                    
            # Only warn if it's neither documented nor a close match
            if candidate not in self.documented_words and not close_match:
                return (
                    f"⚠️ Note: {candidate} isn't in the documented Woccon word list; "
                    "this may be speculative or a reconstruction.\n\n" + text
                )
        
        return text
    
        
    @staticmethod
    def _load_json(path: str) -> Dict:
        """Load JSON from file."""
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