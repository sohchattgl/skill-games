import streamlit as st
import json
import time
import uuid
from pathlib import Path

from adaptive import (
    init_user_game_state,
    handle_answer,
    difficulty_distribution,
    POINTS_PER_DIFFICULTY,
    next_question_for_user,
)
from firebase_utils import (
    init_firebase,
    create_user_record,
    authenticate_user,
    log_attempt,
    update_user_best_and_answers,
    get_leaderboard,
    get_user,
)

# ---------- CONFIG ----------
SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"
QUESTIONS_FILE = "questions.json"
QUIZ_DURATION_SECONDS = 120

import os


with open(SERVICE_ACCOUNT_PATH, 'w') as f:
    f.write(os.getenv('FIREBASE_KEY'))


# ---------- FAST INITIALIZATION ----------
@st.cache_resource
def init_app():
    firebase_available = Path(SERVICE_ACCOUNT_PATH).exists()
    if firebase_available:
        init_firebase(SERVICE_ACCOUNT_PATH)
    
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)
    
    return firebase_available, questions

st.set_page_config(page_title="Capybara Quiz", layout="centered")
firebase_available, questions = init_app()

# ---------- CLEAN SESSION STATE ----------
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

@st.cache_data(ttl=300)
def get_user_data(email):
    if not firebase_available:
        return None
    try:
        return get_user(email)
    except:
        return None

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
            if st.button("🚀 Start Quiz", use_container_width=True, type="primary", key="nav_start"):
                start_quiz()
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

# ---------- AUTHENTICATION (FIXED) ----------
def render_auth():
    if not firebase_available:
        st.error("🚫 Firebase not configured")
        st.stop()

    # Only show auth if not authenticated
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

# ---------- GAME LOGIC (FIXED) ----------
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

def end_quiz():
    st.session_state.game_active = False
    st.session_state.page = "results"
    
    # Save to Firebase
    if firebase_available and st.session_state.user:
        try:
            attempt = st.session_state.attempt_meta.copy()
            attempt["end_time"] = time.time()
            attempt["duration"] = int(attempt["end_time"] - attempt["start_time"])
            attempt["total_points"] = st.session_state.game_state["total_points"]
            
            log_attempt(st.session_state.user["email"], attempt)
            
            correct_qs = [q["id"] for q in attempt["questions_attempted"] if q.get("correct")]
            update_user_best_and_answers(
                st.session_state.user["email"],
                attempt["total_points"],
                correct_qs
            )
        except:
            pass

def get_next_question():
    excluded = set(st.session_state.game_state["answered_this_attempt"])
    
    if firebase_available and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
        if user_data:
            excluded.update(user_data.get("answered_questions", []))
    
    try:
        next_q = next_question_for_user(
            questions,
            st.session_state.game_state["current_level"],
            excluded
        )
        if next_q:
            return next_q
    except:
        pass
    
    available = [q for q in questions if q.get("id") not in excluded]
    return available[0] if available else None

# ---------- GAME INTERFACE (COMPLETELY FIXED) ----------
def render_game():
    # Timer (no auto-refresh - manual only)
    elapsed = time.time() - st.session_state.attempt_meta["start_time"]
    time_left = max(0, QUIZ_DURATION_SECONDS - elapsed)
    
    if time_left <= 0:
        end_quiz()
        st.rerun()
        return
    
    # Get question
    if not st.session_state.current_question:
        st.session_state.current_question = get_next_question()
        st.session_state.answer_submitted = False
    
    question = st.session_state.current_question
    if not question:
        end_quiz()
        st.rerun()
        return
    
    # UI
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Points", st.session_state.game_state["total_points"])
    with col2:
        st.metric("Level", st.session_state.game_state["current_level"].title())
    with col3:
        mins, secs = divmod(int(time_left), 60)
        if st.button(f"⏰ {mins}:{secs:02d}", key="timer_refresh"):
            st.rerun()  # Manual refresh only
    
    st.markdown("---")
    st.markdown(f"**Q:** {question.get('question')}")
    
    # Simple radio + button (no form complications)
    options = question.get("options", [])
    selected = st.radio("Choose answer:", options, key=f"radio_{question.get('id')}")
    
    # Prevent double submission with time check
    can_submit = not st.session_state.answer_submitted
    current_time = time.time()
    
    if can_submit and st.button("Submit Answer", use_container_width=True, type="primary"):
        # Prevent rapid clicking
        if current_time - st.session_state.last_answer_time > 1:
            st.session_state.answer_submitted = True
            st.session_state.last_answer_time = current_time
            process_answer(question, selected)
    elif st.session_state.answer_submitted:
        st.info("Processing... Next question loading...")

def process_answer(question, selected):
    correct = selected == question.get("answer")
    
    try:
        # Get exclusions
        excluded = set(st.session_state.game_state["answered_this_attempt"])
        if firebase_available and st.session_state.user:
            user_data = get_user_data(st.session_state.user["email"])
            if user_data:
                excluded.update(user_data.get("answered_questions", []))
        
        # Update game state
        next_q = handle_answer(correct, question["id"], st.session_state.game_state, questions, excluded)
        
        # Log attempt
        points = POINTS_PER_DIFFICULTY.get(question.get("difficulty", "easy"), 1) if correct else 0
        st.session_state.attempt_meta["questions_attempted"].append({
            "id": question["id"],
            "difficulty": question.get("difficulty", "easy"),
            "correct": correct,
            "pts_awarded": points,
        })
        
        # Show immediate feedback
        if correct:
            st.success(f"✅ Correct! +{points} points")
        else:
            st.error(f"❌ Wrong. Answer: {question.get('answer')}")
        
        # Move to next question
        st.session_state.current_question = next_q
        st.session_state.answer_submitted = False
        
        # Small delay then refresh
        time.sleep(1)
        st.rerun()
        
    except Exception as e:
        st.error(f"Error: {e}")
        st.session_state.answer_submitted = False

# ---------- OTHER PAGES ----------
def render_home():
    st.markdown("### 🎯 Ready to Test Your Knowledge?")
    st.write("2-minute adaptive quiz. Answer correctly to level up!")
    
    if firebase_available and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
        if user_data and user_data.get("best_score", 0) > 0:
            st.info(f"🏆 Your best: {user_data['best_score']} points")

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
    game = st.session_state.game_state
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Final Score", game["total_points"])
    with col2:
        st.metric("Questions", len(attempt["questions_attempted"]))
    with col3:
        if attempt["questions_attempted"]:
            correct = sum(1 for q in attempt["questions_attempted"] if q["correct"])
            accuracy = (correct / len(attempt["questions_attempted"]) * 100)
            st.metric("Accuracy", f"{accuracy:.0f}%")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Play Again", use_container_width=True):
            start_quiz()
            st.rerun()
    with col2:
        if st.button("🏆 Leaderboard", use_container_width=True):
            st.session_state.page = "leaderboard"
            st.rerun()

# ---------- MAIN APP ----------
def main():
    render_header()
    
    # Check authentication first
    if not st.session_state.authenticated or not st.session_state.user:
        render_auth()
        return
    
    # Show logged in user
    st.sidebar.success(f"👋 {st.session_state.user['display_name']}")
    
    # Navigation
    render_nav()
    st.markdown("---")
    
    # Page routing
    if st.session_state.game_active:
        render_game()
    elif st.session_state.page == "leaderboard":
        render_leaderboard()
    elif st.session_state.page == "results":
        render_results()
    else:
        render_home()

if __name__ == "__main__":
    main()