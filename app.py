# Посредник для Telegram (Render) + Gemini. Пропускает только запросы двух твоих ботов и запросы generateContent к Gemini.
# Без сторонних библиотек: только стандартный Python. Запускается командой: python app.py (порт 7860).
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {"8906707048", "8374095423"}
UPSTREAM = os.environ.get("UPSTREAM", "https://api.telegram.org")
GEMINI_UP = os.environ.get("GEMINI_UP", "https://generativelanguage.googleapis.com")
PORT = int(os.environ.get("PORT", "7860"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _handle(self):
        path = self.path.lstrip("/")
        if path in ("", "health"):
            return self._reply(200, b"ok")          # проверка "жив ли посредник" (и для самого Hugging Face)
        if path.startswith("gemini/"):               # ИИ: только generateContent, ключ приходит в заголовке от бота
            gp = path[len("gemini/"):]
            if self.command != "POST" or not re.match(r"^v1beta/models/[\w.\-]+:generateContent$", gp):
                return self._reply(404, b"Not found")
            n = int(self.headers.get("Content-Length") or 0)
            req = urllib.request.Request(f"{GEMINI_UP}/{gp}", data=self.rfile.read(n) if n else b"", method="POST")
            req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
            if self.headers.get("x-goog-api-key"):
                req.add_header("x-goog-api-key", self.headers["x-goog-api-key"])
            try:
                with urllib.request.urlopen(req, timeout=100) as r:
                    return self._reply(r.status, r.read(), r.headers.get("Content-Type", "application/json"))
            except urllib.error.HTTPError as e:
                return self._reply(e.code, e.read(), e.headers.get("Content-Type", "application/json"))
            except Exception:
                return self._reply(502, b"Bad gateway")
        m = re.match(r"^(?:file/)?bot(\d+):", path)
        if not m or m.group(1) not in ALLOWED:
            return self._reply(404, b"Not found")
        data = None
        if self.command == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n) if n else b""
        req = urllib.request.Request(f"{UPSTREAM}/{path}", data=data, method=self.command)
        if self.headers.get("Content-Type"):
            req.add_header("Content-Type", self.headers["Content-Type"])
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                return self._reply(r.status, r.read(), r.headers.get("Content-Type", "application/octet-stream"))
        except urllib.error.HTTPError as e:      # Telegram ответил ошибкой (например 401/409) — отдаём как есть
            return self._reply(e.code, e.read(), e.headers.get("Content-Type", "application/json"))
        except Exception:
            return self._reply(502, b"Bad gateway")

    do_GET = _handle
    do_POST = _handle
    do_HEAD = _handle

    def log_message(self, *a):   # не пишем адреса (в них токен бота)
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
