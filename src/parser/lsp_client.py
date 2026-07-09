# lsp_client.py

import json
import os
import pathlib
import subprocess
import threading
import queue
import itertools
from typing import Any, Optional


class LspClient:
    def __init__(self, root_path: str):
        self.root_path = pathlib.Path(root_path).resolve()
        self.root_uri = self.path_to_uri(self.root_path)

        self.proc = subprocess.Popen(
            ["pyright-langserver", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
        )

        self._id_counter = itertools.count(1)
        self._responses: dict[int, queue.Queue] = {}
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    @staticmethod
    def path_to_uri(path: pathlib.Path) -> str:
        return path.resolve().as_uri()

    def _send_payload(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")

        assert self.proc.stdin is not None
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    def _read_message(self) -> Optional[dict[str, Any]]:
        assert self.proc.stdout is not None

        headers = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None

            line = line.decode("ascii").strip()
            if line == "":
                break

            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()

        content_length = int(headers["content-length"])
        body = self.proc.stdout.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _read_loop(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                break

            # Response to a request
            if "id" in message:
                response_id = message["id"]
                if response_id in self._responses:
                    self._responses[response_id].put(message)

            # Server notification, for example diagnostics
            else:
                method = message.get("method")
                if method == "textDocument/publishDiagnostics":
                    pass

    def request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = next(self._id_counter)
        q: queue.Queue = queue.Queue()
        self._responses[request_id] = q

        self._send_payload({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })

        response = q.get(timeout=20)
        self._responses.pop(request_id, None)

        if "error" in response:
            raise RuntimeError(response["error"])

        return response.get("result")

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send_payload({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })

    def initialize(self) -> None:
        result = self.request("initialize", {
            "processId": os.getpid(),
            "rootUri": self.root_uri,
            "capabilities": {
                "textDocument": {
                    "definition": {
                        "linkSupport": True
                    },
                    "references": {},
                    "hover": {},
                    "synchronization": {
                        "didOpen": True,
                        "didChange": True,
                    }
                },
                "workspace": {
                    "workspaceFolders": True
                }
            },
            "workspaceFolders": [
                {
                    "uri": self.root_uri,
                    "name": self.root_path.name,
                }
            ],
        })

        self.notify("initialized", {})
        return result

    def did_open(self, file_path: str) -> None:
        path = pathlib.Path(file_path).resolve()
        text = path.read_text(encoding="utf-8")

        self.notify("textDocument/didOpen", {
            "textDocument": {
                "uri": self.path_to_uri(path),
                "languageId": "python",
                "version": 1,
                "text": text,
            }
        })

    def definition(self, file_path: str, line: int, character: int) -> Any:
        path = pathlib.Path(file_path).resolve()

        return self.request("textDocument/definition", {
            "textDocument": {
                "uri": self.path_to_uri(path)
            },
            "position": {
                "line": line,
                "character": character,
            }
        })

    def references(self, file_path: str, line: int, character: int) -> Any:
        path = pathlib.Path(file_path).resolve()

        return self.request("textDocument/references", {
            "textDocument": {
                "uri": self.path_to_uri(path)
            },
            "position": {
                "line": line,
                "character": character,
            },
            "context": {
                "includeDeclaration": True
            }
        })

    def shutdown(self) -> None:
        try:
            self.request("shutdown", {})
            self.notify("exit", {})
        finally:
            self.proc.kill()