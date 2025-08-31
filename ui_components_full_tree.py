import streamlit as st
from skill_tree import SKILL_TREE, TOPIC_GROUPS
from game_logic import TOPICS, get_topic_stats, is_topic_unlocked, start_topic_quiz
from firebase_utils import get_user_data

def render_full_skill_tree():
    """Render the full statistics skill tree view"""
    st.title("Complete Statistics Skill Tree")
    st.info("🎓 This shows the full learning path available in statistics. Topics will unlock as you progress!")
    
    # Get user data for progress tracking
    user_data = None
    if "user" in st.session_state and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
    
    # Back button
    prev_page = st.session_state.get("prev_page", "topics")
    back_text = "← Back to Topics" if prev_page == "topics" else "← Back to Home"
    if st.button(back_text, key="back_button"):
        st.session_state.page = prev_page
        if "prev_page" in st.session_state:
            del st.session_state.prev_page
        st.rerun()
    
    # Topic group selection
    selected_group = st.selectbox(
        "Select Topic Group",
        ["Foundations", "Probability", "Data Analysis", "Statistical Testing", "Advanced Methods"]
    )
    
    # Show topics in selected group
    st.markdown(f"### {selected_group}")
    for topic_name in TOPIC_GROUPS[selected_group]:
        if topic_name in SKILL_TREE:
            topic = SKILL_TREE[topic_name]
            with st.expander(f"📚 {topic_name}"):
                st.markdown(f"**Description:** {topic['description']}")
                
                # Show prerequisites
                if topic["prerequisites"]:
                    st.markdown("**Prerequisites:**")
                    for prereq in topic["prerequisites"]:
                        st.markdown(f"- {prereq}")
                
                # Show subtopics
                if topic.get("subtopics"):
                    st.markdown("**Subtopics:**")
                    for subtopic in topic["subtopics"]:
                        st.markdown(f"- {subtopic}")
                
                # Show points required
                st.markdown(f"**Points Required:** {topic['points_required']}")
                
                # Show quiz status and start button if available
                if topic_name in TOPICS:
                    if user_data and "questions" in st.session_state:
                        try:
                            stats = get_topic_stats(user_data, st.session_state.questions, topic_name)
                            is_unlocked = is_topic_unlocked(topic_name, user_data, st.session_state.questions)
                            
                            # Show progress
                            progress = (stats.get("mastered", 0) / stats.get("total_questions", 1)) * 100
                            st.progress(progress / 100)
                            st.caption(f"Progress: {progress:.0f}% ({stats.get('mastered', 0)}/{stats.get('total_questions', 0)} questions)")
                            
                            if is_unlocked:
                                if st.button("Start Quiz", key=f"full_tree_{topic_name}", use_container_width=True):
                                    start_topic_quiz(topic_name, st.session_state.questions)
                                    st.session_state.page = "quiz"
                                    st.rerun()
                            else:
                                st.warning(f"🔒 Need {topic['points_required']} points in prerequisites to unlock")
                        except Exception as e:
                            st.error(f"Error loading topic stats: {e}")
                    else:
                        st.success("✅ Available for quizzes")
                else:
                    st.info("🔜 Coming soon")
