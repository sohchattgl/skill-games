from typing import List, Dict
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

def generate_performance_metrics(attempt_data: Dict) -> Dict:
    """Generate basic performance metrics"""
    try:
        questions = attempt_data.get("questions_attempted", [])
        total_questions = len(questions)
        correct_questions = sum(1 for q in questions if q.get("correct", False))
        
        return {
            "total_questions": total_questions,
            "correct_questions": correct_questions,
            "accuracy": (correct_questions/total_questions*100) if total_questions else 0,
            "points": attempt_data.get("total_points", 0),
            "time_taken": attempt_data.get("duration", 0)
        }
    except Exception as e:
        st.error(f"Error generating metrics: {e}")
        return {}

def get_difficulty_breakdown(questions: List[Dict]) -> Dict:
    """Break down performance by difficulty level"""
    difficulty_stats = {
        "1": {"total": 0, "correct": 0},
        "2": {"total": 0, "correct": 0},
        "3": {"total": 0, "correct": 0}
    }
    
    if not questions:
        return difficulty_stats
        
    for q in questions:
        # Handle both string IDs and question objects
        if isinstance(q, str):
            # If it's just an ID string, we can't determine difficulty
            diff = "1"  # Default to easy
        else:
            # If it's a question object, get difficulty
            diff = str(q.get("difficulty", 1))
        
        difficulty_stats[diff]["total"] += 1
        if isinstance(q, dict) and q.get("correct", False):
            difficulty_stats[diff]["correct"] += 1
    
    return difficulty_stats

def get_concept_performance(questions: List[Dict]) -> Dict:
    """Analyze performance by concept"""
    concept_stats = {}
    
    for q in questions:
        concepts = q.get("concepts", [])
        points = q.get("pts_awarded", 0)
        
        for concept in concepts:
            if concept not in concept_stats:
                concept_stats[concept] = {
                    "attempts": 0,
                    "correct": 0,
                    "points": 0,
                    "total_possible": 0
                }
            
            concept_stats[concept]["attempts"] += 1
            concept_stats[concept]["correct"] += 1 if q.get("correct", False) else 0
            concept_stats[concept]["points"] += points
            concept_stats[concept]["total_possible"] += q.get("difficulty", 1)  # max points possible
    
    return concept_stats

def analyze_strengths_weaknesses(concept_stats: Dict, threshold_strength=0.7, threshold_weakness=0.4) -> Dict:
    """Identify strengths and weaknesses based on concept performance"""
    strengths = []
    weaknesses = []
    
    for concept, stats in concept_stats.items():
        accuracy = stats["correct"] / stats["attempts"] if stats["attempts"] > 0 else 0
        points_ratio = stats["points"] / stats["total_possible"] if stats["total_possible"] > 0 else 0
        
        if accuracy >= threshold_strength and points_ratio >= threshold_strength:
            strengths.append((concept, accuracy, points_ratio))
        elif accuracy <= threshold_weakness or points_ratio <= threshold_weakness:
            weaknesses.append((concept, accuracy, points_ratio))
    
    return {
        "strengths": sorted(strengths, key=lambda x: x[1], reverse=True)[:3],
        "weaknesses": sorted(weaknesses, key=lambda x: x[1])[:3]
    }

def get_bloom_progress(questions: List[Dict]) -> Dict:
    """Analyze progress in Bloom's taxonomy levels"""
    bloom_stats = {}
    
    for q in questions:
        # Handle different types of question data
        if isinstance(q, dict):
            bloom = q.get("bloom", "remember").lower()
            is_correct = q.get("correct", False)
        else:
            # For non-dict types, skip
            continue
        
        if bloom not in bloom_stats:
            bloom_stats[bloom] = {"total": 0, "correct": 0}
        
        bloom_stats[bloom]["total"] += 1
        if is_correct:
            bloom_stats[bloom]["correct"] += 1
    
    return bloom_stats

