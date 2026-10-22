import json

with open('data/fetched_students_middle.json', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total students: {len(data)}")
for i, s in enumerate(data[:10]):
    name = s.get('student_name')
    adm = s.get('admission_number')
    sid = s.get('student_id')
    stat = s.get('status')
    print(f"{i}: {name} | Adm: {adm} | ID: {sid} | Status: {stat}")
