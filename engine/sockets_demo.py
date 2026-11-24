"""Real local TCP/UDP socket demos on 127.0.0.1 (these are REAL packets on the loopback interface)."""
import socket
import threading
import time

HOST = "127.0.0.1"


class Demo:
    def __init__(self, proto, default_port):
        self.proto, self.default_port = proto, default_port
        self.sock = None; self.thread = None; self.running = False; self.port = None; self.log = []; self.lock = threading.Lock()

    def _l(self, m):
        with self.lock:
            self.log.append(f"{time.strftime('%H:%M:%S')}  {m}"); self.log = self.log[-60:]

    def start(self, port=None):
        if self.running:
            return {"ok": True, "message": f"{self.proto} server already running on {HOST}:{self.port}"}
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM if self.proto == "TCP" else socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, int(port or self.default_port)))
        except OSError as e:
            s.close(); return {"ok": False, "message": f"Cannot bind port: {e}"}
        if self.proto == "TCP":
            s.listen(5)
        s.settimeout(0.4); self.sock, self.port, self.running = s, s.getsockname()[1], True
        self.thread = threading.Thread(target=self._serve, daemon=True); self.thread.start()
        self._l(f"[server] {self.proto} listening on {HOST}:{self.port}")
        return {"ok": True, "message": f"{self.proto} server started on {HOST}:{self.port}"}

    def _serve(self):
        while self.running:
            try:
                if self.proto == "TCP":
                    c, a = self.sock.accept()
                    self._l(f"[server] TCP connection accepted from {a[0]}:{a[1]} (3-way handshake complete)")
                    with c:
                        c.settimeout(2); data = c.recv(4096)
                        self._l(f"[server] received {len(data)} bytes: {data.decode(errors='replace')!r}")
                        c.sendall(b"ACK(TCP): " + data)
                    self._l("[server] connection closed (FIN exchange)")
                else:
                    data, a = self.sock.recvfrom(4096)
                    self._l(f"[server] UDP datagram from {a[0]}:{a[1]}: {data.decode(errors='replace')!r} (no connection)")
                    self.sock.sendto(b"ACK(UDP): " + data, a)
            except socket.timeout:
                continue
            except OSError:
                break

    def send(self, message):
        if not self.running:
            return {"ok": False, "message": f"{self.proto} server is not running. Start it first."}
        t0 = time.perf_counter()
        try:
            if self.proto == "TCP":
                with socket.create_connection((HOST, self.port), timeout=3) as c:
                    self._l(f"[client] TCP connected to {HOST}:{self.port}")
                    c.sendall(message.encode()); self._l(f"[client] sent {len(message.encode())} bytes")
                    reply = c.recv(4096).decode(errors="replace")
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
                    c.settimeout(3); c.sendto(message.encode(), (HOST, self.port)); self._l("[client] datagram sent (fire-and-forget)")
                    reply = c.recvfrom(4096)[0].decode(errors="replace")
            ms = round((time.perf_counter() - t0) * 1000, 2)
            self._l(f"[client] reply: {reply!r} ({ms} ms)")
            return {"ok": True, "reply": reply, "rtt_ms": ms}
        except OSError as e:
            return {"ok": False, "message": f"Communication failed: {e}"}

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self._l(f"[server] {self.proto} server stopped")
        return {"ok": True, "message": f"{self.proto} server stopped"}

    def status(self):
        return {"running": self.running, "port": self.port, "host": HOST, "log": list(self.log)}


DEMOS = {"tcp": Demo("TCP", 50007), "udp": Demo("UDP", 50008)}
