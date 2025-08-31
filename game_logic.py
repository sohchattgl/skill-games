import uuid
import time
import random
import streamlit as st
from typing import Optional, Dict, List, Set
from firebase_utils import (
    log_attempt,
    update_user_best_and_answers,
    get_user_data,
    clear_cache
)

# ---------- GAME CONSTANTS ----------
DIFFICULTY_LEVELS = [1, 2, 3]  # numeric difficulty levels

POINTS_PER_DIFFICULTY = {
    1: 1,  # easy
    2: 2,  # medium
    3: 3   # hard
}

DIFFICULTY_NAMES = {
    1: "Easy",
    2: "Medium",
    3: "Hard"
}

CORRECTS_TO_PROMOTE = 3  # number of correct answers needed to level up

# ---------- SKILL TREE CONFIG ----------
TOPICS = {
    "Hypothesis Testing": {
        "id": "hypothesis_testing",
        "prerequisites": [],  # No prerequisites - initially unlocked
        "points_required": 0,
        "description": "Learn the fundamentals of hypothesis testing"
    },
    "One Sample T-Test": {
        "id": "one_sample_ttest",
        "prerequisites": ["hypothesis_testing"],  # Requires hypothesis testing
        "points_required": 1,  # Need 1 point from prerequisite
        "description": "Apply hypothesis testing to single samples"
    },
    "Two Sample T-Test": {
        "id": "two_sample_ttest",
        "prerequisites": ["hypothesis_testing"],  # Requires hypothesis testing
        "points_required": 1,  # Need 1 point from prerequisite
        "description": "Compare means between two samples"
    }
}

def init_user_game_state():
    """Initialize a new game state for a user"""
    return {
        "current_level": 1,  # Start at level 1 (easy)
        "streak_at_level": 0,
        "total_points": 0,
        "max_streak": 0,
        "current_streak": 0,
        "answered_this_attempt": [],
    }

def start_quiz():
    """Initialize a new quiz session"""
    st.session_state.game_state = init_user_game_state()
    st.session_state.attempt_meta = {
        "attempt_id": str(uuid.uuid4()),
        "start_time": time.time(),
        "questions_attempted": [],
    }
    st.session_state.current_question = None
    st.session_state.game_active = True
    st.session_state.answer_submitted = False
    st.session_state.last_answer_time = 0
    st.session_state.actual_level = 1

def update_topic_progress(user_data: dict, topic: str, attempt_meta: dict) -> dict:
    """Update topic progress based on quiz attempt"""
    if 'topic_progress' not in user_data:
        user_data['topic_progress'] = {}
    if topic not in user_data['topic_progress']:
        user_data['topic_progress'][topic] = {
            'attempts': 0,
            'unlocked': topic == "Hypothesis Testing"
        }
    
    # Get questions attempted for this topic
    topic_questions = [q for q in attempt_meta['questions_attempted'] if q.get('topic') == topic]
    if not topic_questions:  # Skip if no questions were attempted
        return user_data
        
    # Update attempt count
    user_data['topic_progress'][topic]['attempts'] += 1
    
    # Note: points and mastery are calculated on-the-fly in get_topic_stats
    # based on the answered_questions list
    
    return user_data

def end_quiz(firebase_available: bool):
    """End current quiz session and save results"""
    st.session_state.game_active = False
    st.session_state.page = "results"
    
    if firebase_available and st.session_state.user:
        try:
            attempt = st.session_state.attempt_meta.copy()
            attempt["end_time"] = time.time()
            attempt["duration"] = int(attempt["end_time"] - attempt["start_time"])
            attempt["total_points"] = st.session_state.game_state["total_points"]
            attempt["user_email"] = st.session_state.user["email"]
            attempt["topic"] = st.session_state.current_topic
            
            # Get current user data
            user_data = get_user_data(st.session_state.user["email"]) or {}
            
            # Update topic-specific progress
            current_topic = st.session_state.current_topic
            user_data = update_topic_progress(user_data, current_topic, attempt)
            
            # Update global progress
            correct_qs = [q["id"] for q in attempt["questions_attempted"] if q.get("correct")]
            current_answered = set(user_data.get("answered_questions", []))
            current_answered.update(correct_qs)
            
            # Prepare attempt data for logging
            attempt.update({
                "total_points": st.session_state.game_state["total_points"],
                "user_email": st.session_state.user["email"],
                "topic": st.session_state.current_topic,
                "end_time": time.time(),
                "timestamp": time.time()
            })
            
            # Save all updates
            log_attempt(st.session_state.user["email"], attempt)
            update_user_best_and_answers(
                st.session_state.user["email"],
                attempt["total_points"],
                list(current_answered),
                user_data
            )
            
            # Clear cache to reflect new data
            clear_cache()
            
        except Exception as e:
            st.error(f"Error saving progress: {e}")

