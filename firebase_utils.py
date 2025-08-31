import uuid
import hashlib
import time
from typing import Dict, List
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
from report_utils import (
    get_concept_performance,
    get_bloom_progress,
    get_difficulty_breakdown
)

_firestore_client = None

def init_firebase(service_account_json_path: str):
    """Initialize Firebase safely and set global _firestore_client"""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    if not firebase_admin._apps:  # prevent duplicate init
        cred = credentials.Certificate(service_account_json_path)
        firebase_admin.initialize_app(cred)
    _firestore_client = firestore.client()
    return _firestore_client

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ----- Users -----
@st.cache_data(ttl=5)  # Short cache to prevent stale data
def get_user_data(email: str, db=None) -> Dict:
    """Get user data from Firebase"""
    if not email:
        return None
    user = get_user(email, db)
    if user:
        # Ensure all required fields exist
        user.setdefault("best_score", 0)
        user.setdefault("answered_questions", [])
        user.setdefault("topic_progress", {})
    return user

def create_user_record(email: str, display_name: str, password: str, db=None) -> Dict:
    db = db or _firestore_client
    if db is None:
        return {"ok": False, "error": "Firestore not initialized"}
    users_ref = db.collection("users")
    doc = users_ref.document(email)
    if doc.get().exists:
        return {"ok": False, "error": "user-exists"}
    user_data = {
        "email": email,
        "display_name": display_name,
        "password_hash": hash_password(password),
        "best_score": 0,
        "answered_questions": [],
        "created_at": int(time.time())
    }
    doc.set(user_data)
    return {"ok": True, "user": user_data}

def authenticate_user(email: str, password: str, db=None) -> Dict:
    db = db or _firestore_client
    if db is None:
        return {"ok": False, "error": "Firestore not initialized"}
    doc_ref = db.collection("users").document(email)
    doc = doc_ref.get()
    if not doc.exists:
        return {"ok": False, "error": "no-user"}
    data = doc.to_dict()
    if data.get("password_hash") == hash_password(password):
        return {"ok": True, "user": data}
    return {"ok": False, "error": "wrong-password"}

def get_user(email: str, db=None):
    db = db or _firestore_client
    if db is None:
        return None
    doc = db.collection("users").document(email).get()
    return doc.to_dict() if doc.exists else None

def update_user_best_and_answers(email: str, best_score: int, new_answered_ids: List[str], updated_data: Dict = None, db=None):
    db = db or _firestore_client
    if db is None:
        return False
    user_ref = db.collection("users").document(email)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return False
    
    data = user_doc.to_dict()
    prev_answers = set(data.get("answered_questions", []))
    prev_answers.update(new_answered_ids)
    new_best = max(data.get("best_score", 0), best_score)
    
    update_data = {
        "best_score": new_best,
        "answered_questions": list(prev_answers)
    }
    
    # Update topic progress if provided
    if updated_data and 'topic_progress' in updated_data:
        data['topic_progress'] = updated_data['topic_progress']
        update_data['topic_progress'] = updated_data['topic_progress']
    
    user_ref.update(update_data)
    return True

# ----- Attempts logging -----
@st.cache_data(ttl=60)
def get_attempts_cached(email: str, limit: int = 10) -> List[Dict]:
    """Get cached attempts data"""
    return get_user_attempts(email, limit)

def log_attempt(email: str, attempt_doc: Dict, db=None):
    """Add additional fields for enhanced reporting and save to Firestore"""
    db = db or _firestore_client
    if db is None:
        return

    # Clear the cache to ensure fresh data
    get_attempts_cached.clear()
    
    attempts_ref = db.collection("attempts")
    attempt_id = attempt_doc.get("attempt_id", str(uuid.uuid4()))

    # Normalize questions_attempted keys (concept vs concepts)
    for q in attempt_doc.get("questions_attempted", []):
        if "concepts" not in q and "concept" in q:
            q["concepts"] = q.get("concept", [])

    # Ensure we have timestamps
    current_time = int(time.time())
    attempt_doc["timestamp"] = current_time
    if "end_time" not in attempt_doc:
        attempt_doc["end_time"] = current_time
    
    # Add analytics fields
    attempt_doc.update({
        "attempt_id": attempt_id,
        "user_email": email,
        "created_at": current_time,
        "timestamp": current_time,  # Add this for consistent sorting
        "end_time": attempt_doc.get("end_time", current_time),
        "concept_stats": get_concept_performance(attempt_doc.get("questions_attempted", [])),
        "bloom_stats": get_bloom_progress(attempt_doc.get("questions_attempted", [])),
        "difficulty_stats": get_difficulty_breakdown(attempt_doc.get("questions_attempted", [])),
        "topics": list(set(q.get("topic") for q in attempt_doc.get("questions_attempted", []) if q.get("topic"))),
    })

    attempts_ref.document(attempt_id).set(attempt_doc)
    return attempt_id

# ----- Cache Management -----
def clear_cache():
    """Clear all cached data for the current user"""
    st.cache_data.clear()
    st.cache_resource.clear()

# ----- Leaderboard -----
@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_leaderboard_cached(limit: int = 10):
    """Get cached leaderboard data"""
    return get_leaderboard(limit)

def get_leaderboard(limit: int = 10, db=None):
    db = db or _firestore_client
    if db is None:
        return []
    users_ref = db.collection("users")
    q = users_ref.order_by("best_score", direction=firestore.Query.DESCENDING).limit(limit)
    return [d.to_dict() for d in q.stream()]

def save_feedback(feedback_data):
    db = _firestore_client
    if db is None:
        return {"ok": False, "error": "Firestore not initialized"}
    try:
        db.collection('feedback').add(feedback_data)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@st.cache_data(ttl=60)
def get_user_attempts(email: str, limit: int = 10, db=None) -> List[Dict]:
    """Get user's previous attempts across all topics with enhanced error handling and caching"""
    db = db or _firestore_client
    if db is None:
        st.error("Database connection not available")
        return []
        
    attempts_ref = db.collection("attempts")
    
    try:
        # Try ordered query first (fast when index exists)
        try:
            query = (attempts_ref
                    .where("user_email", "==", email)
                    .order_by("end_time", direction=firestore.Query.DESCENDING)
                    .limit(limit))
            docs = list(query.stream())
        except Exception:
            # Fallback: query without ordering then sort in memory (avoids index requirement)
            docs = list(attempts_ref.where("user_email", "==", email).limit(100).stream())

        attempts = []
        for doc in docs:
            attempt = doc.to_dict()
            # Ensure topic is included (some attempts store topic on root or per-question)
            if 'topic' not in attempt and 'questions_attempted' in attempt:
                questions = attempt['questions_attempted']
                if questions:
                    attempt['topic'] = questions[0].get('topic', 'Unknown')
            attempts.append(attempt)

        # Sort by end_time or timestamp in-memory to ensure consistent ordering
        attempts.sort(key=lambda x: x.get("end_time", x.get("timestamp", 0)), reverse=True)
        return attempts[:limit]
        
    except Exception as e:
        st.error(f"Error fetching attempts: {str(e)}")
        return []
