# -*- coding: utf-8 -*-
"""一次性探测：启动 search_mcp_server.py 的 stdio，走一次 initialize + tools/list。"""
import json
import subprocess
import sys
import os

SRV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_mcp_server.py")
PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "python.exe")


def call(proc, payload):
    proc.stdin.write(json.dumps(payload).encode() + b"\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


p = subprocess.Popen([PY, SRV], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
try:
    init = call(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "probe", "version": "0"}}})
    p.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n'); p.stdin.flush()
    listed = call(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = listed.get("result", {}).get("tools", [])
    print("server:", init["result"]["serverInfo"].get("name"))
    for t in tools:
        schema = t.get("inputSchema", {}).get("properties", {})
        print("-", t["name"], "|", t.get("description", "")[:60], "| args:", ",".join(schema.keys()))
finally:
    p.kill()