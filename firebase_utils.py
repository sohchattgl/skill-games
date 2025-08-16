# firebase_utils.py
# Simple wrappers to interact with Firestore for this MVP.

import uuid
import hashlib
import time
from typing import Dict, List
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

_firestore_client = None

def init_firebase(service_account_json_path: str):
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client
    cred = credentials.Certificate(service_account_json_path)
    firebase_admin.initialize_app(cred)
    _firestore_client = firestore.client()
    return _firestore_client

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ----- Users -----
def create_user_record(email: str, display_name: str, password: str, db=None) -> Dict:
    db = db or _firestore_client
    users_ref = db.collection("users")
    doc = users_ref.document(email)
    # check exists
    if doc.get().exists:
        return {"ok": False, "error": "user-exists"}
    user_data = {
        "email": email,
        "display_name": display_name,
        "password_hash": hash_password(password),
        "best_score": 0,
        "answered_questions": [],  # list of question ids the user answered correctly in past
        "created_at": int(time.time())
    }
    doc.set(user_data)
    return {"ok": True, "user": user_data}

def authenticate_user(email: str, password: str, db=None) -> Dict:
    db = db or _firestore_client
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
    doc = db.collection("users").document(email).get()
    if not doc.exists:
        return None
    return doc.to_dict()

def update_user_best_and_answers(email: str, best_score: int, new_answered_ids: List[str], db=None):
    db = db or _firestore_client
    user_ref = db.collection("users").document(email)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return False
    data = user_doc.to_dict()
    prev_answers = set(data.get("answered_questions", []))
    prev_answers.update(new_answered_ids)
    new_best = max(data.get("best_score", 0), best_score)
    user_ref.update({
        "best_score": new_best,
        "answered_questions": list(prev_answers)
    })
    return True

# ----- Attempts logging -----
def log_attempt(email: str, attempt_doc: Dict, db=None):
    db = db or _firestore_client
    attempts_ref = db.collection("attempts")
    # generate attempt id
    attempt_id = attempt_doc.get("attempt_id", str(uuid.uuid4()))
    attempt_doc["attempt_id"] = attempt_id
    attempt_doc["user_email"] = email
    attempt_doc["created_at"] = int(time.time())
    attempts_ref.document(attempt_id).set(attempt_doc)
    return attempt_id

# ----- Leaderboard -----
def get_leaderboard(limit: int = 10, db=None):
    db = db or _firestore_client
    # We will query users by best_score desc
    users_ref = db.collection("users")
    q = users_ref.order_by("best_score", direction=firestore.Query.DESCENDING).limit(limit)
    docs = q.stream()
    out = []
    for d in docs:
        data = d.to_dict()
        out.append({
            "display_name": data.get("display_name"),
            "email": data.get("email"),
            "best_score": data.get("best_score", 0)
        })
    return out

def save_feedback(feedback_data):
    """Save user feedback to Firebase"""
    try:
        db = firestore.client()
        db.collection('feedback').add(feedback_data)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}