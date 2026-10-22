import json

data = json.load(open('data/middle_activity_categories.json', encoding='utf-8'))
cats = data['categories']['data']
for c in cats:
    print(f"Domain ID: {c['id']} | Code: {c['ent_code']} | Caption: {c['ent_caption']}")
