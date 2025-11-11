#!/usr/bin/env python
"""
Generate substantial mock curling data to populate the database with realistic shot patterns
"""

import sqlite3
import random
import numpy as np
import os

def generate_large_dataset():
    """Generate thousands of realistic curling shots"""
    
    print("Generating large dataset of curling shots...")
    
    # Initialize database connection
    conn = sqlite3.connect('curling_data.db')
    
    # Clear existing data
    conn.execute("DELETE FROM stone_positions")
    conn.execute("DELETE FROM shots")
    conn.execute("DELETE FROM ends")
    conn.execute("DELETE FROM games")
    conn.execute("DELETE FROM shot_accuracy_metrics")
    
    # Generate multiple tournaments/games
    game_id = 1
    shot_id = 1
    
    # Tournament parameters
    num_tournaments = 5
    games_per_tournament = 20
    ends_per_game = 8
    shots_per_end = 16
    
    for tournament in range(num_tournaments):
        print(f"  Generating tournament {tournament + 1}/{num_tournaments}")
        
        for game in range(games_per_tournament):
            # Insert game
            conn.execute("""
                INSERT INTO games (id, event_id, session, name, sheet, type, start_date, start_time, team_red, team_yellow, final_score_red, final_score_yellow)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [game_id, tournament+1, "Session_1", f"Game_{game_id}", f"Sheet_{game%4+1}", "Round Robin", "2024-01-01", "10:00", f"Team_A_{game}", f"Team_B_{game}", random.randint(5,12), random.randint(5,12)])
            
            for end_num in range(1, ends_per_game + 1):
                # Insert end
                end_id = (game_id - 1) * ends_per_game + end_num
                conn.execute("""
                    INSERT INTO ends (id, game_id, number, direction, color_hammer, score_red, score_yellow, time_left_red, time_left_yellow)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [end_id, game_id, end_num, 1, "red" if end_num % 2 == 1 else "yellow", random.randint(0, 3), random.randint(0, 3), 38*60, 38*60])
                
                for shot_num in range(1, shots_per_end + 1):
                    # Determine shot characteristics based on shot number and strategy
                    team = "red" if shot_num % 2 == 1 else "yellow"
                    
                    # Shot type probabilities based on game situation
                    if shot_num <= 4:  # Early shots - more guards
                        shot_type = random.choices(
                            ["Draw", "Guard", "Take-out", "Hit and Roll"],
                            weights=[30, 50, 15, 5]
                        )[0]
                    elif shot_num <= 12:  # Mid-game - mixed strategy
                        shot_type = random.choices(
                            ["Draw", "Guard", "Take-out", "Hit and Roll", "Freeze"],
                            weights=[40, 20, 25, 10, 5]
                        )[0]
                    else:  # Late shots - more aggressive
                        shot_type = random.choices(
                            ["Draw", "Guard", "Take-out", "Hit and Roll"],
                            weights=[35, 10, 40, 15]
                        )[0]
                    
                    # Generate realistic shot parameters based on type
                    if shot_type == "Draw":
                        weight = np.random.normal(1.9, 0.1)
                        target_distance_error = np.random.gamma(2, 0.08)  # Gamma for right-skewed distribution
                        direction_error = np.random.normal(0, 3.5)
                        success_rate = 0.75
                    elif shot_type == "Guard":
                        weight = np.random.normal(2.1, 0.15)
                        target_distance_error = np.random.gamma(1.5, 0.12)
                        direction_error = np.random.normal(0, 4.2)
                        success_rate = 0.68
                    elif shot_type == "Take-out":
                        weight = np.random.normal(2.8, 0.2)
                        target_distance_error = np.random.gamma(3, 0.25)  # Higher variability
                        direction_error = np.random.normal(0, 8.5)
                        success_rate = 0.52
                    elif shot_type == "Hit and Roll":
                        weight = np.random.normal(2.4, 0.18)
                        target_distance_error = np.random.gamma(2.5, 0.15)
                        direction_error = np.random.normal(0, 6.2)
                        success_rate = 0.58
                    else:  # Freeze
                        weight = np.random.normal(1.85, 0.12)
                        target_distance_error = np.random.gamma(1.8, 0.06)
                        direction_error = np.random.normal(0, 2.8)
                        success_rate = 0.42
                    
                    # Clamp values to reasonable ranges
                    weight = max(1.5, min(3.2, weight))
                    target_distance_error = max(0.0, min(3.0, target_distance_error))
                    direction_error = max(-25, min(25, abs(direction_error)))
                    
                    # Success determination
                    is_successful = random.random() < success_rate
                    percent_score = random.randint(70, 95) if is_successful else random.randint(20, 50)
                    
                    # Insert shot
                    conn.execute("""
                        INSERT INTO shots (id, end_id, number, color, team, player_name, type, turn, percent_score, target_x, target_y, intended_outcome)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [shot_id, end_id, shot_num, team, team, f"Player_{shot_num%4+1}", shot_type, "out" if random.random() > 0.5 else "in", percent_score, np.random.normal(0, 1), np.random.normal(15, 2), shot_type])
                    
                    # Generate stone positions (simplified)
                    final_x = np.random.normal(0, 1.5)
                    final_y = np.random.normal(15, 3)  # Rough house area
                    
                    conn.execute("""
                        INSERT INTO stone_positions (shot_id, color, x, y)
                        VALUES (?, ?, ?, ?)
                    """, [shot_id, team, final_x, final_y])
                    
                    # Insert accuracy metrics
                    conn.execute("""
                        INSERT OR REPLACE INTO shot_accuracy_metrics (
                            shot_id, target_distance_error, final_position_x, final_position_y,
                            path_direction_error, distance_category, direction_category,
                            error_magnitude, outcome_success, partial_success_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        shot_id, target_distance_error, final_x, final_y, direction_error,
                        "on_target" if target_distance_error < 0.2 else "short" if target_distance_error < 0.5 else "long",
                        "on_line" if abs(direction_error) < 3 else "left" if direction_error < 0 else "right",
                        "minor" if target_distance_error < 0.3 else "moderate" if target_distance_error < 0.8 else "major",
                        1 if is_successful else 0,
                        percent_score / 100.0
                    ])
                    
                    shot_id += 1
            
            game_id += 1
    
    conn.commit()
    conn.close()
    
    total_shots = (num_tournaments * games_per_tournament * ends_per_game * shots_per_end)
    print(f"✓ Generated {total_shots:,} shots across {num_tournaments} tournaments")
    
    # Show summary
    verify_dataset()

def verify_dataset():
    """Verify the generated dataset"""
    conn = sqlite3.connect('curling_data.db')
    
    # Shot counts by type
    cursor = conn.execute("""
        SELECT type, COUNT(*) as count, 
               AVG(sam.target_distance_error) as avg_dist_error,
               AVG(sam.path_direction_error) as avg_dir_error
        FROM shots s
        JOIN shot_accuracy_metrics sam ON s.id = sam.shot_id
        GROUP BY s.type
        ORDER BY count DESC
    """)
    
    print("\nDataset Summary:")
    print("Shot Type      | Count  | Avg Dist Error | Avg Dir Error")
    print("-" * 55)
    
    for row in cursor.fetchall():
        shot_type, count, dist_err, dir_err = row
        print(f"{shot_type:<14} | {count:>5} | {dist_err:>13.3f}m | {dir_err:>12.1f}°")
    
    # Total counts
    total_shots = conn.execute("SELECT COUNT(*) FROM shots").fetchone()[0]
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    
    print(f"\nTotal: {total_shots:,} shots from {total_games} games")
    
    conn.close()

if __name__ == "__main__":
    generate_large_dataset()