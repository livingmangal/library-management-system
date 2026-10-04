#!/usr/bin/env python3
"""JSON API gateway for the modern Web frontend.
Communicates directly with the library TCP server and returns JSON.
"""

import json
import os
import sys

from common import ask_server, form_data

sys.stdout.reconfigure(encoding="utf-8")

print("Content-Type: application/json; charset=utf-8")
print("Access-Control-Allow-Origin: *")
print()

data = form_data()

# Also support raw JSON body if Content-Type is application/json
if os.environ.get("CONTENT_TYPE", "").startswith("application/json") and os.environ.get("REQUEST_METHOD") == "POST":
    length = int(os.environ.get("CONTENT_LENGTH") or 0)
    raw_body = sys.stdin.buffer.read(length).decode("utf-8")
    try:
        data = json.loads(raw_body)
    except Exception:
        pass

cmd = data.get("cmd", "").strip()

if not cmd:
    print(json.dumps({"ok": False, "error": "No 'cmd' parameter provided."}))
    sys.exit(0)

# Build args
kwargs = {}
for k, v in data.items():
    if k == "cmd":
        continue
    if isinstance(v, str) and v.isdigit():
        kwargs[k] = int(v)
    else:
        kwargs[k] = v

try:
    result = ask_server(cmd, **kwargs)
    print(json.dumps({"ok": True, "data": result}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
