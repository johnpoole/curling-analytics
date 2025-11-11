#!/usr/bin/env python

# -*- coding: utf-8 -*-
"""
Enhanced database schema for curling shot accuracy analysis.
Adds detailed accuracy metrics including distance and direction error
instead of just percentage scores.

This script creates additional tables and columns to capture:
1. Intended target position for each shot
2. Actual final position (already available)  
3. Distance error (meters from intended target)
4. Direction error (angular deviation from intended path)
5. Categorized error types (short/long, left/right, etc.)
"""
import database_functions as db
import os

# Set the database path
os.environ["CADBPATH"] = os.path.join(os.getcwd(), "curling_data.db")

def create_enhanced_accuracy_tables():
    """Create additional tables for detailed shot accuracy analysis."""
    
    # Add new columns to existing shots table
    c = """
    ALTER TABLE shots ADD COLUMN target_x REAL;
    """
    try:
        db.run_command(c)
        print("Added target_x column to shots table")
    except:
        print("target_x column already exists or error adding it")
    
    c = """
    ALTER TABLE shots ADD COLUMN target_y REAL;
    """
    try:
        db.run_command(c)
        print("Added target_y column to shots table")
    except:
        print("target_y column already exists or error adding it")
    
    c = """
    ALTER TABLE shots ADD COLUMN intended_outcome TEXT;
    """
    try:
        db.run_command(c)
        print("Added intended_outcome column to shots table")
    except:
        print("intended_outcome column already exists or error adding it")

    # Create enhanced accuracy metrics table
    c = """
    CREATE TABLE IF NOT EXISTS shot_accuracy_metrics(
        id INTEGER PRIMARY KEY,
        shot_id INTEGER,
        -- Distance metrics
        target_distance_error REAL,  -- meters from intended target
        final_position_x REAL,       -- actual final x position
        final_position_y REAL,       -- actual final y position
        -- Direction metrics  
        path_direction_error REAL,   -- angular deviation in degrees
        lateral_displacement REAL,   -- perpendicular distance from intended line
        -- Categorized errors
        distance_category TEXT,      -- 'short', 'long', 'on_target'
        direction_category TEXT,     -- 'left', 'right', 'on_line'  
        error_magnitude TEXT,        -- 'minor', 'moderate', 'major'
        -- Shot outcome analysis
        achieved_outcome TEXT,       -- what actually happened
        outcome_success BOOLEAN,     -- did shot achieve intended outcome
        partial_success_score REAL,  -- 0-1 scale for partial success
        -- Contextual factors
        difficulty_rating REAL,     -- 0-1 scale based on shot complexity
        pressure_factor REAL,       -- 0-1 scale based on game situation
        ice_conditions TEXT,         -- if available from data
        FOREIGN KEY (shot_id) REFERENCES shots(id)
    );
    """
    db.run_command(c)
    print("Created shot_accuracy_metrics table")

    # Create shot intention analysis table
    c = """
    CREATE TABLE IF NOT EXISTS shot_intentions(
        id INTEGER PRIMARY KEY,
        shot_id INTEGER,
        -- Intended strategy
        primary_intention TEXT,      -- 'score', 'guard', 'remove', 'position'
        secondary_intention TEXT,    -- backup plan if primary fails
        target_stone_id INTEGER,     -- which stone to hit (if applicable)
        intended_final_position_x REAL,  -- where shooting stone should end up
        intended_final_position_y REAL,
        -- Execution parameters
        ideal_velocity REAL,         -- optimal speed for shot
        ideal_curl_amount REAL,      -- expected curl distance
        margin_for_error REAL,       -- acceptable deviation radius
        -- Risk assessment
        risk_level TEXT,             -- 'low', 'medium', 'high'
        backup_options INTEGER,      -- number of alternative outcomes
        failure_cost REAL,           -- penalty for missing (position value)
        FOREIGN KEY (shot_id) REFERENCES shots(id)
    );
    """
    db.run_command(c)
    print("Created shot_intentions table")

    # Create enhanced stone tracking table
    c = """
    CREATE TABLE IF NOT EXISTS stone_movements(
        id INTEGER PRIMARY KEY,
        shot_id INTEGER,
        stone_color TEXT,
        -- Before shot position
        initial_x REAL,
        initial_y REAL,
        initial_in_play BOOLEAN,
        -- After shot position  
        final_x REAL,
        final_y REAL,
        final_in_play BOOLEAN,
        -- Movement analysis
        displacement_distance REAL,  -- how far stone moved
        displacement_direction REAL, -- angle of movement
        movement_type TEXT,          -- 'removed', 'displaced', 'stationary'
        -- Impact analysis
        was_target BOOLEAN,          -- was this the intended target
        impact_velocity REAL,        -- estimated impact speed
        impact_angle REAL,           -- angle of collision
        FOREIGN KEY (shot_id) REFERENCES shots(id)
    );
    """
    db.run_command(c)
    print("Created stone_movements table")

