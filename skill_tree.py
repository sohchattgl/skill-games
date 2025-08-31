from typing import Dict, List, Set
import streamlit as st

# Full Statistics Skill Tree Structure
SKILL_TREE = {
    "Basic Algebra": {
        "id": "basic_algebra",
        "prerequisites": [],
        "points_required": 0,
        "level": 1,
        "description": "Fundamental algebraic concepts",
        "subtopics": ["Set Theory"],
        "learning_outcomes": [
            "Understand basic algebraic operations",
            "Master equation solving",
            "Apply algebraic concepts to real problems"
        ]
    },
    "Set Theory": {
        "id": "set_theory",
        "prerequisites": ["basic_algebra"],
        "points_required": 1,
        "description": "Mathematical foundations of sets",
        "subtopics": ["Mathematical Notation", "Fundamental Probability Concepts"]
    },
    "Probability Basics": {
        "id": "probability_basics",
        "prerequisites": ["set_theory"],
        "points_required": 2,
        "description": "Core probability concepts",
        "subtopics": ["Types of Data", "Independence and Dependence"]
    },
    "Statistical Thinking": {
        "id": "statistical_thinking",
        "prerequisites": ["probability_basics"],
        "points_required": 2,
        "description": "Foundation of statistical reasoning",
        "subtopics": ["Data Management", "Continuous Distributions"]
    },
    "Data Visualization": {
        "id": "data_visualization",
        "prerequisites": ["statistical_thinking"],
        "points_required": 2,
        "description": "Techniques for visualizing data",
        "subtopics": ["Statistical Software", "Correlation Analysis"]
    },
    "Hypothesis Testing": {
        "id": "hypothesis_testing",
        "prerequisites": ["statistical_thinking"],
        "points_required": 3,
        "description": "Concepts of statistical hypothesis testing",
        "subtopics": ["One Sample T-Test", "Two Sample T-Test", "P-value and Significance"]
    },
    "Linear Regression": {
        "id": "linear_regression",
        "prerequisites": ["hypothesis_testing"],
        "points_required": 3,
        "description": "Simple linear regression analysis",
        "subtopics": ["Regression Methods", "Model Selection"]
    },
    "Advanced Topics": {
        "id": "advanced_topics",
        "prerequisites": ["linear_regression"],
        "points_required": 4,
        "description": "Advanced statistical concepts",
        "subtopics": ["ANOVA", "Factor Analysis", "Multivariate Analysis"]
    }
}

# Topic groupings for the dropdown interface
TOPIC_GROUPS = {
    "Foundations": ["Basic Algebra", "Set Theory"],
    "Probability": ["Probability Basics", "Independence and Dependence"],
    "Data Analysis": ["Statistical Thinking", "Data Visualization"],
    "Statistical Testing": ["Hypothesis Testing", "One Sample T-Test", "Two Sample T-Test"],
    "Advanced Methods": ["Linear Regression", "ANOVA", "Factor Analysis"]
}

@st.cache_data
def get_topic_dependencies(topic_id: str) -> List[str]:
    """Get all prerequisites for a given topic"""
    topic = next((t for t in SKILL_TREE.values() if t["id"] == topic_id), None)
    if not topic:
        return []
    
    prereqs = topic.get("prerequisites", [])
    all_prereqs = set(prereqs)  # Use set for better performance
    
    for prereq in prereqs:
        all_prereqs.update(get_topic_dependencies(prereq))
    
    return list(all_prereqs)

@st.cache_data
def get_unlocked_topics(completed_topics: Set[str]) -> List[str]:
    """Get list of topics that can be unlocked based on completed topics"""
    unlocked = []
    
    for topic_name, topic in SKILL_TREE.items():
        # Check if all prerequisites are completed
        if all(prereq in completed_topics for prereq in topic["prerequisites"]):
            # Check if enough points are earned
            points_earned = sum(SKILL_TREE[completed]["points_required"] 
                              for completed in completed_topics 
                              if completed in topic["prerequisites"])
            if points_earned >= topic["points_required"]:
                unlocked.append(topic_name)
                
    return sorted(unlocked, key=lambda x: SKILL_TREE[x].get("level", 0))

def calculate_topic_progress(user_data: Dict) -> Dict[str, float]:
    """Calculate progress percentage for each topic"""
    progress = {}
    
    for topic_name, topic in SKILL_TREE.items():
        if not topic["prerequisites"]:
            progress[topic_name] = 100.0  # Root topics are 100% unlockable
            continue
            
        total_points_needed = topic["points_required"]
        if total_points_needed == 0:
            progress[topic_name] = 100.0
            continue
            
        points_earned = sum(SKILL_TREE[prereq]["points_required"]
                          for prereq in topic["prerequisites"]
                          if prereq in (user_data.get("completed_topics", [])))
                          
        progress[topic_name] = min(100.0, (points_earned / total_points_needed) * 100)
    
    return progress
