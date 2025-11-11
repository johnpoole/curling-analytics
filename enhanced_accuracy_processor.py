#!/usr/bin/env python

# -*- coding: utf-8 -*-
"""
Enhanced shot accuracy analyzer for World Curling data.
Calculates distance and direction accuracy metrics from stone position data
instead of just using percentage scores.

This script:
1. Infers intended target positions from shot types and context
2. Calculates distance and direction errors
3. Categorizes error patterns  
4. Populates enhanced accuracy tables
"""

import sqlite3
import pandas as pd
import numpy as np
import os
import database_functions as db

# Set the database path
os.environ["CADBPATH"] = os.path.join(os.getcwd(), "curling_data.db")

# Sheet dimensions and target zones (in meters, button-centered)
HOUSE_RADIUS = 1.829
SHEET_WIDTH = 4.88
TEE_TO_HOG = 6.40
BUTTON_X = 0.0
BUTTON_Y = 0.0

# Accuracy thresholds
DISTANCE_THRESHOLDS = {
    'on_target': 0.20,    # Within 20cm
    'close': 0.50,        # Within 50cm  
    'moderate': 1.00,     # Within 1m
    'large': float('inf') # Beyond 1m
}

DIRECTION_THRESHOLDS = {
    'on_line': 3.0,       # Within 3 degrees
    'slight': 8.0,        # Within 8 degrees
    'moderate': 15.0,     # Within 15 degrees
    'large': float('inf') # Beyond 15 degrees
}

