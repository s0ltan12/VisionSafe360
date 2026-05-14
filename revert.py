import json

with open('/home/etsh/.gemini/antigravity/brain/afe53431-06f6-44ff-8082-6668369417d4/.system_generated/logs/overview.txt', 'r') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'CODE_ACTION' and 'LiveMonitoring.tsx' in data.get('content', ''):
            print(data['content'])
