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





from neo4j import GraphDatabase
import streamlit.components.v1 as components
from pyvis.network import Network
from tempfile import NamedTemporaryFile
from pathlib import Path

@st.cache_resource
def init_neo4j():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        # quick ping
        with driver.session() as s:
            s.run("RETURN 1").consume()
        return driver
    except Exception as e:
        st.warning(f"Neo4j not available: {e}")
        return None

def fetch_skill_graph(driver):
    """
    Expected Neo4j model:
      (:Skill {id, name})-[:SUBSKILL_OF]->(:Skill)
      (:Question {id})-[:ASSESSES]->(:Skill)
    """
    with driver.session() as s:
        # skills
        skills = s.run("MATCH (s:Skill) RETURN s.id AS id, coalesce(s.name, s.id) AS name").data()
        # edges (skill hierarchy)
        edges = s.run("""
            MATCH (p:Skill)-[:PRE_PREREQUISITE]->(c:Skill)
            RETURN p.id AS parent, c.id AS child
        """).data()
        # question links (via QuestionBank)
        q_links = s.run("""
            MATCH (s:Skill)-[:HAS]->(:QuestionBank)-[:HAS]->(q:Question)
            RETURN q.id AS qid, s.id AS sid
        """).data()

    return skills, edges,q_links

def compute_mastery_per_skill(q_links, mastered_qids):
    """
    mastered_qids: set of question IDs the user has permanently mastered (from Firebase)
    Returns dict sid -> (mastered, total)
    """
    per_skill = {}
    for row in q_links:
        sid = row["sid"]
        qid = row["qid"]
        #print("Question id:",qid)
        total, mastered = per_skill.get(sid, (0,0))
        total += 1
        if qid in mastered_qids:
            mastered += 1
        print("Mastered skills:",mastered)
        per_skill[sid] = (mastered, total)
    return per_skill



