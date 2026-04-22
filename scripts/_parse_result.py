"""解析审核结果JSON，输出问题摘要"""
import json, sys
from pathlib import Path

json_path = sys.argv[1]
data = json.loads(Path(json_path).read_text(encoding='utf-8'))

for phase in data.get('check_results', []):
    name = phase.get('name', '')
    issues = phase.get('issues', [])
    warnings = phase.get('warnings', [])
    if issues or warnings:
        print(f'\n=== {name} ===')
        for i in issues:
            sev = i.get('severity', '')
            msg = i.get('message', '')[:180]
            print(f'  [{sev}] {msg}')
        for w in warnings:
            sev = w.get('severity', '')
            msg = w.get('message', '')[:180]
            print(f'  [{sev}] {msg}')
