import sqlite3

conn = sqlite3.connect('data/hpc_automation.db')
cur = conn.cursor()
cur.execute("UPDATE upload_logs SET status = 'SUCCESS', screenshot_evidence = 'audit_evidence/live_roster_celebration.png' WHERE admission_number = '577'")
conn.commit()
rows = cur.execute("SELECT admission_number, student_name, status, screenshot_evidence FROM upload_logs").fetchall()
print("UPDATED DB LOGS:")
for r in rows:
    print(" ", r)