def render_skill_tree_viz(skills, edges, mastery=None):
    """
    Enhanced skill tree visualization with improved text visibility.
    
    Args:
        skills: List of skill dicts with 'id' and 'name'
        edges: List of edge dicts with 'parent' and 'child'
        mastery: dict sid -> (mastered, total)
    
    Colors:
      - No questions: #f8f9fa (light gray)
      - 0%: #e9ecef (gray)
      - (0,100%): gradient blue scale
      - 100%: #00b894 (green)
    """
    from pyvis.network import Network
    from tempfile import NamedTemporaryFile
    from pathlib import Path
    import streamlit.components.v1 as components
    
    net = Network(height="650px", width="100%", directed=True)
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=100, spring_strength=0.1)
    
    def color_for_ratio(r):
        """Generate color based on mastery ratio."""
        if r == 1.0:
            return "#00b894"  # Green for 100%
        if r == 0.0:
            return "#e9ecef"  # Light gray for 0%
        
        # Blue gradient for partial mastery
        base_blue = [52, 152, 219]  # RGB for #3498db
        intensity = 0.6 + (0.4 * r)  # Scale from 60% to 100% intensity
        return f"rgb({int(base_blue[0] * intensity)}, {int(base_blue[1] * intensity)}, {int(base_blue[2] * intensity)})"
    
    def get_font_config(ratio):
        """Configure font based on mastery ratio for better visibility."""
        if ratio is None or ratio == 0:
            return {
                'color': '#2c3e50',      # Dark text for light backgrounds
                'size': 14,
                'face': 'arial',
                'strokeWidth': 2,
                'strokeColor': '#ffffff'  # White outline for contrast
            }
        elif ratio == 1.0:
            return {
                'color': '#ffffff',      # White text for green background
                'size': 16,
                'face': 'arial',
                'strokeWidth': 2,
                'strokeColor': '#2c3e50'  # Dark outline
            }
        else:
            return {
                'color': '#ffffff',      # White text for blue backgrounds
                'size': 15,
                'face': 'arial',
                'strokeWidth': 2,
                'strokeColor': '#2c3e50'  # Dark outline
            }
    
    # Add nodes with enhanced visibility
    for s in skills:
        sid = s["id"]
        name = s["name"]
        m, t = mastery.get(sid, (0, 0))
        ratio = (m / t) if t > 0 else None
        
        # Create subtitle with better formatting
        # Create subtitle with better formatting
        if t == 0:
            subtitle = f"{name} - No linked questions"
        else:
            percentage = int((m/t) * 100)
            subtitle = f"{name} - Mastery: {m}/{t} ({percentage}%)"
        
        # Get color and font configuration
        color = "#f8f9fa" if ratio is None else color_for_ratio(ratio)
        font_config = get_font_config(ratio)
        
        # Size based on mastery (larger for higher mastery)
        base_size = 25
        size = base_size if ratio is None else base_size + int(20 * ratio)  # 25–45
        
        # Add node with enhanced styling
        net.add_node(
            sid, 
            label=name,
            title=subtitle,
            color={
                'background': color,
                'border': '#2c3e50',
                'highlight': {
                    'background': color,
                    'border': '#e74c3c'
                }
            },
            font=font_config,
            shape="dot",
            size=size,
            borderWidth=2
        )
    
    # Add edges with better styling
    for e in edges:
        net.add_edge(
            e["parent"], 
            e["child"], 
            arrows="to",
            color={'color': '#7f8c8d', 'highlight': '#e74c3c'},
            width=2,
            smooth={'type': 'dynamic'}
        )
    
    # Configure physics for better layout
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -3000,
          "centralGravity": 0.3,
          "springLength": 120,
          "springConstant": 0.1,
          "damping": 0.95,
          "avoidOverlap": 1
        },
        "maxVelocity": 50,
        "minVelocity": 0.1,
        "stabilization": {"iterations": 100}
      },
      "nodes": {
        "borderWidthSelected": 3
      },
      "interaction": {
        "hover": true,
        "hoverConnectedEdges": true,
        "selectConnectedEdges": false
      }
    }
    """)
    
    # Generate and display the network
    with NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        net.show(f.name, notebook=False)
        html = Path(f.name).read_text(encoding="utf-8")
    
    components.html(html, height=680, scrolling=True)

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

# ---------- NEO4J CONFIG ----------
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://22339b75.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "HU_7HSU8Ow2HSklMpCeg3lyu7I0EuHmSmyGWvPNFPjQ")


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
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if st.button("🏠 Home", use_container_width=True, key="nav_home"):
            st.session_state.page = "home"
            st.rerun()
    with col2:
        if st.button("🏆 Board", use_container_width=True, key="nav_board"):
            st.session_state.page = "leaderboard"
            st.rerun()
    with col3:
        if st.button("🌳 Skills", use_container_width=True, key="nav_skills"):
            st.session_state.page = "skills"; 
            st.rerun()
    with col4:
        if st.session_state.game_active:
            if st.button("⏹️ End Quiz", use_container_width=True, type="secondary", key="nav_end"):
                end_quiz()
                st.rerun()
        else:
            if st.button("📚 Topics", use_container_width=True, type="primary", key="nav_topics"):
                st.session_state.page = "topics"
                st.rerun()
    with col5:
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

def render_skills():
    st.markdown("### 🌳 Skill Tree")
    driver = init_neo4j()
    if not driver:
        st.error("Neo4j connection not available. Check NEO4J_* settings.")
        return

    # get user mastery from Firebase (permanently mastered question IDs)
    mastered_ids = set()
    if firebase_available and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
        if user_data:
            mastered_ids = set(user_data.get("answered_questions", []))
    print("User data:",user_data)
    print("Mastered ids:",mastered_ids)
    with st.spinner("Loading skill graph..."):
        skills, edges, q_links = fetch_skill_graph(driver)
        mastery = compute_mastery_per_skill(q_links, mastered_ids)
        #quick stats
        mastered_skills = sum(1 for sid,(m,t) in mastery.items() if t>0 and m==t)
        covered_skills  = sum(1 for sid,(m,t) in mastery.items() if t>0 and m>0)

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Skills mastered", mastered_skills)
    with c2: st.metric("Skills with progress", covered_skills)
    with c3: st.metric("Total skills", len(skills))

    st.caption("Node size & color scale with mastery. Arrows point from parent → sub-skill.")
    render_skill_tree_viz(skills, edges, mastery)
    #render_skill_tree_viz(skills, edges)



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
    elif st.session_state.page == "skills":
        render_skills()
    else:
        render_home()

if __name__ == "__main__":
    main()