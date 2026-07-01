import sqlite3
import pandas as pd
import time
import re

def wait_for_completion():
    print("Waiting for queue to drain...")
    while True:
        with sqlite3.connect('scheduler.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE status='completed'")
            completed = cursor.fetchone()[0]
            if completed >= 153:
                print("Queue drained!")
                break
        time.sleep(5)

def generate_report():
    print("\n--- FINAL RUN SUMMARY ---")
    
    with sqlite3.connect('scheduler.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM queue_items WHERE status='completed'")
        completed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM queue_items WHERE status='failed'")
        failed = cursor.fetchone()[0]
        
    df = pd.read_csv("A_PLUS_SCHEDULER_PROBABILISTIC.csv", header=None, names=[
        "apn", "final_score", "base_score", "uncertainty_multiplier", "coverage", 
        "confidence", "rank_bucket", "amount_due", "persistence_years", "equity_proxy", 
        "deal_strength", "raw_owner", "headline", "decision_label", "drivers", "blockers", 
        "confidence_summary", "max_theoretical_score", "top_action", "expected_delta", "bottleneck"
    ])
    
    df['coverage'] = pd.to_numeric(df['coverage'], errors='coerce')
    df['confidence'] = pd.to_numeric(df['confidence'], errors='coerce')
    df['final_score'] = pd.to_numeric(df['final_score'], errors='coerce')
    
    print(f"Processed: 153")
    print(f"Successful: {completed}")
    print(f"Failed: {failed}")
    
    print(f"\nAverage completeness (coverage): {df['coverage'].mean():.2f}")
    print(f"Average confidence: {df['confidence'].mean():.2f}")
    
    print(f"\nScore Distribution:")
    print(f"Average score: {df['final_score'].mean():.2f}")
    print(f"Median score: {df['final_score'].median():.2f}")
    print(f"90th percentile: {df['final_score'].quantile(0.90):.2f}")
    print(f"Highest score: {df['final_score'].max():.2f}")
    print(f"Lowest score: {df['final_score'].min():.2f}")
    
    print("\nAction Gradient Aggregation:")
    print(f"{'Missing Field':<20} | {'Count':>5} | {'Avg Score Gain':>15}")
    print("-" * 46)
    
    # top_action looks like "resolve_missing_field on mailing_address"
    # we can extract the field using regex
    action_stats = {}
    for _, row in df.iterrows():
        action_str = str(row['top_action'])
        if "on" in action_str:
            field = action_str.split(" on ")[-1].strip()
            try:
                delta = float(row['expected_delta'])
                if field not in action_stats:
                    action_stats[field] = []
                action_stats[field].append(delta)
            except ValueError:
                pass
            
    for field, deltas in action_stats.items():
        avg_gain = sum(deltas) / len(deltas)
        print(f"{field:<20} | {len(deltas):>5} | {avg_gain:>15.2f}")
        
    print("\nValidation Summary:")
    apns = df['apn'].tolist()
    unique_apns = len(set(apns))
    duplicates = len(apns) - unique_apns
    
    print(f"Exported rows: {len(apns)}")
    print(f"Unique APNs: {unique_apns}")
    print(f"Duplicate APNs: {duplicates}")

if __name__ == "__main__":
    wait_for_completion()
    generate_report()