class ShotTargetInferenceEngine:
    """Infers intended target positions from shot context."""
    
    def __init__(self):
        self.shot_type_targets = {
            'Draw': self._infer_draw_target,
            'Guard': self._infer_guard_target, 
            'Take-out': self._infer_takeout_target,
            'Hit and Roll': self._infer_hit_roll_target,
            'Freeze': self._infer_freeze_target,
            'Tap': self._infer_tap_target,
            'Peel': self._infer_peel_target
        }
    
    def infer_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer the intended target position for a shot."""
        
        shot_type = shot_data['type']
        
        if shot_type in self.shot_type_targets:
            return self.shot_type_targets[shot_type](
                shot_data, pre_shot_stones, post_shot_stones
            )
        else:
            # Default to button for unknown shot types
            return {'x': BUTTON_X, 'y': BUTTON_Y, 'confidence': 0.3}
    
    def _infer_draw_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for draw shots."""
        
        # Find the thrown stone (new stone in post-shot)
        thrown_stone = self._find_thrown_stone(shot_data, pre_shot_stones, post_shot_stones)
        
        if thrown_stone is None:
            return {'x': BUTTON_X, 'y': BUTTON_Y, 'confidence': 0.2}
        
        # For draws, target is likely the final resting position
        # unless it was significantly off-target
        final_x = thrown_stone['x']
        final_y = thrown_stone['y']
        
        # If stone ended in house, target was probably button area
        distance_to_button = np.sqrt(final_x**2 + final_y**2)
        
        if distance_to_button <= HOUSE_RADIUS:
            # Target was likely button or strategic position in house
            return {'x': final_x, 'y': final_y, 'confidence': 0.8}
        else:
            # Stone ended outside house, target was probably button
            return {'x': BUTTON_X, 'y': BUTTON_Y, 'confidence': 0.6}
    
    def _infer_guard_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for guard shots."""
        
        thrown_stone = self._find_thrown_stone(shot_data, pre_shot_stones, post_shot_stones)
        
        if thrown_stone is None:
            # Default guard position
            return {'x': 0.0, 'y': 3.5, 'confidence': 0.3}
        
        final_x = thrown_stone['x']
        final_y = thrown_stone['y']
        
        # Guards are typically placed between hog line and house
        if 1.5 <= final_y <= 6.0:
            # Stone ended in guard zone, target was likely the final position
            return {'x': final_x, 'y': final_y, 'confidence': 0.8}
        else:
            # Stone didn't end in expected guard zone
            # Target was probably center guard position
            return {'x': 0.0, 'y': 3.5, 'confidence': 0.5}
    
    def _infer_takeout_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for takeout shots."""
        
        # Find stones that were removed between shots
        removed_stones = self._find_removed_stones(pre_shot_stones, post_shot_stones)
        
        if removed_stones:
            # Target was likely the stone that was removed
            target_stone = removed_stones[0]  # Take first if multiple removed
            return {'x': target_stone['x'], 'y': target_stone['y'], 'confidence': 0.9}
        else:
            # No stones removed - missed takeout
            # Try to infer target from opponent stones that are close to thrown stone
            thrown_stone = self._find_thrown_stone(shot_data, pre_shot_stones, post_shot_stones)
            
            if thrown_stone:
                # Find closest opponent stone
                opponent_color = 'red' if shot_data['color'] == 'yellow' else 'yellow'
                opponent_stones = [s for s in pre_shot_stones if s['color'] == opponent_color]
                
                if opponent_stones:
                    distances = [
                        np.sqrt((s['x'] - thrown_stone['x'])**2 + (s['y'] - thrown_stone['y'])**2)
                        for s in opponent_stones
                    ]
                    closest_idx = np.argmin(distances)
                    closest_stone = opponent_stones[closest_idx]
                    
                    return {'x': closest_stone['x'], 'y': closest_stone['y'], 'confidence': 0.7}
            
            # Fallback to button
            return {'x': BUTTON_X, 'y': BUTTON_Y, 'confidence': 0.3}
    
    def _infer_hit_roll_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for hit and roll shots."""
        
        # Hit and roll has two targets: the stone to hit and final position
        # For simplicity, use the final position of the thrown stone as the primary target
        
        thrown_stone = self._find_thrown_stone(shot_data, pre_shot_stones, post_shot_stones)
        
        if thrown_stone:
            return {'x': thrown_stone['x'], 'y': thrown_stone['y'], 'confidence': 0.7}
        else:
            return {'x': BUTTON_X, 'y': BUTTON_Y, 'confidence': 0.4}
    
    def _infer_freeze_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for freeze shots."""
        
        thrown_stone = self._find_thrown_stone(shot_data, pre_shot_stones, post_shot_stones)
        
        if thrown_stone:
            # Find the closest stone to the thrown stone (the freeze target)
            other_stones = [s for s in post_shot_stones 
                           if not (s['x'] == thrown_stone['x'] and s['y'] == thrown_stone['y'])]
            
            if other_stones:
                distances = [
                    np.sqrt((s['x'] - thrown_stone['x'])**2 + (s['y'] - thrown_stone['y'])**2)
                    for s in other_stones
                ]
                closest_idx = np.argmin(distances)
                closest_stone = other_stones[closest_idx]
                
                # Target position is slightly behind the stone being frozen to
                target_x = (thrown_stone['x'] + closest_stone['x']) / 2
                target_y = (thrown_stone['y'] + closest_stone['y']) / 2
                
                return {'x': target_x, 'y': target_y, 'confidence': 0.8}
        
        return {'x': BUTTON_X, 'y': BUTTON_Y, 'confidence': 0.4}
    
    def _infer_tap_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for tap shots."""
        # Similar to takeout but lighter touch
        return self._infer_takeout_target(shot_data, pre_shot_stones, post_shot_stones)
    
    def _infer_peel_target(self, shot_data, pre_shot_stones, post_shot_stones):
        """Infer target for peel shots."""
        # Similar to takeout but removing guards
        return self._infer_takeout_target(shot_data, pre_shot_stones, post_shot_stones)
    
    def _find_thrown_stone(self, shot_data, pre_shot_stones, post_shot_stones):
        """Find the stone that was just thrown."""
        
        shooting_color = shot_data['color']
        
        # Count stones of shooting color before and after
        pre_count = len([s for s in pre_shot_stones if s['color'] == shooting_color])
        post_count = len([s for s in post_shot_stones if s['color'] == shooting_color])
        
        if post_count > pre_count:
            # New stone was added - find it
            pre_positions = set((s['x'], s['y']) for s in pre_shot_stones if s['color'] == shooting_color)
            
            for stone in post_shot_stones:
                if stone['color'] == shooting_color and (stone['x'], stone['y']) not in pre_positions:
                    return stone
        
        return None
    
    def _find_removed_stones(self, pre_shot_stones, post_shot_stones):
        """Find stones that were removed during the shot."""
        
        post_positions = set((s['color'], s['x'], s['y']) for s in post_shot_stones)
        removed = []
        
        for stone in pre_shot_stones:
            if (stone['color'], stone['x'], stone['y']) not in post_positions:
                removed.append(stone)
        
        return removed

def calculate_accuracy_metrics(shot_id, target, final_position):
    """Calculate distance and direction accuracy metrics."""
    
    # Distance error
    target_distance_error = np.sqrt(
        (final_position['x'] - target['x'])**2 + 
        (final_position['y'] - target['y'])**2
    )
    
    # Direction error (simplified)
    # Calculate angle from button to target vs angle from button to final position
    target_angle = np.arctan2(target['y'], target['x']) if target['x'] != 0 or target['y'] != 0 else 0
    final_angle = np.arctan2(final_position['y'], final_position['x']) if final_position['x'] != 0 or final_position['y'] != 0 else 0
    
    path_direction_error = abs(np.degrees(target_angle - final_angle))
    if path_direction_error > 180:
        path_direction_error = 360 - path_direction_error
    
    # Categorize errors
    distance_category = 'large'
    for category, threshold in DISTANCE_THRESHOLDS.items():
        if target_distance_error <= threshold:
            distance_category = category
            break
    
    direction_category = 'large'  
    for category, threshold in DIRECTION_THRESHOLDS.items():
        if path_direction_error <= threshold:
            direction_category = category
            break
    
    # Overall error magnitude
    if distance_category in ['on_target'] and direction_category in ['on_line', 'slight']:
        error_magnitude = 'minor'
    elif distance_category in ['on_target', 'close'] and direction_category in ['on_line', 'slight', 'moderate']:
        error_magnitude = 'moderate'
    else:
        error_magnitude = 'major'
    
    return {
        'target_distance_error': target_distance_error,
        'path_direction_error': path_direction_error,
        'distance_category': distance_category,
        'direction_category': direction_category,
        'error_magnitude': error_magnitude
    }

def process_shot_accuracy(shot_id):
    """Process accuracy metrics for a single shot."""
    
    conn = sqlite3.connect(os.getenv("CADBPATH"))
    
    # Get shot data
    shot_query = """
    SELECT s.*, e.number as end_number, g.id as game_id
    FROM shots s
    JOIN ends e ON s.end_id = e.id  
    JOIN games g ON e.game_id = g.id
    WHERE s.id = ?
    """
    
    shot_df = pd.read_sql(shot_query, conn, params=[shot_id])
    
    if shot_df.empty:
        conn.close()
        return None
    
    shot_data = shot_df.iloc[0]
    
    # Get stone positions before this shot
    if shot_data['number'] > 1:
        prev_shot_query = """
        SELECT sp.color, sp.x, sp.y
        FROM stone_positions sp
        JOIN shots s ON sp.shot_id = s.id
        WHERE s.end_id = ? AND s.number = ?
        """
        pre_shot_df = pd.read_sql(prev_shot_query, conn, 
                                 params=[shot_data['end_id'], shot_data['number'] - 1])
    else:
        pre_shot_df = pd.DataFrame(columns=['color', 'x', 'y'])
    
    # Get stone positions after this shot
    post_shot_query = """
    SELECT color, x, y 
    FROM stone_positions 
    WHERE shot_id = ?
    """
    post_shot_df = pd.read_sql(post_shot_query, conn, params=[shot_id])
    
    conn.close()
    
    if post_shot_df.empty:
        return None
    
    # Convert to list of dicts for easier processing
    pre_shot_stones = pre_shot_df.to_dict('records')
    post_shot_stones = post_shot_df.to_dict('records')
    
    # Infer target position
    inference_engine = ShotTargetInferenceEngine()
    target = inference_engine.infer_target(shot_data, pre_shot_stones, post_shot_stones)
    
    # Find final position of thrown stone
    thrown_stone = inference_engine._find_thrown_stone(shot_data, pre_shot_stones, post_shot_stones)
    
    if thrown_stone is None:
        return None
    
    # Calculate accuracy metrics
    metrics = calculate_accuracy_metrics(shot_id, target, thrown_stone)
    
    # Add additional data
    metrics.update({
        'shot_id': shot_id,
        'final_position_x': thrown_stone['x'],
        'final_position_y': thrown_stone['y'],
        'target_x': target['x'],
        'target_y': target['y'],
        'target_confidence': target['confidence']
    })
    
    return metrics

def populate_enhanced_accuracy_data():
    """Populate the enhanced accuracy tables with calculated metrics."""
    
    # Get all shots that have position data
    query = """
    SELECT DISTINCT s.id
    FROM shots s
    JOIN stone_positions sp ON s.id = sp.shot_id
    ORDER BY s.id
    LIMIT 100  -- Process first 100 shots as demonstration
    """
    
    shot_ids = db.run_query(query)['id'].tolist()
    
    print(f"Processing accuracy metrics for {len(shot_ids)} shots...")
    
    processed_count = 0
    for shot_id in shot_ids:
        metrics = process_shot_accuracy(shot_id)
        
        if metrics:
            # Insert into shot_accuracy_metrics table
            insert_query = """
            INSERT INTO shot_accuracy_metrics (
                shot_id, target_distance_error, final_position_x, final_position_y,
                path_direction_error, distance_category, direction_category,
                error_magnitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            try:
                conn = sqlite3.connect(os.getenv("CADBPATH"))
                conn.execute(insert_query, [
                    metrics['shot_id'],
                    metrics['target_distance_error'],
                    metrics['final_position_x'], 
                    metrics['final_position_y'],
                    metrics['path_direction_error'],
                    metrics['distance_category'],
                    metrics['direction_category'],
                    metrics['error_magnitude']
                ])
                conn.commit()
                conn.close()
                
                processed_count += 1
                if processed_count % 10 == 0:
                    print(f"  Processed {processed_count} shots...")
                    
            except Exception as e:
                print(f"Error inserting metrics for shot {shot_id}: {e}")
    
    print(f"✓ Processed accuracy metrics for {processed_count} shots")

def demonstrate_enhanced_analysis():
    """Show sample analysis using the enhanced accuracy data."""
    
    print("\\nEnhanced Accuracy Analysis Results:")
    print("="*50)
    
    # Sample analysis queries
    queries = [
        {
            'name': 'Average Distance Errors by Shot Type',
            'query': """
            SELECT 
                s.type,
                COUNT(*) as shot_count,
                ROUND(AVG(sam.target_distance_error), 3) as avg_distance_error_m,
                ROUND(AVG(sam.path_direction_error), 1) as avg_direction_error_deg
            FROM shots s
            JOIN shot_accuracy_metrics sam ON s.id = sam.shot_id
            GROUP BY s.type
            ORDER BY avg_distance_error_m
            """
        },
        {
            'name': 'Error Pattern Distribution',
            'query': """
            SELECT 
                distance_category,
                direction_category, 
                COUNT(*) as frequency,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM shot_accuracy_metrics), 1) as percentage
            FROM shot_accuracy_metrics
            GROUP BY distance_category, direction_category
            ORDER BY frequency DESC
            """
        },
        {
            'name': 'Accuracy by Error Magnitude',
            'query': """
            SELECT 
                error_magnitude,
                COUNT(*) as shot_count,
                ROUND(AVG(target_distance_error), 3) as avg_distance_m,
                ROUND(AVG(path_direction_error), 1) as avg_direction_deg
            FROM shot_accuracy_metrics
            GROUP BY error_magnitude
            ORDER BY avg_distance_m
            """
        }
    ]
    
    for analysis in queries:
        print(f"\\n{analysis['name']}:")
        print("-" * len(analysis['name']))
        try:
            results = db.run_query(analysis['query'])
            if not results.empty:
                print(results.to_string(index=False))
            else:
                print("  No data available yet - run populate_enhanced_accuracy_data()")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    print("Enhanced Shot Accuracy Analysis for World Curling Data")
    print("="*60)
    
    # Check if we have any shots to process
    try:
        shot_count = db.run_query("SELECT COUNT(*) as count FROM shots")['count'][0]
        print(f"Found {shot_count} shots in database")
        
        if shot_count > 0:
            print("\\nProcessing enhanced accuracy metrics...")
            populate_enhanced_accuracy_data()
            
            print("\\nRunning sample analysis...")
            demonstrate_enhanced_analysis()
        else:
            print("\\nNo shot data found. Run populate_db.py first to load World Curling data.")
            
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure the database is properly set up and contains shot data.")