"""Line-delimited JSON over Unix socket: client side.

Server-side handler lives in `wayscribe.daemon`.
"""
from __future__ import annotations

import json
import socket
import sys
from typing import Any

from wayscribe.config import socket_path


def send_command(cmd: str, **kwargs: Any) -> int:
    payload = json.dumps({"cmd": cmd, **kwargs}).encode() + b"\n"
    sock_path = socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(5.0)
            s.connect(str(sock_path))
            s.sendall(payload)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"wayscribe daemon not running (socket: {sock_path})", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"wayscribe ipc error: {exc}", file=sys.stderr)
        return 2

    if not buf:
        print("wayscribe daemon closed the connection without a reply", file=sys.stderr)
        return 2

    response = json.loads(buf.decode())
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok", True) else 1