def add_accuracy_analysis_views():
    """Create views for common accuracy analysis queries."""
    
    # View for shot accuracy summary
    c = """
    CREATE VIEW IF NOT EXISTS shot_accuracy_summary AS
    SELECT 
        s.id as shot_id,
        s.type,
        s.player_name,
        s.percent_score,
        sam.target_distance_error,
        sam.path_direction_error,
        sam.distance_category,
        sam.direction_category,
        sam.error_magnitude,
        sam.outcome_success,
        sam.partial_success_score,
        -- Calculate composite accuracy score
        CASE 
            WHEN sam.outcome_success = 1 THEN 
                CASE sam.error_magnitude
                    WHEN 'minor' THEN 0.9 + sam.partial_success_score * 0.1
                    WHEN 'moderate' THEN 0.7 + sam.partial_success_score * 0.2  
                    ELSE 0.5 + sam.partial_success_score * 0.2
                END
            ELSE sam.partial_success_score * 0.5
        END as composite_accuracy
    FROM shots s
    LEFT JOIN shot_accuracy_metrics sam ON s.id = sam.shot_id;
    """
    db.run_command(c)
    print("Created shot_accuracy_summary view")

    # View for player performance analysis
    c = """
    CREATE VIEW IF NOT EXISTS player_accuracy_stats AS
    SELECT 
        s.player_name,
        s.type as shot_type,
        COUNT(*) as total_shots,
        AVG(sam.target_distance_error) as avg_distance_error,
        AVG(sam.path_direction_error) as avg_direction_error,
        AVG(CASE WHEN sam.outcome_success = 1 THEN 1.0 ELSE 0.0 END) as success_rate,
        AVG(sam.partial_success_score) as avg_partial_success,
        STDDEV(sam.target_distance_error) as distance_consistency,
        STDDEV(sam.path_direction_error) as direction_consistency,
        -- Error pattern analysis
        SUM(CASE WHEN sam.distance_category = 'short' THEN 1 ELSE 0 END) as short_errors,
        SUM(CASE WHEN sam.distance_category = 'long' THEN 1 ELSE 0 END) as long_errors,
        SUM(CASE WHEN sam.direction_category = 'left' THEN 1 ELSE 0 END) as left_errors,
        SUM(CASE WHEN sam.direction_category = 'right' THEN 1 ELSE 0 END) as right_errors
    FROM shots s
    JOIN shot_accuracy_metrics sam ON s.id = sam.shot_id
    WHERE sam.target_distance_error IS NOT NULL
    GROUP BY s.player_name, s.type
    HAVING COUNT(*) >= 10;
    """
    db.run_command(c)
    print("Created player_accuracy_stats view")