@st.cache_data(ttl=5)  # Short cache to prevent stale data
def get_topic_stats(user_data: dict, questions: list, topic: str) -> dict:
    """Calculate stats for a specific topic with caching"""
    if not user_data or not questions:
        return {
            'points': 0,
            'total_points': 0,
            'mastered': 0,
            'total_questions': 0,
            'attempts': 0,
            'successes': 0,
            'unlocked': topic == "Hypothesis Testing"
        }
    default_stats = {
        'points': 0,
        'total_points': 0,
        'mastered': 0,
        'total_questions': 0,
        'attempts': 0,
        'successes': 0,
        'unlocked': topic == "Hypothesis Testing"
    }
    
    try:
        # Get all questions for this topic
        topic_questions = [q for q in questions if q.get('topic') == topic]
        if not topic_questions:
            return default_stats
            
        # Get user's progress for this topic
        topic_progress = user_data.get('topic_progress', {}).get(topic, {}) if user_data else {}
        
        # Calculate total available points for this topic's questions
        total_points_available = sum(POINTS_PER_DIFFICULTY.get(int(q.get('difficulty', 1)), 1) 
                                   for q in topic_questions)
        
        # Count questions the user has mastered in this topic and calculate points
        answered_questions = set(user_data.get('answered_questions', [])) if user_data else set()
        mastered_questions = [q for q in topic_questions if q['id'] in answered_questions]
        points_earned = sum(POINTS_PER_DIFFICULTY.get(int(q.get('difficulty', 1)), 1) 
                           for q in mastered_questions)
                           
        return {
            'points': points_earned,
            'total_points': total_points_available,
            'mastered': len(mastered_questions),
            'total_questions': len(topic_questions),
            'attempts': topic_progress.get('attempts', 0),
            'successes': topic_progress.get('successes', 0),
            'unlocked': topic_progress.get('unlocked', topic == "Hypothesis Testing")
        }
    except Exception as e:
        st.error(f"Error calculating topic stats: {str(e)}")
        return default_stats
    
    # Initialize attempts and successes to 0 if not present
    attempts = topic_progress.get('attempts', 0)
    successes = topic_progress.get('successes', 0)
    
    # Root topic is always unlocked, others need prerequisites
    is_unlocked = topic_progress.get('unlocked', topic == "Hypothesis Testing")
    
    return {
        'points': points_earned,  # Now calculated based on answered questions and difficulty
        'total_points': total_points_available,
        'mastered': len(mastered_questions),
        'total_questions': len(topic_questions),
        'attempts': attempts,  # Will show 0 for first attempt
        'successes': successes,  # Will show 0 for first attempt
        'unlocked': is_unlocked
    }

def is_topic_unlocked(topic: str, user_data: dict, questions: list) -> bool:
    """Check if a topic is unlocked for a user based on prerequisites"""
    if not user_data:
        return topic == "Hypothesis Testing"  # Only root topic is initially unlocked
        
    # Root topic is always unlocked
    if topic == "Hypothesis Testing":
        return True
    
    topic_info = TOPICS.get(topic)
    if not topic_info:
        return False
    
    # Check prerequisites
    for prereq_id in topic_info['prerequisites']:
        # Find the prerequisite topic by ID
        prereq_topic_name = None
        for topic_name, topic_config in TOPICS.items():
            if topic_config['id'] == prereq_id:
                prereq_topic_name = topic_name
                break
        if prereq_topic_name:
            prereq_stats = get_topic_stats(user_data, questions, prereq_topic_name)
            # Use '>=' so topic unlocks as soon as enough points are earned
            if prereq_stats['points'] < TOPICS[prereq_topic_name]['points_required']:
                return False
    # Also check if user has enough points in prerequisites for this topic
    total_prereq_points = sum(
        get_topic_stats(user_data, questions, t)['points']
        for t in TOPICS if TOPICS[t]['id'] in topic_info['prerequisites']
    )
    if total_prereq_points < topic_info['points_required']:
        return False
    return True

def start_topic_quiz(topic: str, questions: list):
    """Start a quiz session for a specific topic"""
    topic_questions = [q for q in questions if q.get('topic') == topic]
    st.session_state.questions = topic_questions
    st.session_state.current_topic = topic
    start_quiz()

def get_next_question(questions: list, firebase_available: bool) -> Optional[Dict]:
    """Get next question based on user's progress"""
    excluded_forever = set()
    
    if firebase_available and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
        if user_data:
            excluded_forever = set(user_data.get("answered_questions", []))
    
    excluded_this_session = set(st.session_state.game_state["answered_this_attempt"])
    total_excluded = excluded_forever.union(excluded_this_session)
    
    # Filter questions by current topic if set
    topic_questions = questions
    if hasattr(st.session_state, "current_topic"):
        topic_questions = [q for q in questions if q.get("topic") == st.session_state.current_topic]
    
    try:
        next_q = select_question(
            topic_questions,
            st.session_state.game_state["current_level"],
            total_excluded
        )
        if next_q:
            st.session_state.actual_level = next_q.get("difficulty", 1)
            return next_q
    except:
        pass
    
    available = [q for q in topic_questions if q.get("id") not in total_excluded]
    if available:
        selected_q = available[0]
        st.session_state.actual_level = selected_q.get("difficulty", 1)
        return selected_q
    
    return None

