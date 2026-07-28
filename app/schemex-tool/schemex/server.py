"""Local development server for the interactive schema graph.

`schemex serve --state schemex_out/` serves the graph visualisation plus a
small JSON API (critique / fixer / coverage / chat) so the fixer, critic
bot, coverage check, and advocate/skeptic debate chat all run live in the
browser -- instead of round-tripping through separate `schemex critique` /
`schemex check` CLI calls and reopening a regenerated graph.html each time.

Uses only the standard library (http.server) -- no new dependency.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .io_utils import RunState
from .llm import ClaudeClient, LLMError
from .models import Cluster, CritiqueReport
from .pipeline import pick_best_cluster, run_coverage_check, run_critique, run_debate, run_fixer


class _AppState:
    def __init__(self, state_dir: str, model: str, max_tokens: int, api_key: Optional[str]) -> None:
        self.state = RunState.load(state_dir)
        if not self.state.clusters or not self.state.schemas:
            raise SystemExit(
                f"No clusters/schemas found in {state_dir}. Run `schemex run` first."
            )
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key
        self._client: Optional[ClaudeClient] = None

    def client(self) -> ClaudeClient:
        if self._client is None:
            self._client = ClaudeClient(
                model=self.model, max_tokens=self.max_tokens, api_key=self.api_key,
            )
        return self._client

    def cluster_for(self, cluster_id: Optional[str], draft_text: str) -> Cluster:
        if cluster_id:
            cluster = next((c for c in self.state.clusters if c.id == cluster_id), None)
            if cluster is None:
                raise ValueError(f"No cluster with id '{cluster_id}'.")
            return cluster
        return pick_best_cluster(self.client(), draft_text, self.state.clusters)


def _make_handler(app: _AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SchemexServer/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            print("[schemex serve]", fmt % args)

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw or b"{}")

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            if self.path in ("/", "/graph.html"):
                self._send_html(app.state.render_graph_html(interactive=True))
            elif self.path == "/api/clusters":
                self._send_json([
                    {"id": c.id, "name": c.name, "rationale": c.rationale}
                    for c in app.state.clusters
                ])
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            try:
                body = self._read_json()
                if self.path == "/api/critique":
                    self._handle_critique(body)
                elif self.path == "/api/fix":
                    self._handle_fix(body)
                elif self.path == "/api/coverage":
                    self._handle_coverage(body)
                elif self.path == "/api/chat":
                    self._handle_chat(body)
                else:
                    self._send_json({"error": "not found"}, 404)
            except LLMError as exc:
                self._send_json({"error": str(exc)}, 500)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:  # last resort -- still respond with JSON
                self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

        def _handle_critique(self, body: dict) -> None:
            draft_text = (body.get("draft_text") or "").strip()
            if not draft_text:
                raise ValueError("draft_text is required")
            cluster = app.cluster_for(body.get("cluster_id"), draft_text)
            schema = app.state.schemas.get(cluster.id)
            if schema is None:
                raise ValueError(f"Cluster '{cluster.id}' has no schema.")
            report = run_critique(app.client(), "draft", draft_text, schema, cluster)
            self._send_json({
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                "critique": report.to_dict(),
            })

        def _handle_fix(self, body: dict) -> None:
            draft_text = (body.get("draft_text") or "").strip()
            critique_dict = body.get("critique")
            if not draft_text or not critique_dict:
                raise ValueError("draft_text and critique are required")
            critique = CritiqueReport.from_dict(critique_dict)
            fixed = run_fixer(app.client(), draft_text, critique)
            self._send_json({"fixed_draft": fixed})

        def _handle_coverage(self, body: dict) -> None:
            draft_text = (body.get("draft_text") or "").strip()
            if not draft_text:
                raise ValueError("draft_text is required")
            cluster = app.cluster_for(body.get("cluster_id"), draft_text)
            schema = app.state.schemas.get(cluster.id)
            if schema is None:
                raise ValueError(f"Cluster '{cluster.id}' has no schema.")
            report = run_coverage_check(app.client(), "draft", draft_text, schema, cluster)
            self._send_json({
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                "coverage": report.to_dict(),
            })

        def _handle_chat(self, body: dict) -> None:
            draft_text = (body.get("draft_text") or "").strip()
            question = (body.get("question") or "").strip()
            history = body.get("history") or []
            if not draft_text or not question:
                raise ValueError("draft_text and question are required")
            cluster = app.cluster_for(body.get("cluster_id"), draft_text)
            schema = app.state.schemas.get(cluster.id)
            if schema is None:
                raise ValueError(f"Cluster '{cluster.id}' has no schema.")
            reply = run_debate(app.client(), draft_text, schema, cluster, history, question)
            self._send_json({
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                **reply,
            })

    return Handler


def run_server(
    state_dir: str,
    port: int = 8000,
    model: str = "",
    max_tokens: int = 4096,
    api_key: Optional[str] = None,
) -> int:
    app = _AppState(state_dir, model, max_tokens, api_key)
    handler = _make_handler(app)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"

    print(f"Schemex interactive graph -- {len(app.state.clusters)} clusters loaded from {state_dir}")
    print(f"Serving at {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
    return 0
