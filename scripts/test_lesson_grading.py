#!/usr/bin/env python3
"""Manual checks for lesson answer grading fast paths (no LLM)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grammar_lesson_manager import GrammarLessonManager
from lesson_intent import answer_fast_accept, is_standalone_uncertainty


class _ParentStub:
    model = "stub"


def _grammar_item_index(items, substring: str) -> int:
    for i, it in enumerate(items):
        if substring in it.get("question", ""):
            return i
    raise ValueError(f"No item containing {substring!r}")


def main() -> None:
    rules_path = ROOT / "woccon_language" / "rules_unified.json"
    dict_path = ROOT / "woccon_language" / "dictionary_unified.json"
    with open(rules_path, encoding="utf-8") as f:
        rules = json.load(f)
    with open(dict_path, encoding="utf-8") as f:
        lexicon = json.load(f)["lexicon"]

    items = GrammarLessonManager.build_items(rules, lexicon)
    gm = GrammarLessonManager(items, parent=_ParentStub())
    idx = _grammar_item_index(items, "katẽ:ne")
    gm.i = idx
    gm._setup_question_alternatives(items[idx])
    expected = items[idx]["answer"]

    def sim(a: str, b: str) -> float:
        return gm._string_similarity(a, b)

    cases = [
        ("Interrogative", True, False),
        ("interrogative mode", True, False),
        ("not sure", False, True),
        ("imperative", False, False),
    ]
    failures = 0
    for user, should_accept, should_uncertainty in cases:
        accepted, _ = answer_fast_accept(
            user, expected, gm.alternative_answers, similarity_fn=sim
        )
        uncertain = is_standalone_uncertainty(
            user, expected=expected, alternatives=gm.alternative_answers, similarity_fn=sim
        )
        ok = (accepted == should_accept) and (uncertain == should_uncertainty)
        status = "ok" if ok else "FAIL"
        if not ok:
            failures += 1
        print(
            f"{status}: user={user!r} fast_accept={accepted} "
            f"(want {should_accept}) uncertain={uncertain} (want {should_uncertainty})"
        )

    # Grading without LLM: patch llm_chat to fail
    import grammar_lesson_manager as glm

    def _boom(*_a, **_k):
        raise RuntimeError("LLM disabled for test")

    orig = glm.llm_chat
    glm.llm_chat = _boom
    try:
        ok, *_ = gm.check_answer_with_llm("Interrogative", expected, items[idx]["question"])
        print(f"{'ok' if ok else 'FAIL'}: check_answer_with_llm(Interrogative) without LLM -> {ok}")
        if not ok:
            failures += 1
    finally:
        glm.llm_chat = orig

    # Routing: a wrong-but-on-topic answer must be graded incorrect (not off-topic),
    # using a stubbed LLM so the test is deterministic and offline.
    import grammar_lesson_manager as glm

    gm2 = GrammarLessonManager(items, parent=_ParentStub())
    ya_idx = _grammar_item_index(gm2.items, "root **ya-**")
    gm2.i = ya_idx
    gm2._setup_question_alternatives(gm2.items[ya_idx])
    gm2.parent = type(
        "P",
        (),
        {"model": "stub", "_retrieve": lambda self, q: [], "_build_prompt": lambda self, q, r, h: []},
    )()

    def _fake_llm(evaluation):
        def _inner(*_a, **_k):
            return {"message": {"content": json.dumps({"evaluation": evaluation, "confidence": 0.9})}}
        return _inner

    orig2 = glm.llm_chat
    try:
        glm.llm_chat = _fake_llm("incorrect")
        msg, done = gm2.handle("Path")
        wrong_ok = msg.startswith("❌") and not done
        print(f"{'ok' if wrong_ok else 'FAIL'}: 'Path' on ya- -> {msg.splitlines()[0]!r}")
        if not wrong_ok:
            failures += 1

        # Then 'I'm not sure' should reveal the answer, not show the off-topic menu.
        glm.llm_chat = _fake_llm("off_topic")
        msg2, _ = gm2.handle("I'm not sure")
        reveal_ok = "No problem! The answer is" in msg2
        print(f"{'ok' if reveal_ok else 'FAIL'}: 'I'm not sure' -> {msg2.splitlines()[0]!r}")
        if not reveal_ok:
            failures += 1

        # After a reveal, continuing must advance to the NEXT question, not repeat.
        q_before = gm2.items[gm2.i]["question"]
        msg3, _ = gm2.handle("Let's continue to the next question")
        q_after = gm2.items[gm2.i]["question"]
        advance_ok = q_before != q_after and q_after in msg3
        print(f"{'ok' if advance_ok else 'FAIL'}: continue after reveal advances ({q_before != q_after})")
        if not advance_ok:
            failures += 1
    finally:
        glm.llm_chat = orig2

    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
