"""Loopback HTTP transport. Worker threads access plain Python state only."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from .catalog import OPS
from .core import BridgeError

MAX_BODY = 8 * 1024 * 1024


def start_http(state, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def respond(self, status, result):
            body = json.dumps(result, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise BridgeError("INVALID_LENGTH", "Content-Length must be 1..8388608")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise BridgeError("INCOMPLETE_BODY", "Request body was truncated")
                if self.headers.get("Origin"):
                    raise BridgeError("ORIGIN_DENIED", "Browser origins are not accepted")
                auth = self.headers.get("Authorization", "")
                if not hmac.compare_digest(auth, "Bearer " + state.token):
                    raise BridgeError("UNAUTHORIZED", "Authentication required")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise BridgeError("INVALID_REQUEST", "Object body required")
                if self.path == "/health":
                    result = state.health()
                elif self.path == "/catalog":
                    result = {"operations": [v for k, v in OPS.items() if v['execution_domain'] == 'blender_main_thread' and (k != "python.execute" or state.allow_python)]}
                elif self.path == "/submit":
                    result = state.submit(data)
                elif self.path == "/job":
                    result = state.job(data["id"])
                elif self.path == "/cancel":
                    result = state.cancel(data["id"])
                elif self.path == "/artifacts":
                    with state.lock:
                        result = {"artifacts": list(state.artifacts.values())}
                else:
                    raise BridgeError("NOT_FOUND", "Unknown endpoint")
                self.respond(200, {"ok": True, "result": result})
            except (BrokenPipeError, ConnectionResetError):
                pass  # Accepted jobs remain queryable after disconnect.
            except Exception as exc:
                try:
                    self.respond(400, {"ok": False, "error": {"code": getattr(exc, "code", "BAD_REQUEST"), "message": str(exc)}})
                except OSError:
                    pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="BlenderBridgeHTTP").start()
    return server
