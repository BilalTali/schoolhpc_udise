import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/live_part_b_state.json', 'r', encoding='utf-8') as f:
    d = json.load(f)['data']['formdata'][0]['dt']

print("activity:", d.get('activity'))
print("any_other:", d.get('any_other'))
print("spt:", d.get('spt'))
print("awr:", d.get('awr'))
print("sen:", d.get('sen'))
print("cre:", d.get('cre'))
print("slr:", d.get('slr'))
print("ml:", d.get('ml'))
print("mpa:", d.get('mpa'))
print("mps:", d.get('mps'))
print("mpc:", d.get('mpc'))
