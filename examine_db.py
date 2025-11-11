#!/usr/bin/env python
import sqlite3

conn = sqlite3.connect('curling_data.db')
cursor = conn.cursor()

# Get table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print('Tables:', tables)

# Examine shots table structure
cursor.execute("PRAGMA table_info(shots)")
print('\nShots table columns:')
for row in cursor.fetchall():
    print(f'  {row[1]} ({row[2]})')

# Get sample shots data with percentage scores
cursor.execute("""
    SELECT type, percent_score, COUNT(*) as count
    FROM shots 
    WHERE percent_score IS NOT NULL 
    GROUP BY type, percent_score 
    ORDER BY type, percent_score
    LIMIT 20
""")
print('\nSample shot types and success rates:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}% - {row[2]} shots')

# Get summary statistics
cursor.execute("""
    SELECT 
        type,
        COUNT(*) as total_shots,
        AVG(percent_score) as avg_success,
        MIN(percent_score) as min_success,
        MAX(percent_score) as max_success
    FROM shots 
    WHERE percent_score IS NOT NULL 
    GROUP BY type
    ORDER BY total_shots DESC
    LIMIT 10
""")
print('\nShot type success statistics:')
print('Type\t\t\tTotal\tAvg%\tMin%\tMax%')
for row in cursor.fetchall():
    print(f'{row[0]:<20}\t{row[1]}\t{row[2]:.1f}\t{row[3]:.0f}\t{row[4]:.0f}')

conn.close()