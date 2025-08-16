# adaptive.py
# All adaptive logic centralized here.

import random
from typing import List, Dict, Optional, Set

# Difficulty ordering (you can change or extend)
DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

# The correct mapping to points (editable)
POINTS_PER_DIFFICULTY = {
    "easy": 1,
    "medium": 2,  # medium gives +1 extra (total 2)
    "hard": 3     # hard gives +2 extra (total 3)
}

# how many correct at a level to promote
CORRECTS_TO_PROMOTE = 3

def init_user_game_state():
    return {
        "current_level": "easy",
        "streak_at_level": 0,   # consecutive corrects at current level
        "total_points": 0,
        "max_streak": 0,
        "current_streak": 0,
        "answered_this_attempt": [],  # list of question ids attempted this attempt
    }

def next_question_for_user(questions: List[Dict],
                           current_level: str,
                           excluded_ids: Set[str]) -> Optional[Dict]:
    """
    Pick a question from the given difficulty level that is not in excluded_ids.
    Return None if none available at that level.
    """
    candidates = [q for q in questions if q.get("difficulty") == current_level and q.get("id") not in excluded_ids]
    if not candidates:
        return None
    return random.choice(candidates)

def handle_answer(is_correct: bool, q_id: str, state: dict, questions: List[Dict], global_excluded: Set[str]):
    """
    Update state in-place when user answers a question.
    - is_correct: bool
    - q_id: id of question answered
    - state: user state dict from init_user_game_state()
    - questions: full list of questions (for fallback)
    - global_excluded: set of question ids user shouldn't see (previous correct answers across attempts)
    Returns: next_question (dict or None)
    """
    state["answered_this_attempt"].append(q_id)
    state["current_streak"] = state.get("current_streak", 0) + (1 if is_correct else 0)
    state["max_streak"] = max(state["max_streak"], state["current_streak"])

    if is_correct:
        # award points based on current_level
        pts = POINTS_PER_DIFFICULTY.get(state["current_level"], 1)
        state["total_points"] += pts
        state["streak_at_level"] += 1
        # promotion?
        if state["streak_at_level"] >= CORRECTS_TO_PROMOTE:
            # move up one level if possible
            cur_index = DIFFICULTY_LEVELS.index(state["current_level"])
            if cur_index < len(DIFFICULTY_LEVELS) - 1:
                state["current_level"] = DIFFICULTY_LEVELS[cur_index + 1]
            state["streak_at_level"] = 0
    else:
        # wrong answer: move down one level (but not below easy)
        cur_index = DIFFICULTY_LEVELS.index(state["current_level"])
        if cur_index > 0:
            state["current_level"] = DIFFICULTY_LEVELS[cur_index - 1]
        # reset the streak at level
        state["streak_at_level"] = 0
        # reset current streak (consecutive corrects)
        state["current_streak"] = 0

    # Now determine next question. Exclude:
    # - questions from global_excluded (previously correctly answered across attempts)
    # - questions answered this attempt already
    local_excluded = set(global_excluded).union(set(state["answered_this_attempt"]))
    next_q = next_question_for_user(questions, state["current_level"], local_excluded)

    # if none at current level, try to find in other levels (prefer same or nearby)
    if not next_q:
        # try other levels in order of proximity
        for lvl in DIFFICULTY_LEVELS:
            if lvl == state["current_level"]:
                continue
            cand = next_question_for_user(questions, lvl, local_excluded)
            if cand:
                next_q = cand
                break

    return next_q

def difficulty_distribution(attempt_questions: List[Dict]) -> dict:
    dist = {}
    for q in attempt_questions:
        d = q.get("difficulty", "unknown")
        dist[d] = dist.get(d, 0) + 1
    return dist
