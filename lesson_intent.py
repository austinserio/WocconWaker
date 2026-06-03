"""Shared intent detection for vocabulary and grammar lessons."""
import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger("woccon_assistant")

EXIT_KEYWORD_PATTERNS = [
    r"\b(exit|quit|leave|cancel)\b",
    r"\b(stop)\s+(the\s+)?lesson\b",
    r"\b(end)\s+(the\s+)?lesson\b",
    r"\b(i'?m\s+done|that'?s\s+enough|i\s+give\s+up)\b",
]
STANDALONE_EXIT_PATTERN = r"^\s*(exit|quit|stop|end|leave|cancel)\s*$"

EXPLAIN_KEYWORD_PATTERNS = [
    r"\b(explain|explanation|help|hint|suggestion)\b",
    r"\b(what|why|how)\b.*\?",
    r"^\s*(what|why|how)\b",
]

# Whole-message give-up phrases (used only when the message is not also a valid answer).
UNCERTAINTY_STANDALONE_PATTERNS = [
    r"^\s*(idk|not sure|no idea|no clue|confused|don'?t know|unsure)\s*$",
    r"^\s*(i don't know|i do not know)\s*$",
    r"^\s*(can'?t remember|don'?t have a guess|skip|pass)\s*$",
    r"^\s*(what is it|what'?s the answer|tell me|reveal|show me)\s*$",
    r"^\s*(give up|stumped|clueless|beats me|drawing a blank)\s*$",
    r"^\s*(um|uh|hmm|err)\s*$",
    r"^\s*(whatever|dunno|who knows)\s*$",
]

UNCERTAINTY_PHRASE_PATTERNS = [
    r"\b(i don't know|idk|no idea|no clue|uncertain|don't remember|forgot)\b",
    r"\b(can'?t remember|don'?t have a guess)\b",
    r"\b(what is it|what'?s the answer|tell me|reveal|show me)\b",
    r"\b(not positive|not confident|not certain|not really sure)\b",
    r"\b(i'm not|im not).*(sure|positive|certain|confident)\b",
    r"\b(no idea|haven'?t a clue|give up|stumped)\b",
    r"\b(beats me|beyond me|drawing a blank|lost|clueless)\b",
]


def normalize_lesson_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s:-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_obvious_exit_intent(text: str) -> bool:
    t = text.lower().strip()
    if re.search(STANDALONE_EXIT_PATTERN, t):
        return True
    return any(re.search(p, t) for p in EXIT_KEYWORD_PATTERNS)


def has_obvious_explain_intent(text: str) -> bool:
    t = text.lower().strip()
    return any(re.search(p, t) for p in EXPLAIN_KEYWORD_PATTERNS)


def parse_llm_label(response: str, valid_labels: List[str]) -> Optional[str]:
    """Return a single valid label; avoid matching EXIT inside negated phrases."""
    if not response:
        return None
    upper = response.strip().upper()
    if upper.startswith("ERROR"):
        return None
    if upper in valid_labels:
        return upper
    tokens = [t for t in re.split(r"[\s.,:;!?\n\-]+", upper) if t]
    if tokens and tokens[0] in valid_labels:
        return tokens[0]
    if tokens and tokens[-1] in valid_labels:
        return tokens[-1]
    # Negated exit, e.g. "NOT AN EXIT REQUEST" → treat as non-exit when CONTINUE is valid
    if "EXIT" in valid_labels and "CONTINUE" in valid_labels:
        if re.search(r"\b(NO|NOT|NEVER|DON'?T|ISN'?T)\b.{0,40}\bEXIT\b", upper):
            return "CONTINUE"
    found = [label for label in valid_labels if re.search(rf"\b{re.escape(label)}\b", upper)]
    if not found:
        return None
    if "EXIT" in found and "CONTINUE" in found:
        return "CONTINUE"
    if len(found) == 1:
        return found[0]
    return None


def response_looks_like_answer(
    user_text: str,
    expected: str,
    alternatives: Optional[Dict[str, str]] = None,
    similarity_fn: Optional[Callable[[str, str], float]] = None,
    similarity_threshold: float = 0.55,
    min_token_len: int = 2,
) -> bool:
    """Fast path: user message overlaps expected answer or registered alternatives."""
    user = normalize_lesson_text(user_text)
    exp = normalize_lesson_text(expected)
    if not user or not exp:
        return False
    if user == exp or exp in user or user in exp:
        return True
    if alternatives:
        for alt_key in alternatives:
            alt = normalize_lesson_text(alt_key)
            if not alt:
                continue
            if user == alt or alt in user or user in alt:
                return True
    for token in re.findall(r"[a-z0-9]+", exp):
        if len(token) >= min_token_len and token in user:
            return True
    for token in re.findall(r"[a-z0-9]+", user):
        if len(token) >= min_token_len and token in exp:
            return True
    if similarity_fn and similarity_fn(user, exp) >= similarity_threshold:
        return True
    return False


