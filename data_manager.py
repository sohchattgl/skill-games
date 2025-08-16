"""
Data Manager for Quiz Bot MVP
Handles persistent storage, user data, and session logging
"""

import json
import csv
import hashlib
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import uuid

class DataManager:
    def __init__(self, data_dir: str = "data"):
        """Initialize data manager with data directory"""
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.sessions_log = os.path.join(data_dir, "sessions.csv")
        self.user_progress_file = os.path.join(data_dir, "user_progress.json")
        
        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize files
        self._init_data_files()
    
    def _init_data_files(self):
        """Initialize data files if they don't exist"""
        # Initialize users file
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                json.dump({}, f)
        
        # Initialize user progress file
        if not os.path.exists(self.user_progress_file):
            with open(self.user_progress_file, 'w') as f:
                json.dump({}, f)
        
        # Initialize sessions log file
        if not os.path.exists(self.sessions_log):
            with open(self.sessions_log, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'session_id', 'username', 'start_time', 'end_time',
                    'questions_attempted', 'questions_correct', 'final_score',
                    'starting_level', 'ending_level', 'best_score_achieved'
                ])
    
    def hash_password(self, password: str) -> str:
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username: str, password: str) -> bool:
        """Register a new user"""
        users = self.load_users()
        
        if username in users:
            return False  # User already exists
        
        users[username] = {
            'password': self.hash_password(password),
            'created_at': datetime.now().isoformat(),
            'best_score': 0,
            'total_sessions': 0
        }
        
        # Save users
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2)
        
        # Initialize user progress
        user_progress = self.load_user_progress()
        user_progress[username] = {
            'answered_correctly': [],  # Questions answered correctly (ever)
            'current_difficulty': 'easy',
            'answered_questions': [],  # Current session questions
            'session_score': 0,
            'session_correct_count': {'easy': 0, 'medium': 0, 'hard': 0},
            'best_score': 0,
            'session_start_time': None
        }
        
        with open(self.user_progress_file, 'w') as f:
            json.dump(user_progress, f, indent=2)
        
        return True
    
    def authenticate_user(self, username: str, password: str) -> bool:
        """Authenticate user"""
        users = self.load_users()
        if username not in users:
            return False
        return users[username]['password'] == self.hash_password(password)
    
    def load_users(self) -> Dict:
        """Load users from file"""
        try:
            with open(self.users_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def load_user_progress(self) -> Dict:
        """Load user progress from file"""
        try:
            with open(self.user_progress_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_user_progress(self, user_progress: Dict):
        """Save user progress to file"""
        with open(self.user_progress_file, 'w') as f:
            json.dump(user_progress, f, indent=2)
    
    def get_user_progress(self, username: str) -> Dict:
        """Get progress for specific user"""
        all_progress = self.load_user_progress()
        return all_progress.get(username, {
            'answered_correctly': [],
            'current_difficulty': 'easy',
            'answered_questions': [],
            'session_score': 0,
            'session_correct_count': {'easy': 0, 'medium': 0, 'hard': 0},
            'best_score': 0,
            'session_start_time': None
        })
    
    def update_user_progress(self, username: str, progress: Dict):
        """Update progress for specific user"""
        all_progress = self.load_user_progress()
        all_progress[username] = progress
        self.save_user_progress(all_progress)
    
    def start_session(self, username: str) -> str:
        """Start a new quiz session and return session ID"""
        session_id = str(uuid.uuid4())
        
        # Update user progress with session start
        progress = self.get_user_progress(username)
        progress['session_start_time'] = datetime.now().isoformat()
        progress['session_id'] = session_id
        
        # Reset session-specific data
        progress['answered_questions'] = []
        progress['session_score'] = 0
        progress['session_correct_count'] = {'easy': 0, 'medium': 0, 'hard': 0}
        progress['current_difficulty'] = 'easy'
        
        self.update_user_progress(username, progress)
        return session_id
    
    def end_session(self, username: str, session_data: Dict):
        """End quiz session and log results"""
        progress = self.get_user_progress(username)
        users = self.load_users()
        
        session_id = progress.get('session_id', 'unknown')
        start_time = progress.get('session_start_time')
        end_time = datetime.now().isoformat()
        
        # Update best scores
        final_score = session_data.get('final_score', 0)
        if final_score > progress['best_score']:
            progress['best_score'] = final_score
            users[username]['best_score'] = final_score
        
        # Update total sessions
        users[username]['total_sessions'] = users[username].get('total_sessions', 0) + 1
        
        # Save updated user data
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2)
        
        self.update_user_progress(username, progress)
        
        # Log session to CSV
        self.log_session({
            'session_id': session_id,
            'username': username,
            'start_time': start_time,
            'end_time': end_time,
            'questions_attempted': len(session_data.get('questions_attempted', [])),
            'questions_correct': session_data.get('questions_correct', 0),
            'final_score': final_score,
            'starting_level': 'easy',  # Always start at easy
            'ending_level': session_data.get('ending_level', 'easy'),
            'best_score_achieved': progress['best_score']
        })
        
        return session_id
    
    def log_session(self, session_data: Dict):
        """Log session data to CSV file"""
        with open(self.sessions_log, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                session_data.get('session_id', ''),
                session_data.get('username', ''),
                session_data.get('start_time', ''),
                session_data.get('end_time', ''),
                session_data.get('questions_attempted', 0),
                session_data.get('questions_correct', 0),
                session_data.get('final_score', 0),
                session_data.get('starting_level', 'easy'),
                session_data.get('ending_level', 'easy'),
                session_data.get('best_score_achieved', 0)
            ])
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get leaderboard based on best scores"""
        users = self.load_users()
        leaderboard = []
        
        for username, user_data in users.items():
            leaderboard.append({
                'username': username,
                'best_score': user_data.get('best_score', 0),
                'total_sessions': user_data.get('total_sessions', 0)
            })
        
        # Sort by best score (descending)
        leaderboard.sort(key=lambda x: x['best_score'], reverse=True)
        return leaderboard[:limit]
    
    def get_session_logs(self, username: Optional[str] = None) -> List[Dict]:
        """Get session logs, optionally filtered by username"""
        logs = []
        
        try:
            with open(self.sessions_log, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if username is None or row['username'] == username:
                        logs.append(row)
        except FileNotFoundError:
            pass
        
        return logs
    
    def get_user_stats(self, username: str) -> Dict:
        """Get comprehensive user statistics"""
        users = self.load_users()
        progress = self.get_user_progress(username)
        session_logs = self.get_session_logs(username)
        
        if username not in users:
            return {}
        
        return {
            'username': username,
            'created_at': users[username].get('created_at'),
            'best_score': users[username].get('best_score', 0),
            'total_sessions': users[username].get('total_sessions', 0),
            'questions_mastered': len(progress.get('answered_correctly', [])),
            'session_logs': session_logs
        }