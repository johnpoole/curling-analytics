#!/usr/bin/env python
"""
Demonstration script showing how to extract shot success probabilities 
from the curling_data.db database to improve curlingeval.js logic.

This script shows:
1. How to query shot success rates by type
2. How to analyze situational factors affecting success
3. How to build empirical success models
4. How to export calibrated parameters to JavaScript
"""

import sqlite3
import pandas as pd
import numpy as np
import json

def analyze_shot_success_patterns(db_path):
    """Analyze shot success patterns from the curling database."""
    
    conn = sqlite3.connect(db_path)
    
    # Query 1: Base success rates by shot type
    shot_type_query = """
    SELECT 
        type,
        COUNT(*) as total_shots,
        AVG(percent_score) as avg_success,
        STDDEV(percent_score) as std_dev,
        MIN(percent_score) as min_success,
        MAX(percent_score) as max_success,
        -- Calculate quartiles for distribution analysis
        (SELECT percent_score FROM shots s2 WHERE s2.type = s.type 
         ORDER BY percent_score LIMIT 1 OFFSET (COUNT(*) * 25 / 100)) as q25,
        (SELECT percent_score FROM shots s2 WHERE s2.type = s.type 
         ORDER BY percent_score LIMIT 1 OFFSET (COUNT(*) * 75 / 100)) as q75
    FROM shots s
    WHERE percent_score IS NOT NULL 
    GROUP BY type
    HAVING COUNT(*) >= 30  -- Minimum sample size for reliability
    ORDER BY total_shots DESC
    """
    
    shot_types_df = pd.read_sql(shot_type_query, conn)
    
    # Query 2: Success rates by game situation
    situational_query = """
    SELECT 
        s.type,
        e.number as end_number,
        CASE 
            WHEN s.number <= 4 THEN 'early'
            WHEN s.number <= 12 THEN 'middle' 
            ELSE 'late'
        END as shot_phase,
        CASE
            WHEN ABS(g.final_score_red - g.final_score_yellow) <= 1 THEN 'close'
            WHEN ABS(g.final_score_red - g.final_score_yellow) <= 3 THEN 'moderate'
            ELSE 'blowout'
        END as game_closeness,
        COUNT(*) as shot_count,
        AVG(s.percent_score) as avg_success,
        STDDEV(s.percent_score) as std_dev
    FROM shots s
    JOIN ends e ON s.end_id = e.id
    JOIN games g ON e.game_id = g.id
    WHERE s.percent_score IS NOT NULL
        AND g.final_score_red IS NOT NULL 
        AND g.final_score_yellow IS NOT NULL
    GROUP BY s.type, e.number, shot_phase, game_closeness
    HAVING COUNT(*) >= 10
    ORDER BY s.type, end_number, shot_phase
    """
    
    situational_df = pd.read_sql(situational_query, conn)
    
    # Query 3: Player skill consistency
    player_skill_query = """
    SELECT 
        player_name,
        COUNT(DISTINCT end_id) as ends_played,
        COUNT(*) as total_shots,
        AVG(percent_score) as overall_avg,
        STDDEV(percent_score) as consistency,
        -- Success rate for different shot types
        AVG(CASE WHEN type LIKE '%Draw%' THEN percent_score END) as draw_avg,
        AVG(CASE WHEN type LIKE '%Take%' THEN percent_score END) as takeout_avg,
        COUNT(CASE WHEN type LIKE '%Draw%' THEN 1 END) as draw_count,
        COUNT(CASE WHEN type LIKE '%Take%' THEN 1 END) as takeout_count
    FROM shots
    WHERE percent_score IS NOT NULL
    GROUP BY player_name
    HAVING COUNT(*) >= 50  -- Players with significant sample size
    ORDER BY overall_avg DESC
    """
    
    player_skill_df = pd.read_sql(player_skill_query, conn)
    
    # Query 4: End pressure effects
    pressure_query = """
    SELECT 
        e.number as end_number,
        CASE 
            WHEN s.number >= 13 AND e.color_hammer = s.color THEN 'hammer_pressure'
            WHEN s.number >= 13 AND e.color_hammer != s.color THEN 'steal_pressure'
            WHEN s.number <= 4 THEN 'early_setup'
            ELSE 'mid_end'
        END as pressure_situation,
        COUNT(*) as shot_count,
        AVG(s.percent_score) as avg_success,
        STDDEV(s.percent_score) as std_dev
    FROM shots s
    JOIN ends e ON s.end_id = e.id
    WHERE s.percent_score IS NOT NULL
    GROUP BY end_number, pressure_situation
    HAVING COUNT(*) >= 10
    ORDER BY end_number, pressure_situation
    """
    
    pressure_df = pd.read_sql(pressure_query, conn)
    
    conn.close()
    
    return {
        'shot_types': shot_types_df,
        'situational': situational_df,
        'player_skill': player_skill_df,
        'pressure': pressure_df
    }

