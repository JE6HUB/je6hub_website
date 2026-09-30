import json

with open('/Users/je6hub/.gemini/antigravity-ide/brain/1695a2b8-2ade-4e53-a7d4-00ee3bfffb0f/.system_generated/logs/transcript_full.jsonl') as f:
    for line in f:
        data = json.loads(line)
        if 'tool_calls' in data:
            for tc in data['tool_calls']:
                if tc['name'] == 'write_to_file':
                    args = tc.get('args', {})
                    if 'base.html' in args.get('TargetFile', ''):
                        with open('extracted_base.html', 'w') as out:
                            out.write(args.get('CodeContent', ''))
                    if 'home.html' in args.get('TargetFile', ''):
                        with open('extracted_home.html', 'w') as out:
                            out.write(args.get('CodeContent', ''))
