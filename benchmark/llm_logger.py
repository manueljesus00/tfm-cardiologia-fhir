"""
benchmark/llm_logger.py — Monitor en tiempo real del tráfico LLM.

Sirve una pequeña web con SSE en:
    http://localhost:<port>/debug/tfm-monitor

Cada llamada al LLM durante el benchmark aparece en la página
con el prompt completo, la respuesta, tokens y latencia.

Uso básico (llamar una vez al arrancar el benchmark):
    from benchmark.llm_logger import LLMLogger
    LLMLogger.start(port=9999)        # abre el servidor
    LLMLogger.log_call(...)           # llamado automáticamente por _TrackingProvider

El log también se escribe en logs/llm_traffic.log para revisión offline.
"""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar


# ─── HTML del visor ──────────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>LLM Monitor — TFM</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d1117; color: #e6edf3; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 13px; }
header { background: #161b22; padding: 12px 20px; border-bottom: 1px solid #30363d;
         display: flex; align-items: center; gap: 12px; position: sticky; top: 0; z-index: 10; }
header h1 { font-size: 15px; color: #58a6ff; }
#status { font-size: 11px; color: #8b949e; margin-left: auto; }
#dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
       background: #3fb950; margin-right: 5px; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.25} }
#feed { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
.card-header { padding: 9px 14px; display: flex; align-items: center; gap: 8px;
               background: #1c2128; border-bottom: 1px solid #30363d;
               cursor: pointer; user-select: none; }
.card-header:hover { background: #21262d; }
.badge { padding: 2px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.fase1  { background: #1f4a8a; color: #79c0ff; }
.fase2  { background: #3a1d6e; color: #d2a8ff; }
.bmodel { background: #1d3a1d; color: #56d364; }
.meta   { color: #8b949e; font-size: 11px; }
.toggle { margin-left: auto; color: #8b949e; font-size: 11px; }
.card-body { display: block; }
.card-body.collapsed { display: none; }
.section { padding: 10px 14px; border-top: 1px solid #21262d; }
.sec-title { font-size: 10px; text-transform: uppercase; letter-spacing: .08em;
             color: #8b949e; margin-bottom: 6px; }
pre { white-space: pre-wrap; word-break: break-word; line-height: 1.55;
      max-height: 420px; overflow-y: auto; background: #0d1117;
      padding: 10px; border-radius: 4px; border: 1px solid #21262d; }
.p-pre  { color: #e6edf3; }
.r-pre  { color: #56d364; }
.tok    { color: #f78166; }
</style>
</head>
<body>
<header>
  <h1>&#x1F9EC; LLM Monitor &mdash; TFM Cardiolog&iacute;a FHIR</h1>
  <span id="status"><span id="dot"></span>Conectado &middot; esperando llamadas&hellip;</span>
</header>
<div id="feed"></div>
<script>
  const feed = document.getElementById('feed');
  const statusEl = document.getElementById('status');
  let count = 0;

  const src = new EventSource('/debug/tfm-monitor/events');

  src.addEventListener('llm_call', function(e) {
    const d = JSON.parse(e.data);
    count++;
    const phaseClass = (d.phase.toLowerCase().includes('fase1') || d.phase.toLowerCase().includes('ner'))
                       ? 'fase1' : 'fase2';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML =
      '<div class="card-header" onclick="toggle(this)">' +
        '<span class="badge ' + phaseClass + '">' + esc(d.phase) + '</span>' +
        '<span class="badge bmodel">' + esc(d.model) + '</span>' +
        '<span class="meta">' + esc(d.ts) + '</span>' +
        '<span class="meta tok">' + d.prompt_tokens + '&rarr;' + d.completion_tokens + ' tok</span>' +
        '<span class="meta">' + d.latency_s + 's</span>' +
        '<span class="toggle">&#9660;</span>' +
      '</div>' +
      '<div class="card-body">' +
        '<div class="section">' +
          '<div class="sec-title">Prompt <span class="tok">(' + d.prompt_tokens + ' tokens &middot; ' + d.prompt.length + ' chars)</span></div>' +
          '<pre class="p-pre">' + esc(d.prompt) + '</pre>' +
        '</div>' +
        '<div class="section">' +
          '<div class="sec-title">Respuesta <span class="tok">(' + d.completion_tokens + ' tokens &middot; ' + d.response.length + ' chars)</span></div>' +
          '<pre class="r-pre">' + esc(d.response) + '</pre>' +
        '</div>' +
      '</div>';
    feed.prepend(card);
    statusEl.innerHTML = '<span id="dot"></span>' + count + ' llamadas';
  });

  src.onerror = function() {
    statusEl.textContent = '\u26A0 Conexi\u00F3n perdida \u2014 recarga para reconectar';
  };

  function toggle(header) {
    const body = header.nextElementSibling;
    body.classList.toggle('collapsed');
    header.querySelector('.toggle').textContent = body.classList.contains('collapsed') ? '\u25B6' : '\u25BC';
  }

  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
</script>
</body>
</html>
"""


# ─── Servidor SSE ─────────────────────────────────────────────────────────────

class _SSEHandler(BaseHTTPRequestHandler):
    """Handler HTTP minimalista: sirve el HTML y el stream SSE."""

    def log_message(self, fmt, *args):  # silenciar log de acceso
        pass

    def do_GET(self):
        if self.path == "/debug/tfm-monitor":
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/debug/tfm-monitor/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            # Añadir cola de este cliente al registro global
            client_q: queue.Queue = queue.Queue(maxsize=64)
            with LLMLogger._clients_lock:
                LLMLogger._clients.append(client_q)
            try:
                while True:
                    try:
                        event = client_q.get(timeout=20)
                        if event is None:
                            break
                        self.wfile.write(event)
                        self.wfile.flush()
                    except queue.Empty:
                        # Heartbeat para mantener viva la conexión
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with LLMLogger._clients_lock:
                    try:
                        LLMLogger._clients.remove(client_q)
                    except ValueError:
                        pass

        else:
            self.send_response(404)
            self.end_headers()


# ─── Logger singleton ─────────────────────────────────────────────────────────

class LLMLogger:
    """
    Singleton que captura cada llamada LLM y la distribuye a:
      · Un fichero de log en disco (logs/llm_traffic.log)
      · Los clientes SSE conectados al visor web
    """

    _clients: ClassVar[list[queue.Queue]] = []
    _clients_lock: ClassVar[threading.Lock] = threading.Lock()
    _log_path: ClassVar[Path | None] = None
    _file_lock: ClassVar[threading.Lock] = threading.Lock()
    _server: ClassVar[HTTPServer | None] = None
    _started: ClassVar[bool] = False

    @classmethod
    def start(cls, port: int = 9999, log_dir: str = "logs") -> None:
        """
        Inicia el servidor HTTP de monitorización. Llamar una vez al arrancar el benchmark.
        No bloquea: el servidor corre en un hilo daemon.
        """
        if cls._started:
            return
        cls._started = True

        Path(log_dir).mkdir(parents=True, exist_ok=True)
        cls._log_path = Path(log_dir) / "llm_traffic.log"

        with open(cls._log_path, "w", encoding="utf-8") as f:
            f.write(f"=== LLM Traffic Log — {datetime.now().isoformat(timespec='seconds')} ===\n\n")

        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), _SSEHandler)
            cls._server = server
            t = threading.Thread(
                target=server.serve_forever,
                daemon=True,
                name="llm-monitor",
            )
            t.start()
            print(f"[🔍] LLM Monitor  →  http://localhost:{port}/debug/tfm-monitor")
        except OSError as e:
            print(f"[⚠] LLM Monitor no pudo arrancar en puerto {port}: {e}")

        print(f"[📝] LLM Log       →  {cls._log_path.resolve()}")

    @classmethod
    def log_call(
        cls,
        model: str,
        phase: str,
        prompt: str,
        response: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_s: float,
    ) -> None:
        """Registra una llamada LLM. Thread-safe."""
        ts = datetime.now().strftime("%H:%M:%S")

        # ── Fichero de log ─────────────────────────────────────────────────
        if cls._log_path is not None:
            block = (
                f"\n{'═' * 80}\n"
                f"[{ts}]  {model}  |  {phase}\n"
                f"Tokens: {prompt_tokens} → {completion_tokens}  |  "
                f"Latencia: {latency_s:.2f}s\n"
                f"{'─' * 40} PROMPT ({len(prompt)} chars)\n"
                f"{prompt}\n"
                f"{'─' * 40} RESPUESTA ({len(response)} chars)\n"
                f"{response}\n"
            )
            with cls._file_lock:
                with open(cls._log_path, "a", encoding="utf-8") as f:
                    f.write(block)

        # ── SSE a clientes web ─────────────────────────────────────────────
        with cls._clients_lock:
            if not cls._clients:
                return
            payload = json.dumps(
                {
                    "ts": ts,
                    "model": model,
                    "phase": phase,
                    "prompt": prompt,
                    "response": response,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "latency_s": latency_s,
                },
                ensure_ascii=False,
            )
            event_bytes = f"event: llm_call\ndata: {payload}\n\n".encode("utf-8")
            dead = []
            for q in cls._clients:
                try:
                    q.put_nowait(event_bytes)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                cls._clients.remove(q)