def calculate_success_modifiers(analysis_results):
    """Calculate modifier coefficients for the enhanced curlingeval.js"""
    
    shot_types_df = analysis_results['shot_types']
    situational_df = analysis_results['situational']
    pressure_df = analysis_results['pressure']
    
    # Base success rates by shot type
    base_success_rates = {}
    for _, row in shot_types_df.iterrows():
        # Convert 0-100 percentage to 0-1 probability
        base_success_rates[row['type']] = row['avg_success'] / 100.0
    
    # Calculate situational modifiers
    situational_modifiers = {}
    
    # Pressure effects
    baseline_success = pressure_df[pressure_df['pressure_situation'] == 'early_setup']['avg_success'].mean()
    hammer_pressure = pressure_df[pressure_df['pressure_situation'] == 'hammer_pressure']['avg_success'].mean()
    steal_pressure = pressure_df[pressure_df['pressure_situation'] == 'steal_pressure']['avg_success'].mean()
    
    if not pd.isna(baseline_success) and not pd.isna(hammer_pressure):
        situational_modifiers['HAMMER_PRESSURE'] = hammer_pressure / baseline_success
    
    if not pd.isna(baseline_success) and not pd.isna(steal_pressure):
        situational_modifiers['STEAL_PRESSURE'] = steal_pressure / baseline_success
    
    # End number effects (fatigue)
    early_ends = pressure_df[pressure_df['end_number'] <= 3]['avg_success'].mean()
    late_ends = pressure_df[pressure_df['end_number'] >= 8]['avg_success'].mean()
    
    if not pd.isna(early_ends) and not pd.isna(late_ends):
        situational_modifiers['FATIGUE_FACTOR'] = late_ends / early_ends
    
    # Shot phase effects
    phase_modifiers = {}
    for phase in ['early', 'middle', 'late']:
        phase_data = situational_df[situational_df['shot_phase'] == phase]
        if not phase_data.empty:
            phase_modifiers[phase] = phase_data['avg_success'].mean() / 100.0
    
    return {
        'base_success_rates': base_success_rates,
        'situational_modifiers': situational_modifiers,
        'phase_modifiers': phase_modifiers,
        'sample_sizes': {
            'shot_types': shot_types_df[['type', 'total_shots']].to_dict('records'),
            'total_shots_analyzed': shot_types_df['total_shots'].sum()
        }
    }