def is_standalone_uncertainty(
    text: str,
    expected: Optional[str] = None,
    alternatives: Optional[Dict[str, str]] = None,
    similarity_fn: Optional[Callable[[str, str], float]] = None,
) -> bool:
    """
    True when the user is giving up, not answering.
    Returns False if the message already overlaps the expected answer (e.g. 'interrogative not sure').
    """
    if not text or not str(text).strip():
        return False
    if expected and response_looks_like_answer(
        text, expected, alternatives, similarity_fn=similarity_fn
    ):
        return False
    t = text.lower().strip()
    if t in ("no", "nope", "not", "negative", "nah"):
        return True
    if any(re.search(p, t) for p in UNCERTAINTY_STANDALONE_PATTERNS):
        return True
    # Substring uncertainty only when the message is short (avoid matching inside long answers).
    if len(t.split()) <= 6 and any(re.search(p, t) for p in UNCERTAINTY_PHRASE_PATTERNS):
        if re.search(r"\bnot sure\b", t):
            return True
        if re.search(r"\b(idk|i don't know|no idea|give up|stumped|clueless)\b", t):
            return True
    return False


def answer_fast_accept(
    user_text: str,
    expected: str,
    alternatives: Optional[Dict[str, str]] = None,
    similarity_fn: Optional[Callable[[str, str], float]] = None,
    similarity_threshold: float = 0.85,
    short_answer_max_words: int = 4,
) -> Tuple[bool, str]:
    """
    High-precision accept before LLM: token overlap, alternatives, or short-string similarity.
    Returns (accepted, reason).
    """
    if not expected or not user_text:
        return False, ""
    if response_looks_like_answer(
        user_text, expected, alternatives, similarity_fn=similarity_fn
    ):
        return True, "Matches expected answer or alternative"
    if similarity_fn:
        user_norm = normalize_lesson_text(user_text)
        exp_norm = normalize_lesson_text(expected)
        if (
            user_norm
            and exp_norm
            and len(user_norm.split()) <= short_answer_max_words
        ):
            if similarity_fn(user_norm, exp_norm) >= similarity_threshold:
                return True, "Close string match to expected answer"
            if alternatives:
                for alt_key in alternatives:
                    alt_norm = normalize_lesson_text(alt_key)
                    if alt_norm and similarity_fn(user_norm, alt_norm) >= similarity_threshold:
                        return True, "Close string match to acceptable alternative"
    return False, ""


def classify_exit_intent_via_llm(
    text: str,
    lesson_kind: str,
    model: str,
    llm_chat_fn: Callable,
) -> bool:
    """LLM fallback when exit intent is not obvious."""
    try:
        prompt = f"""
Analyze this user message in the context of a {lesson_kind} lesson.

USER MESSAGE: "{text}"
CONTEXT: The user is in an interactive language lesson and may be answering a question.

Does the user want to EXIT the lesson (stop entirely) or CONTINUE (stay in the lesson)?

Examples:
- "I'm done" = EXIT
- "That's enough" = EXIT
- "I give up" = EXIT
- "This is hard" = CONTINUE
- "Can you help me?" = CONTINUE
- Short answers like single words or roots = CONTINUE

Respond with only one word: EXIT or CONTINUE
"""
        response = llm_chat_fn(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 10},
        )["message"]["content"]
        label = parse_llm_label(response, ["EXIT", "CONTINUE"])
        return label == "EXIT"
    except Exception as e:
        log.error("Error in LLM exit detection: %s", e)
        return False


def classify_explain_intent_via_llm(
    text: str,
    lesson_kind: str,
    model: str,
    llm_chat_fn: Callable,
) -> bool:
    """LLM fallback to distinguish explain/help from an answer attempt."""
    try:
        prompt = f"""
Analyze this user message in the context of a {lesson_kind} lesson.

USER MESSAGE: "{text}"
CONTEXT: The user was just shown a practice question.

Classify intent:
- EXPLANATION = wants more information about the concept
- HELP = wants assistance with the current question
- OTHER = answering or unrelated chat

Examples:
- "explain this rule" = EXPLANATION
- "help me" = HELP
- "what does this suffix mean?" = EXPLANATION
- "imperative" = OTHER
- "ya" = OTHER

Respond with only one word: EXPLANATION, HELP, or OTHER
"""
        response = llm_chat_fn(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 15},
        )["message"]["content"]
        label = parse_llm_label(response, ["EXPLANATION", "HELP", "OTHER"])
        return label in ("EXPLANATION", "HELP")
    except Exception as e:
        log.error("Error in LLM explanation detection: %s", e)
        return has_obvious_explain_intent(text)