def create_sample_data():
    """Create some sample data to demonstrate the enhanced accuracy system."""
    
    print("\nSample enhanced accuracy data structure:")
    print("="*60)
    
    # Sample shot accuracy metrics
    sample_accuracy = [
        {
            'shot_type': 'Draw',
            'target_distance_error': 0.15,  # 15cm from target
            'path_direction_error': 2.3,    # 2.3 degrees off line
            'distance_category': 'on_target',
            'direction_category': 'right', 
            'error_magnitude': 'minor',
            'outcome_success': True,
            'partial_success_score': 0.92
        },
        {
            'shot_type': 'Take-out', 
            'target_distance_error': 0.45,  # 45cm miss
            'path_direction_error': 8.7,    # 8.7 degrees off
            'distance_category': 'short',
            'direction_category': 'left',
            'error_magnitude': 'moderate', 
            'outcome_success': False,
            'partial_success_score': 0.35   # Partial hit
        },
        {
            'shot_type': 'Hit and Roll',
            'target_distance_error': 0.08,  # 8cm from ideal final position  
            'path_direction_error': 1.1,    # 1.1 degrees off
            'distance_category': 'on_target',
            'direction_category': 'on_line',
            'error_magnitude': 'minor',
            'outcome_success': True, 
            'partial_success_score': 0.98
        }
    ]
    
    for i, shot in enumerate(sample_accuracy, 1):
        print(f"Shot {i}: {shot['shot_type']}")
        print(f"  Distance Error: {shot['target_distance_error']:.2f}m ({shot['distance_category']})")
        print(f"  Direction Error: {shot['path_direction_error']:.1f}° ({shot['direction_category']})")
        print(f"  Success: {'Yes' if shot['outcome_success'] else 'No'} (Partial: {shot['partial_success_score']:.2f})")
        print(f"  Error Magnitude: {shot['error_magnitude']}")
        print()

def demonstrate_analysis_capabilities():
    """Show what kinds of analysis the enhanced schema enables."""
    
    print("Enhanced Analysis Capabilities:")
    print("="*40)
    
    print("\n1. DISTANCE ACCURACY PATTERNS")
    print("   - Player tends to be 12cm short on draws")
    print("   - Takeout attempts average 18cm miss distance") 
    print("   - Hit-and-roll final position error: 23cm average")
    
    print("\n2. DIRECTION ACCURACY PATTERNS") 
    print("   - Consistent 3.2° bias to the right")
    print("   - Left-handed vs right-handed error patterns")
    print("   - Ice condition effects on curl accuracy")
    
    print("\n3. SITUATIONAL ACCURACY")
    print("   - Pressure shots: +15% distance error")
    print("   - Complex house: +22% direction error")
    print("   - End-game situations: -8% success rate")
    
    print("\n4. LEARNING INSIGHTS")
    print("   - Which errors are most costly to game outcomes")
    print("   - Optimal risk/reward balance for each player")
    print("   - Training focus areas for improvement")
    
    print("\n5. STRATEGY OPTIMIZATION") 
    print("   - Account for player-specific error patterns")
    print("   - Choose shots based on execution probability")
    print("   - Adaptive strategy based on current performance")

if __name__ == "__main__":
    print("Creating enhanced curling accuracy database schema...")
    print("=" * 60)
    
    try:
        create_enhanced_accuracy_tables()
        print("\n✓ Enhanced tables created successfully")
        
        add_accuracy_analysis_views() 
        print("✓ Analysis views created successfully")
        
        print("\n" + "="*60)
        create_sample_data()
        
        print("="*60) 
        demonstrate_analysis_capabilities()
        
        print("\n" + "="*60)
        print("✓ Enhanced accuracy schema setup complete!")
        print("\nNext steps:")
        print("1. Modify populate_db.py to calculate accuracy metrics")
        print("2. Create shot target inference algorithm") 
        print("3. Build enhanced curlingeval.js integration")
        
    except Exception as e:
        print(f"Error creating enhanced schema: {e}")
        print("Make sure curling_data.db exists and is accessible")