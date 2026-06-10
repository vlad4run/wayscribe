"""Line-delimited JSON over Unix socket: client side.

Server-side handler lives in `wayscribe.daemon`.
"""
from __future__ import annotations

import json
import socket
import sys
from typing import Any

from wayscribe.config import socket_path


class DaemonUnreachable(Exception):
    """The daemon socket is absent or refused the connection."""


def query(cmd: str, timeout: float = 5.0, **kwargs: Any) -> dict[str, Any]:
    """Send one command, return the parsed reply.

    Raises `DaemonUnreachable` if the daemon is not running, or `OSError`
    on transport failure.
    """
    payload = json.dumps({"cmd": cmd, **kwargs}).encode() + b"\n"
    sock_path = socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock_path))
            s.sendall(payload)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise DaemonUnreachable(str(sock_path)) from exc

    if not buf:
        raise OSError("daemon closed the connection without a reply")
    return json.loads(buf.decode())


def send_command(cmd: str, **kwargs: Any) -> int:
    try:
        response = query(cmd, **kwargs)
    except DaemonUnreachable as exc:
        print(f"wayscribe daemon not running (socket: {exc})", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"wayscribe ipc error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok", True) else 1
