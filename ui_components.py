import streamlit as st
import time
from firebase_utils import get_user_data, get_leaderboard_cached, get_user_attempts, get_attempts_cached
from game_logic import (
    TOPICS,
    get_topic_stats,
    is_topic_unlocked,
    start_topic_quiz
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

def render_header():
    """Render the app header"""
    st.markdown("""
    <div style='text-align: center; padding: 1rem 0; margin-bottom: 2rem;'>
        <h1>🦫 Capybara Quiz</h1>
        <p style='color: #666; margin: 0;'>Fast. Smart. Adaptive.</p>
    </div>
    """, unsafe_allow_html=True)

def render_nav():
    """Render navigation buttons"""
    col1, col2, col3, col4 = st.columns(4)
    
    try:
        with col1:
            if st.button("🏠 Home", use_container_width=True, key="nav_home"):
                if st.session_state.game_active:
                    st.warning("You have an active quiz. End it first?")
                st.session_state.page = "home"
                st.rerun()
                
        with col2:
            if st.button("🏆 Board", use_container_width=True, key="nav_board"):
                if st.session_state.game_active:
                    st.warning("End current quiz to view leaderboard?")
                st.session_state.page = "leaderboard"
                st.rerun()
                
        with col3:
            if st.session_state.game_active:
                if st.button("⏹️ End Quiz", use_container_width=True, type="secondary", key="nav_end"):
                    # This will be handled by the main app
                    st.session_state.page = "results"
                    st.rerun()
            else:
                if st.button("📚 Topics", use_container_width=True, type="primary", key="nav_topics"):
                    st.session_state.page = "topics"
                    st.rerun()
                    
        with col4:
            if st.button("🚪 Logout", use_container_width=True, key="nav_logout"):
                if st.session_state.game_active:
                    st.warning("End current quiz and logout?")
                # Logout will be handled by the main app
                st.session_state.page = "home"
                st.rerun()
    except Exception as e:
        st.error(f"Navigation error: {str(e)}")
        # Ensure we can still navigate even if there's an error
        if col4.button("🚪 Emergency Home", use_container_width=True, key="emergency_home"):
            st.session_state.page = "home"
            st.rerun()

def render_home(firebase_available: bool, questions: list):
    """Render home page"""
    st.markdown("### 🎯 Welcome to Capybara Quiz!")
    st.write("Your personalized statistics learning journey awaits.")
    
    # Show recent updates/features
    with st.expander("🎉 What's New", expanded=True):
        st.markdown("""
        **Latest Updates:**
        - 🌳 New Skill Tree System: Visual progression path
        - 📊 Enhanced Statistics: Track your performance across topics
        - 🎯 Adaptive Difficulty: Questions adjust to your level
        - 📈 Performance Insights: Detailed analytics and recommendations
        """)
    
    if firebase_available and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
        leaderboard = get_leaderboard_cached()
        
        if user_data:
            # Get user stats
            best_score = user_data.get("best_score", 0)
            answered_questions = user_data.get("answered_questions", [])
            answered_count = len(answered_questions)
            total_questions = len(questions)
            
            # Calculate percentiles
            if leaderboard:
                all_scores = [user["best_score"] for user in leaderboard]
                score_percentile = (sum(1 for x in all_scores if x <= best_score) / len(all_scores)) * 100
                
                all_mastered = [len(get_user_data(user["email"]).get("answered_questions", [])) 
                              for user in leaderboard if get_user_data(user["email"])]
                mastery_percentile = (sum(1 for x in all_mastered if x <= answered_count) / len(all_mastered)) * 100
            
            # Display stats in single column - full width
            st.markdown("### 🏆 Your Stats")
            if best_score > 0:
                st.success(f"Best Score: {best_score} points")
                if leaderboard:
                    st.caption(f"Better than {score_percentile:.1f}% of users")
            
            if answered_count > 0:
                st.info(f"Questions Mastered: {answered_count}/{total_questions}")
                if leaderboard:
                    st.caption(f"Better than {mastery_percentile:.1f}% of users")
            
            # Show topic progress
            st.markdown("#### 📚 Topic Progress")
            for topic in TOPICS.keys():
                stats = get_topic_stats(user_data, questions, topic)
                progress = (stats.get("mastered", 0) / stats.get("total_questions", 1)) * 100
                st.markdown(f"**{topic}**: {progress:.0f}% complete")
                st.progress(progress / 100)
            
            # Bloom's Taxonomy Progress - Expanded
            st.markdown("### 🧠 Bloom's Taxonomy Progress")
            attempts = get_attempts_cached(st.session_state.user["email"])
            
            if attempts and len(attempts) > 0:
                # Get all questions from all attempts for comprehensive bloom analysis
                all_questions = []
                for attempt in attempts:
                    if "questions_attempted" in attempt:
                        all_questions.extend(attempt["questions_attempted"])
                
                if all_questions:
                    bloom_stats = get_bloom_progress(all_questions)
                    if bloom_stats:
                        for level, stats in bloom_stats.items():
                            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
                            st.markdown(f"**{level.title()}**")
                            st.progress(accuracy / 100)
                            st.caption(f"{stats['correct']}/{stats['total']} correct ({accuracy:.0f}%)")
                    else:
                        st.info("No Bloom's taxonomy data available yet.")
                else:
                    st.info("Start taking quizzes to see your cognitive skill progression!")
            else:
                st.info("Start taking quizzes to see your cognitive skill progression!")
            
            # Performance History - moved below bloom
            st.markdown("### 📈 Performance History")
            
            if attempts and len(attempts) > 0:
                try:
                    # Plot performance history
                    fig = plot_performance_history(attempts)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Plotting error: {str(e)}")
                    # Fallback to simple display if plotting fails
                    st.markdown("#### Recent Quiz Attempts")
                    try:
                        for i, attempt in enumerate(attempts[-5:]):  # Show last 5 attempts
                            # Try different field names for score
                            score = (attempt.get("total_points") or 
                                    attempt.get("score") or 
                                    attempt.get("points") or 0)
                            
                            # Try different field names for timestamp
                            timestamp = (attempt.get("created_at") or 
                                       attempt.get("timestamp") or 
                                       attempt.get("date") or "Unknown")
                            
                            # Try different field names for topic
                            topic = (attempt.get("topic") or 
                                    attempt.get("category") or 
                                    "General Quiz")
                            
                            # Format timestamp if it's a number
                            if isinstance(timestamp, (int, float)):
                                try:
                                    import pandas as pd
                                    timestamp = pd.to_datetime(timestamp, unit='s').strftime('%Y-%m-%d %H:%M')
                                except:
                                    timestamp = "Recent"
                            
                            st.write(f"**{topic}**: {score} points ({timestamp})")
                    except Exception as fallback_error:
                        st.error(f"Fallback display failed: {str(fallback_error)}")
                        st.write("Raw attempts data:", attempts[:2])  # Show first 2 for debugging
            else:
                st.info("No quiz attempts yet. Start your first quiz to see your progress!")
                
            # Recommendations section
            st.markdown("### 📋 Next Steps")
            col1, col2, col3 = st.columns(3)
            
            remaining = total_questions - answered_count
            with col1:
                if remaining > 0:
                    st.info(f"📝 {remaining} new questions available!")
                else:
                    st.success("🎓 All questions mastered!")
                    
            with col2:
                next_topic = next((topic for topic in TOPICS if 
                    is_topic_unlocked(topic, user_data, questions) and 
                    get_topic_stats(user_data, questions, topic)["mastered"] < 
                    get_topic_stats(user_data, questions, topic)["total_questions"]), None)
                if next_topic:
                    if st.button(f"Continue {next_topic}", key="continue_topic", use_container_width=True):
                        start_topic_quiz(next_topic, questions)
                        st.rerun()
                        
            with col3:
                if st.button("🎓 View Full Skill Tree", use_container_width=True, key="view_tree"):
                    st.session_state.update({
                        "page": "full_skill_tree",
                        "prev_page": "home"
                    })
                    st.rerun()
        else:
            st.warning("Start your journey by attempting your first quiz!")

def render_leaderboard():
    """Render leaderboard page"""
    st.markdown("### 🏆 Leaderboard")
    
    leaderboard = get_leaderboard_cached()
    if not leaderboard:
        st.info("No scores yet!")
        return
    
    for i, user in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        st.write(f"{medal} **{user['display_name']}** — {user['best_score']} pts")

def render_topic_box(topic: str, stats: dict, is_unlocked: bool, points_required: int, button_key_prefix: str = ""):
    """Render a single topic box with stats and unlock status"""
    with st.container():
        st.markdown(f"""
        <div style='padding: 1rem; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 1rem;'>
            <h3>{topic} {" 🔒" if not is_unlocked else ""}</h3>
            <p>{TOPICS[topic]["description"]}</p>
            <div style='display: flex; justify-content: space-between; margin-bottom: 0.5rem;'>
                <span>Points: {stats.get("points", 0)}/{stats.get("total_points", 0)}</span>
                <span>Mastered: {stats.get("mastered", 0)}/{stats.get("total_questions", 0)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if is_unlocked:
            if st.button("Start Quiz", key=f"{button_key_prefix}_{TOPICS[topic]['id']}", use_container_width=True):
                start_topic_quiz(topic, st.session_state.questions)
                st.rerun()
        else:
            st.info(f"🔒 Complete {points_required} points in prerequisite topics to unlock")

from ui_components_full_tree import render_full_skill_tree

def render_topics(questions: list, firebase_available: bool):
    """Render the topics selection page with skill tree"""
    if st.session_state.page == "full_skill_tree":
        render_full_skill_tree()
        return
        
    st.title("Statistics Topics")
    
    # Get user data for progress tracking
    user_data = None
    if firebase_available and st.session_state.user:
        user_data = get_user_data(st.session_state.user["email"])
        
    # Add button to view full skill tree
    if st.button("🎓 View Full Skill Tree", use_container_width=True, key="view_full_tree"):
        st.session_state.update({
            "page": "full_skill_tree",
            "prev_page": "topics"
        })
        st.rerun()
        
    st.markdown("### Current Available Topics")
        
    # Render root topic
    root_topic = "Hypothesis Testing"
    stats = get_topic_stats(user_data, questions, root_topic)
    is_unlocked = is_topic_unlocked(root_topic, user_data, questions)
    render_topic_box(root_topic, stats, is_unlocked, TOPICS[root_topic]["points_required"], "root")
    
    # Visual separator
    st.markdown('<div style="border-left: 2px dashed #ccc; height: 2rem; margin: 0 auto;"></div>', unsafe_allow_html=True)
    
    # Render child topics row
    st.markdown('<div style="display: flex; justify-content: center; gap: 2rem;">', unsafe_allow_html=True)
    for topic in ["One Sample T-Test", "Two Sample T-Test"]:
        stats = get_topic_stats(user_data, questions, topic)
        is_unlocked = is_topic_unlocked(topic, user_data, questions)
        points_needed = TOPICS[topic]["points_required"]
        render_topic_box(topic, stats, is_unlocked, points_needed, f"child_{topic.lower().replace(' ', '_')}")
    st.markdown('</div>', unsafe_allow_html=True)

def render_results(attempt_meta: dict, firebase_available: bool, user_data: dict):
    # Show quiz completion header
    st.markdown("### 🎉 Quiz Complete!")
    
    # Generate metrics
    metrics = generate_performance_metrics(attempt_meta)
    
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
    
    # Difficulty Breakdown
    st.subheader("Question Difficulty Breakdown")
    try:
        diff_stats = get_difficulty_breakdown(attempt_meta["questions_attempted"])
        if diff_stats:
            diff_cols = st.columns(3)
            diff_map = {"1": "Easy", "2": "Medium", "3": "Hard"}
            for i, (diff, stats) in enumerate(diff_stats.items()):
                with diff_cols[i]:
                    correct_percent = (stats["correct"]/stats["total"]*100) if stats["total"] else 0
                    st.metric(
                        diff_map.get(str(diff), "Easy"),
                        f"{stats['correct']}/{stats['total']}", 
                        f"{correct_percent:.0f}%"
                    )
        else:
            st.info("No difficulty breakdown available for this attempt.")
    except Exception as e:
        st.warning(f"Could not generate difficulty breakdown: {str(e)}")
        # Show raw difficulty data for debugging
        if attempt_meta.get("questions_attempted"):
            st.write("Available question data fields:", list(attempt_meta["questions_attempted"][0].keys()) if attempt_meta["questions_attempted"] else "No questions")
    
    # Concept Performance
    st.subheader("🎯 Topic Performance")
    concept_stats = get_concept_performance(attempt_meta["questions_attempted"])
    if concept_stats:
        fig = plot_concept_performance(concept_stats)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No topic data available for this attempt.")
    
    # Strengths & Areas to Improve
    analysis = analyze_strengths_weaknesses(concept_stats)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💪 Strengths")
        if analysis["strengths"]:
            for concept, acc, _ in analysis["strengths"]:
                st.success(f"✓ {concept} ({acc:.0%} accuracy)")
        else:
            st.info("Keep practicing to develop your strengths!")
    
    with col2:
        st.subheader("🎯 Areas to Improve")
        if analysis["weaknesses"]:
            for concept, acc, _ in analysis["weaknesses"]:
                st.error(f"△ {concept} ({acc:.0%} accuracy)")
        else:
            st.success("Great job! No weak areas identified.")
    
    # Bloom's Taxonomy Progress - Expanded
    st.subheader("🧠 Bloom's Taxonomy Progress")
    bloom_stats = get_bloom_progress(attempt_meta["questions_attempted"])
    if bloom_stats:
        for level, stats in bloom_stats.items():
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
            st.markdown(f"**{level.title()}**")
            st.progress(accuracy / 100)
            st.caption(f"{stats['correct']}/{stats['total']} correct ({accuracy:.0f}%)")
    else:
        st.info("No taxonomy data available for this attempt.")
    
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
    st.markdown("### 📚 Recommendations")
    if analysis["weaknesses"]:
        recommendations = generate_recommendations(analysis["weaknesses"])
        for rec in recommendations:
            col1, col2 = st.columns([3, 1])
            with col1:
                if rec["type"] == "lecture":
                    st.info(f"📺 {rec['title']}")
                else:
                    st.warning(f"✍️ {rec['title']}")
            with col2:
                st.button("Start →", key=f"rec_{hash(rec['title'])}", use_container_width=True)
    else:
        st.success("🎯 You're doing great! Try some harder questions to challenge yourself!")