def select_question(questions: List[Dict], current_level: int, excluded_ids: Set[str]) -> Optional[Dict]:
    """Pick a question from the given difficulty level that hasn't been used."""
    candidates = [q for q in questions 
                 if int(q.get("difficulty", 1)) == current_level 
                 and q.get("id") not in excluded_ids]
    
    if not candidates:
        return None
    return random.choice(candidates)

def process_answer(question: Dict, selected: str, questions: list, firebase_available: bool):
    """Process user's answer and update game state"""
    correct = selected == question.get("answer")
    
    # Calculate points based on question difficulty
    question_difficulty = int(question.get("difficulty", 1))
    points = POINTS_PER_DIFFICULTY.get(question_difficulty, 1) if correct else 0

    # Record the attempt
    entry = {
        "id": question["id"],
        "question": question.get("question"),
        "difficulty": int(question.get("difficulty", 1)),
        "topic": question.get("topic"),
        "concepts": question.get("concepts", []) or question.get("concept", []),
        "bloom": question.get("bloom"),
        "chosen": selected,
        "correct_answer": question.get("answer"),
        "correct": correct,
        "pts_awarded": points,
        "timestamp": int(time.time()),
    }
    st.session_state.attempt_meta.setdefault("questions_attempted", []).append(entry)
    st.session_state.attempt_meta["total_points"] = st.session_state.game_state["total_points"]

    try:
        # Update game state
        state = st.session_state.game_state
        state["answered_this_attempt"].append(question["id"])
        state["current_streak"] = state.get("current_streak", 0) + (1 if correct else 0)
        state["max_streak"] = max(state["max_streak"], state["current_streak"])

        if correct:
            # Add points
            state["total_points"] += points
            state["streak_at_level"] += 1
            
            # Check for promotion
            if state["streak_at_level"] >= CORRECTS_TO_PROMOTE:
                if state["current_level"] < max(DIFFICULTY_LEVELS):
                    state["current_level"] += 1
                state["streak_at_level"] = 0
        else:
            # Wrong answer: level down if possible
            if state["current_level"] > min(DIFFICULTY_LEVELS):
                state["current_level"] -= 1
            state["streak_at_level"] = 0
            state["current_streak"] = 0

        # Get excluded questions
        excluded_forever = set()
        if firebase_available and st.session_state.user:
            user_data = get_user_data(st.session_state.user["email"])
            if user_data:
                excluded_forever = set(user_data.get("answered_questions", []))

        excluded_this_session = set(st.session_state.game_state.get("answered_this_attempt", []))
        total_excluded = excluded_forever.union(excluded_this_session)

        # Get next question
        next_q = select_question(questions, state["current_level"], total_excluded)
        
        # If no question at current level, try other levels
        if not next_q:
            for level in DIFFICULTY_LEVELS:
                if level == state["current_level"]:
                    continue
                next_q = select_question(questions, level, total_excluded)
                if next_q:
                    break

        # Update Firebase if answer was correct
        if correct and firebase_available and st.session_state.user:
            try:
                clear_cache()
                user_data = get_user_data(st.session_state.user["email"]) or {}
                current_answered = set(user_data.get("answered_questions", []))
                current_answered.add(question["id"])
                
                update_user_best_and_answers(
                    st.session_state.user["email"],
                    st.session_state.game_state["total_points"],
                    list(current_answered)
                )
                clear_cache()
            except Exception as e:
                print(f"Error updating Firebase progress: {e}")

        # Show feedback
        if correct:
            st.success(f"✅ Correct! +{points} points")
        else:
            st.error(f"❌ Wrong. Answer: {question.get('answer')}")

        # Prepare for next question
        st.session_state.current_question = next_q
        st.session_state.answer_submitted = False
        
        if next_q:
            st.session_state.actual_level = next_q.get("difficulty", 1)
        
        # Small pause and rerun
        time.sleep(1)
        st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")
        st.session_state.answer_submitted = False

def difficulty_distribution(attempt_questions: List[Dict]) -> dict:
    """Calculate distribution of questions by difficulty"""
    dist = {}
    for q in attempt_questions:
        d = DIFFICULTY_NAMES.get(int(q.get("difficulty", 1)), "Unknown")
        dist[d] = dist.get(d, 0) + 1
    return dist

# ---------- SKILL TREE MANAGEMENT ----------
