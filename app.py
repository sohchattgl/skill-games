import os
import time
from pathlib import Path
import json
import uuid
import streamlit as st

from firebase_utils import (
    init_firebase,
    log_attempt,
    update_user_best_and_answers,
    get_user_data,
    get_user,
    get_leaderboard,
    authenticate_user,
    create_user_record
)
from data_manager import get_user_attempts
from game_logic import (
    select_question,
    init_user_game_state,
    POINTS_PER_DIFFICULTY,
    DIFFICULTY_LEVELS,
    CORRECTS_TO_PROMOTE,
    start_quiz,
    get_next_question,
    process_answer,
)
from game_logic import end_quiz as gl_end_quiz
from anticheat import apply_copy_protection
from auth_utils import render_auth, logout
from ui_components import (
    render_header,
    render_nav,
    render_home,
    render_leaderboard,
    render_results,
    render_topics,
    render_full_skill_tree,
)
from report_utils import (
    generate_performance_metrics,
    get_difficulty_breakdown,
    get_concept_performance,
    analyze_strengths_weaknesses,
    get_bloom_progress,
    generate_recommendations,
    plot_performance_history,
    plot_concept_performance
)

# ---------- CONFIG ----------
SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"
QUESTIONS_FILE = "questions.json"
QUIZ_DURATION_SECONDS = 300

import os

env = 'prod'

if env == 'dev':
    from dotenv import load_dotenv
    load_dotenv()

# Create Firebase key file from environment variable
with open(SERVICE_ACCOUNT_PATH, 'w') as f:
    f.write(os.getenv('FIREBASE_KEY'))

# ---------- FAST INITIALIZATION ----------
@st.cache_resource
def init_app():
    try:
        firebase_available = Path(SERVICE_ACCOUNT_PATH).exists()
        if firebase_available:
            init_firebase(SERVICE_ACCOUNT_PATH)
        
        # Load and validate questions
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            questions = json.load(f)
            
        # Validate required fields
        required_fields = ["id", "question", "options", "answer", "difficulty", "topic"]
        for q in questions:
            missing = [f for f in required_fields if f not in q]
            if missing:
                st.error(f"Question {q.get('id', 'unknown')} missing required fields: {missing}")
            # Set defaults for optional fields
            q["difficulty"] = int(q.get("difficulty", 1))
            q["topic"] = str(q.get("topic", "Hypothesis Testing"))
            q["concepts"] = q.get("concepts", q.get("concept", []))
            q["bloom"] = str(q.get("bloom", "remember")).lower()
            # Ensure an id exists
            if "id" not in q:
                q["id"] = str(uuid.uuid4())
            
        # Store questions globally
        st.session_state.questions = questions
        return firebase_available, questions
        
    except Exception as e:
        st.error(f"Error initializing app: {e}")
        return False, []
    

st.set_page_config(page_title="Capybara Quiz", layout="centered")
firebase_available, questions = init_app()

# ---------- SESSION STATE ----------
def init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "game_active" not in st.session_state:
        st.session_state.game_active = False
    if "game_state" not in st.session_state:
        st.session_state.game_state = None
    if "attempt_meta" not in st.session_state:
        st.session_state.attempt_meta = None
    if "current_question" not in st.session_state:
        st.session_state.current_question = None
    if "answer_submitted" not in st.session_state:
        st.session_state.answer_submitted = False
    if "last_answer_time" not in st.session_state:
        st.session_state.last_answer_time = 0
    if "questions" not in st.session_state:
        st.session_state.questions = questions if 'questions' in globals() else []

# Initialize session state
init_session()

# ---------- CACHED DATA ----------
@st.cache_data(ttl=60)
def get_leaderboard_cached():
    if not firebase_available:
        return []
    try:
        return get_leaderboard(limit=10)
    except:
        return []

@st.cache_data(ttl=30)
def get_user_data(email):
    if not firebase_available:
        return None
    try:
        return get_user(email)
    except:
        return None

def clear_user_cache(email):
    """Clear cached user data when user answers questions"""
    get_user_data.clear()

@st.cache_data(ttl=30)  
def get_attempts_cached(email):
    """Cache user attempts data"""
    if not firebase_available:
        return []
    try:
        from data_manager import get_user_attempts
        return get_user_attempts(email)
    except Exception as e:
        print(f"Error getting attempts for {email}: {e}")
        return []

