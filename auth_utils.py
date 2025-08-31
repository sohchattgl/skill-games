import streamlit as st
import time
from firebase_utils import authenticate_user, create_user_record

def render_auth(firebase_available: bool):
    """Handle authentication UI and logic"""
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

def logout():
    """Clean logout function"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session()

def init_session():
    """Initialize session state variables"""
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
