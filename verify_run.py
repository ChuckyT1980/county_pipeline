import sqlite3
import pandas as pd
import sys

def verify():
    print("--- RECONCILIATION TABLE ---")
    with sqlite3.connect('scheduler.db') as conn:
        cursor = conn.cursor()
        
        # 1. Input leads vs Queue Completed
        cursor.execute("SELECT COUNT(*) FROM queue_items")
        total_leads = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM queue_items WHERE status='completed'")
        completed = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM queue_items WHERE status='failed'")
        failed = cursor.fetchone()[0]
        
        print(f"Input leads: {total_leads}")
        print(f"Queue completed: {completed}")
        print(f"Queue failed: {failed}")
        
    try:
        df = pd.read_csv("A_PLUS_SCHEDULER_CRM.csv", header=None)
        # Handle the fact that we appended, so there might be multiple headers if we didn't use header=False
        exported_rows = len(df)
        apns = df[1].tolist()
        unique_apns = len(set(apns))
        duplicates = exported_rows - unique_apns
        
        print(f"Exported rows: {exported_rows}")
        print(f"Unique APNs: {unique_apns}")
        print(f"Duplicate APNs: {duplicates}")
    except Exception as e:
        print(f"Could not read CSV: {e}")

if __name__ == "__main__":
    verify()