# ---------- UI COMPONENTS ----------
def render_header():
    st.markdown("""
    <div style='text-align: center; padding: 1rem 0; margin-bottom: 2rem;'>
        <h1>🦫 Capybara Quiz</h1>
        <p style='color: #666; margin: 0;'>Fast. Smart. Adaptive.</p>
    </div>
    """, unsafe_allow_html=True)

def render_nav():
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🏠 Home", use_container_width=True, key="nav_home"):
            st.session_state.page = "home"
            st.rerun()
    with col2:
        if st.button("🏆 Board", use_container_width=True, key="nav_board"):
            st.session_state.page = "leaderboard"
            st.rerun()
    with col3:
        if st.session_state.game_active:
            if st.button("⏹️ End Quiz", use_container_width=True, type="secondary", key="nav_end"):
                end_quiz()
                st.rerun()
        else:
            if st.button("📚 Topics", use_container_width=True, type="primary", key="nav_topics"):
                st.session_state.page = "topics"
                st.rerun()
    with col4:
        if st.button("🚪 Logout", use_container_width=True, key="nav_logout"):
            logout()
            st.rerun()

def logout():
    """Clean logout function"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session()

# ---------- AUTHENTICATION ----------
def render_auth():
    if not firebase_available:
        st.error("🚫 Firebase not configured")
        st.stop()

    if st.session_state.authenticated:
        return

    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        with st.form("login_form_unique", clear_on_submit=True):
            email = st.text_input("Email", placeholder="your@email.com", key="login_email_input")
            password = st.text_input("Password", type="password", key="login_pw_input")
            
            if st.form_submit_button("Login", use_container_width=True):
                if email and password:
                    result = authenticate_user(email.strip().lower(), password)
                    if result.get("ok"):
                        st.session_state.user = {
                            "email": email.strip().lower(),
                            "display_name": result["user"]["display_name"]
                        }
                        st.session_state.authenticated = True
                        st.success("✅ Login successful!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"❌ {result.get('error', 'Login failed')}")
                else:
                    st.error("Please enter both email and password")

    with tab2:
        with st.form("signup_form_unique", clear_on_submit=True):
            email = st.text_input("Email", placeholder="your@email.com", key="signup_email_input")
            name = st.text_input("Name", placeholder="Your Name", key="signup_name_input")
            password = st.text_input("Password", type="password", key="signup_pw_input")
            
            if st.form_submit_button("Sign Up", use_container_width=True):
                if email and password:
                    display_name = name.strip() or email.split("@")[0]
                    result = create_user_record(email.strip().lower(), display_name, password)
                    if result.get("ok"):
                        st.success("✅ Account created! Please login.")
                    else:
                        st.error(f"❌ {result.get('error', 'Signup failed')}")
                else:
                    st.error("Please enter email and password")

# ---------- GAME LOGIC ----------
def start_quiz():
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
    st.session_state.actual_level = 1  # Change from "easy" to 1

def end_quiz():
    """Proxy end_quiz to the game_logic implementation which handles enriched attempt logging."""
    # Delegate to the game_logic implementation which attaches topic/user/timestamps
    try:
        gl_end_quiz(firebase_available)
    except Exception:
        # Fallback to minimal local behavior if delegation fails
        st.session_state.game_active = False
        st.session_state.page = "results"
        try:
            attempt = st.session_state.attempt_meta.copy()
            attempt["end_time"] = time.time()
            attempt["duration"] = int(attempt["end_time"] - attempt["start_time"])
            attempt["total_points"] = st.session_state.game_state["total_points"]
            log_attempt(st.session_state.user["email"], attempt)
        except Exception:
            pass

def get_next_question():
    """Get next question - never repeat correctly answered questions"""
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
            st.session_state.actual_level = next_q.get("difficulty", 1)  # Default to 1
            return next_q
    except:
        pass
    
    available = [q for q in topic_questions if q.get("id") not in total_excluded]
    if available:
        selected_q = available[0]
        st.session_state.actual_level = selected_q.get("difficulty", 1)  # Default to 1
        return selected_q
    
    return None

# ---------- GAME INTERFACE ----------
def render_game():
    # Apply copy protection
    cleanup_protection = apply_copy_protection()
    
    # Timer
    elapsed = time.time() - st.session_state.attempt_meta["start_time"]
    time_left = max(0, QUIZ_DURATION_SECONDS - elapsed)
    
    if time_left <= 0:
        cleanup_protection()
        end_quiz()
        st.rerun()
        return
    
    # Get question
    if not st.session_state.current_question:
        st.session_state.current_question = get_next_question()
        st.session_state.answer_submitted = False
    
    question = st.session_state.current_question
    if not question:
        cleanup_protection()
        end_quiz()
        st.rerun()
        return
    
    # UI
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Points", st.session_state.game_state["total_points"])
    with col2:
        actual_difficulty = getattr(st.session_state, 'actual_level', 1)
        theoretical_level = st.session_state.game_state["current_level"]
        
        # Convert numeric difficulties to display text
        difficulty_map = {1: "Easy", 2: "Medium", 3: "Hard"}
        actual_text = difficulty_map.get(actual_difficulty, "Easy")
        theoretical_text = difficulty_map.get(theoretical_level, "Easy")
        
        if actual_difficulty != theoretical_level:
            st.metric("Level", actual_text, delta=f"Target: {theoretical_text}")
        else:
            st.metric("Level", actual_text)
    with col3:
        mins, secs = divmod(int(time_left), 60)
        if st.button(f"⏰ {mins}:{secs:02d}", key="timer_refresh"):
            st.rerun()
    
    st.markdown("---")
    
    # Show question with new fields
    st.markdown(f"**Q:** {question.get('question')}")
    
    current_difficulty = int(question.get("difficulty", 1))
    # Define difficulty mappings as dictionaries
    difficulty_map = {
        1: "Easy",
        2: "Medium", 
        3: "Hard"
    }
    
    difficulty_emoji = {
        1: "🟢",
        2: "🟡",
        3: "🔴"
    }
    
    st.caption(f"{difficulty_emoji.get(current_difficulty, '🟢')} {difficulty_map.get(current_difficulty, 'Easy')} Question")
    
    # Show topic and concepts
    if question.get("topic"):
        st.caption(f"📚 Topic: {question['topic']}")
        
    # Show concepts (with unique handling)
    if question.get("concepts"):
        concepts = list(dict.fromkeys(question['concepts']))  # Remove duplicates
        st.caption(f"🔍 Concepts: {', '.join(concepts)}")
    
    # Show explanation after answer
    if st.session_state.answer_submitted and question.get("reasoning"):
        st.info(f"💡 {question['reasoning']}")
    
    
    # Answer options
    options = question.get("options", [])
    selected = st.radio("Choose answer:", options, key=f"radio_{question.get('id')}")
    
    # Submit button
    can_submit = not st.session_state.answer_submitted
    current_time = time.time()
    
    if can_submit and st.button("Submit Answer", use_container_width=True, type="primary"):
        if current_time - st.session_state.last_answer_time > 1:
            st.session_state.answer_submitted = True
            st.session_state.last_answer_time = current_time
            process_answer(question, selected)
    elif st.session_state.answer_submitted:
        st.info("Processing... Next question loading...")
    
    cleanup_protection()

def process_answer(question, selected):
    correct = selected == question.get("answer")
    
    # Calculate points based on difficulty
    question_difficulty = int(question.get("difficulty", 1))
    points = POINTS_PER_DIFFICULTY.get(question_difficulty, 1) if correct else 0

    # Append a single record for this question
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

        st.session_state.attempt_meta["total_points"] = state["total_points"]
        
        # Get excluded questions and next question
        excluded_forever = set()
        if firebase_available and st.session_state.user:
            user_data = get_user_data(st.session_state.user["email"])
            if user_data:
                excluded_forever = set(user_data.get("answered_questions", []))

        excluded_this_session = set(st.session_state.game_state.get("answered_this_attempt", []))
        total_excluded = excluded_forever.union(excluded_this_session)
        
        next_q = get_next_question()

        if correct and firebase_available and st.session_state.user:
            try:
                clear_user_cache(st.session_state.user["email"])

                user_data = get_user_data(st.session_state.user["email"]) or {}
                current_answered = set(user_data.get("answered_questions", []))
                current_answered.add(question["id"])

                update_user_best_and_answers(
                    st.session_state.user["email"],
                    st.session_state.game_state["total_points"],
                    list(current_answered)
                )

                clear_user_cache(st.session_state.user["email"])

            except Exception as e:
                print(f"Error updating answered questions: {e}")

        # Feedback
        if correct:
            st.success(f"✅ Correct! +{points} points")
        else:
            st.error(f"❌ Wrong. Answer: {question.get('answer')}")

        # Next question
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

# ---------- OTHER PAGES ----------
def render_home():
    """Wrapper for ui_components.render_home"""
    from ui_components import render_home as ui_render_home
    ui_render_home(firebase_available, questions)

def render_leaderboard():
    st.markdown("### 🏆 Leaderboard")
    
    leaderboard = get_leaderboard_cached()
    if not leaderboard:
        st.info("No scores yet!")
        return
    
    for i, user in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        st.write(f"{medal} **{user['display_name']}** — {user['best_score']} pts")

def render_results():
    st.markdown("### 🎉 Quiz Complete!")
    
    attempt = st.session_state.attempt_meta
    metrics = generate_performance_metrics(attempt)
    
    # Basic Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Final Score", metrics["points"])
    with col2:
        st.metric("Questions", metrics["total_questions"])
    with col3:
        st.metric("Correct", metrics["correct_questions"])
    with col4:
        st.metric("Accuracy", f"{metrics['accuracy']:.0f}%")
    
    # Show Stats - Full Width, Expanded
    st.markdown("### 📊 Detailed Performance Analysis")
    
    # Concept Performance
    st.subheader("🎯 Topic Performance")
    concept_stats = get_concept_performance(attempt["questions_attempted"])
    if concept_stats:
        fig = plot_concept_performance(concept_stats)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No topic data available for this attempt.")
    
    # Strengths & Weaknesses
    analysis = analyze_strengths_weaknesses(concept_stats)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💪 Strengths")
        if analysis["strengths"]:
            for concept, acc, pts in analysis["strengths"]:
                st.success(f"✓ {concept} ({acc:.0%} accuracy)")
        else:
            st.info("Keep practicing to develop your strengths!")
    
    with col2:
        st.subheader("🎯 Areas to Improve")
        if analysis["weaknesses"]:
            for concept, acc, pts in analysis["weaknesses"]:
                st.error(f"△ {concept} ({acc:.0%} accuracy)")
        else:
            st.success("Great job! No significant weak areas identified.")
    
    # Bloom's Taxonomy Progress - Expanded
    st.subheader("🧠 Bloom's Taxonomy Progress")
    bloom_stats = get_bloom_progress(attempt["questions_attempted"])
    if bloom_stats:
        # Create a progress bar for each level
        for level, stats in bloom_stats.items():
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
            st.markdown(f"**{level.title()}**")
            st.progress(accuracy / 100)
            st.caption(f"{stats['correct']}/{stats['total']} correct ({accuracy:.0f}%)")
    else:
        st.info("No Bloom's taxonomy data available for this attempt.")
    
    # Performance History - moved below bloom, full width
    st.markdown("### 📈 Performance History")
    if firebase_available and st.session_state.user:
        attempts = get_attempts_cached(st.session_state.user["email"])
        
        if attempts and len(attempts) > 1:  # Need more than 1 attempt for history
            try:
                fig = plot_performance_history(attempts)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Could not plot performance history: {str(e)}")
                # Fallback to simple list
                st.markdown("#### Recent Quiz Attempts")
                for i, attempt in enumerate(attempts[-5:]):
                    score = attempt.get("total_points", 0)
                    topic = attempt.get("topic", "General Quiz")
                    st.write(f"**{topic}**: {score} points")
        else:
            st.info("Take more quizzes to see your performance trends!")
    
    # Recommendations
    st.subheader("📚 Recommended Next Steps")
    if analysis["weaknesses"]:
        recommendations = generate_recommendations(analysis["weaknesses"])
        for rec in recommendations:
            if rec["type"] == "lecture":
                st.info(f"📺 {rec['title']}")
            else:
                st.warning(f"✍️ {rec['title']}")
            st.markdown(f"[Start →]({rec['link']})")
    else:
        st.success("🎯 You're doing great! Try some harder questions to challenge yourself.")
    

# ---------- MAIN APP ----------
def main():
    render_header()
    
    if not st.session_state.authenticated or not st.session_state.user:
        render_auth()
        return
    
    st.sidebar.success(f"👋 {st.session_state.user['display_name']}")
    
    render_nav()
    st.markdown("---")
    
    if st.session_state.game_active:
        render_game()
    elif st.session_state.page == "leaderboard":
        render_leaderboard()
    elif st.session_state.page == "results":
        render_results()
    elif st.session_state.page == "topics":
        render_topics(st.session_state.questions, firebase_available)
    elif st.session_state.page == "full_skill_tree":
        render_full_skill_tree()
    else:
        render_home()

if __name__ == "__main__":
    main()