def export_to_javascript(modifiers, output_path):
    """Export calibrated parameters to JavaScript format for curlingeval.js"""
    
    js_content = f"""// Auto-generated shot success parameters from curling_data.db analysis
// Generated on {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}

// Base success rates by shot type (empirically derived)
export const EMPIRICAL_SHOT_SUCCESS = {json.dumps(modifiers['base_success_rates'], indent=2)};

// Situational modifiers (multiplicative factors)
export const SITUATIONAL_MODIFIERS_EMPIRICAL = {json.dumps(modifiers['situational_modifiers'], indent=2)};

// Shot phase modifiers
export const PHASE_MODIFIERS = {json.dumps(modifiers['phase_modifiers'], indent=2)};

// Data quality metrics
export const CALIBRATION_INFO = {json.dumps(modifiers['sample_sizes'], indent=2)};

// Helper function to get empirically calibrated success rate
export function getEmpiricalSuccessRate(shotType, situation = {{}}) {{
  let baseRate = EMPIRICAL_SHOT_SUCCESS[shotType] || 0.75;
  
  // Apply situational modifiers
  if (situation.isHammerPressure && SITUATIONAL_MODIFIERS_EMPIRICAL.HAMMER_PRESSURE) {{
    baseRate *= SITUATIONAL_MODIFIERS_EMPIRICAL.HAMMER_PRESSURE;
  }}
  
  if (situation.isStealPressure && SITUATIONAL_MODIFIERS_EMPIRICAL.STEAL_PRESSURE) {{
    baseRate *= SITUATIONAL_MODIFIERS_EMPIRICAL.STEAL_PRESSURE;
  }}
  
  if (situation.isLateGame && SITUATIONAL_MODIFIERS_EMPIRICAL.FATIGUE_FACTOR) {{
    baseRate *= SITUATIONAL_MODIFIERS_EMPIRICAL.FATIGUE_FACTOR;
  }}
  
  // Apply phase modifier if available
  if (situation.shotPhase && PHASE_MODIFIERS[situation.shotPhase]) {{
    const phaseBase = (PHASE_MODIFIERS.early + PHASE_MODIFIERS.middle + PHASE_MODIFIERS.late) / 3;
    const phaseModifier = PHASE_MODIFIERS[situation.shotPhase] / phaseBase;
    baseRate *= phaseModifier;
  }}
  
  return Math.max(0.1, Math.min(0.99, baseRate));
}}
"""
    
    with open(output_path, 'w') as f:
        f.write(js_content)
    
    print(f"JavaScript parameters exported to {output_path}")

def demonstrate_integration():
    """Demonstrate how the enhanced evaluation would work"""
    
    print("=== Curling Shot Success Probability Integration Demo ===\\n")
    
    # This would be the real database path
    db_path = 'curling_data.db'
    
    try:
        # In a real scenario with populated database:
        # analysis = analyze_shot_success_patterns(db_path)
        # modifiers = calculate_success_modifiers(analysis)
        # export_to_javascript(modifiers, 'empirical_shot_parameters.js')
        
        # For demonstration, create mock data showing what the analysis would find
        mock_analysis = {
            'Draw': {'base_success': 0.82, 'sample_size': 2150},
            'Take-out': {'base_success': 0.74, 'sample_size': 1890},
            'Hit and Roll': {'base_success': 0.68, 'sample_size': 945},
            'Guard': {'base_success': 0.85, 'sample_size': 1200},
            'Freeze': {'base_success': 0.61, 'sample_size': 380},
        }
        
        print("Mock Analysis Results (what real database analysis would show):")
        print("Shot Type\\t\\tBase Success\\tSample Size")
        print("-" * 50)
        for shot_type, stats in mock_analysis.items():
            print(f"{shot_type:<15}\\t{stats['base_success']:.1%}\\t\\t{stats['sample_size']}")
        
        print("\\nSituational Modifiers:")
        print("- Hammer pressure (final stones): -8% success rate")
        print("- Steal pressure: -12% success rate") 
        print("- Late game fatigue: -5% success rate")
        print("- Complex house (+4 stones): -15% success rate")
        
        print("\\nIntegration with curlingeval.js:")
        print("1. Calculate base position value (current logic)")
        print("2. For each potential shot, calculate success probability")
        print("3. Weight outcomes by P(success) × value(success) + P(failure) × value(failure)")
        print("4. Return enhanced evaluation with uncertainty quantification")
        
    except Exception as e:
        print(f"Database not accessible: {e}")
        print("Run populate_db.py first to create sample data")

if __name__ == "__main__":
    demonstrate_integration()