def generate_recommendations(weaknesses: List[tuple]) -> List[Dict]:
    """Generate personalized recommendations based on weaknesses"""
    recommendations = []
    
    for concept, _, _ in weaknesses:
        recommendations.append({
            "type": "lecture",
            "title": f"Review Lecture: {concept}",
            "link": f"#lecture-{concept.lower().replace(' ', '-')}",
            "status": "open"
        })
        recommendations.append({
            "type": "practice",
            "title": f"Practice Set: {concept} (10 Qs)",
            "link": f"#practice-{concept.lower().replace(' ', '-')}",
            "status": "open"
        })
    
    return recommendations[:5]  # Limit to top 5 recommendations

def plot_performance_history(attempts: List[Dict]) -> go.Figure:
    """Plot historical performance"""
    if not attempts:
        fig = go.Figure()
        fig.add_annotation(
            text="No history available yet",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False
        )
        return fig

    df = pd.DataFrame(attempts)
    df['created_at'] = pd.to_datetime(df['created_at'], unit='s')
    df = df.sort_values('created_at')
    
    # Calculate 7-day moving average
    df['ma7'] = df['total_points'].rolling(window=7, min_periods=1).mean()
    
    # Add correct and total questions
    df['accuracy'] = df.apply(
        lambda row: len([q for q in row.get('questions_attempted', []) if q.get('correct', False)]) / 
                   len(row.get('questions_attempted', []))
        if row.get('questions_attempted') else 0, 
        axis=1
    )
    df['accuracy'] = df['accuracy'] * 100
    
    fig = go.Figure()
    
    # Plot individual scores
    fig.add_trace(go.Scatter(
        x=df['created_at'],
        y=df['total_points'],
        mode='markers',
        name='Score',
        marker=dict(
            size=8,
            color=df['accuracy'],
            colorscale='RdYlGn',
            showscale=True,
            colorbar=dict(
                title="Accuracy %"
            )
        ),
        hovertemplate='Points: %{y}<br>Accuracy: %{marker.color:.1f}%<br>Date: %{x|%Y-%m-%d %H:%M:%S}<extra></extra>'
    ))
    
    # Plot moving average
    fig.add_trace(go.Scatter(
        x=df['created_at'],
        y=df['ma7'],
        mode='lines',
        name='7-Day Avg',
        line=dict(
            color='rgba(100, 100, 100, 0.5)',
            dash='dot'
        ),
        hovertemplate='Avg: %{y:.1f}<br>Date: %{x|%Y-%m-%d %H:%M:%S}<extra></extra>'
    ))
    
    fig.update_layout(
        title="Quiz Performance History",
        xaxis_title="Date",
        yaxis_title="Points",
        showlegend=True,
        hovermode='closest',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=50)
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.1)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.1)')
    
    return fig

def plot_concept_performance(concept_stats: Dict) -> go.Figure:
    """Create bar chart for concept performance"""
    if not concept_stats:
        # Return empty figure with message if no data
        fig = go.Figure()
        fig.add_annotation(
            text="No concept data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False
        )
        return fig

    # Sort concepts by attempts and accuracy
    sorted_concepts = sorted(
        concept_stats.items(),
        key=lambda x: (x[1]["attempts"], x[1]["correct"]/x[1]["attempts"] if x[1]["attempts"] > 0 else 0),
        reverse=True
    )
    
    # Take top 10 most attempted concepts
    top_concepts = sorted_concepts[:10]
    
    concepts = []
    accuracies = []
    hover_text = []
    
    for concept, stats in top_concepts:
        concepts.append(concept)
        acc = stats["correct"] / stats["attempts"] if stats["attempts"] > 0 else 0
        accuracies.append(acc * 100)
        hover_text.append(f"Concept: {concept}<br>Accuracy: {acc*100:.0f}%<br>Correct: {stats['correct']}/{stats['attempts']}")
    
    fig = go.Figure(go.Bar(
        x=concepts,
        y=accuracies,
        text=[f"{acc:.0f}%" for acc in accuracies],
        textposition='auto',
        hovertext=hover_text,
        hoverinfo='text'
    ))
    
    fig.update_layout(
        title="Concept Performance (Top 10)",
        xaxis_title="Concept",
        yaxis_title="Accuracy (%)",
        showlegend=False,
        xaxis_tickangle=-45
    )
    return fig