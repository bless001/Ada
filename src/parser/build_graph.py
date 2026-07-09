# build_graph.py

from pathlib import Path
from pprint import pprint

from src.parser.treesitter_extract import extract_python_syntax
from src.parser.lsp_client import LspClient


PROJECT_ROOT = "sample_project"
FILE_PATH = "sample_project/main.py"


def normalize_lsp_location(location):
    if not location:
        return None

    # LSP may return Location[] or LocationLink[]
    item = location[0] if isinstance(location, list) else location

    if "targetUri" in item:
        return {
            "uri": item["targetUri"],
            "line": item["targetSelectionRange"]["start"]["line"],
            "character": item["targetSelectionRange"]["start"]["character"],
        }

    if "uri" in item:
        return {
            "uri": item["uri"],
            "line": item["range"]["start"]["line"],
            "character": item["range"]["start"]["character"],
        }

    return None


def build_dependency_graph():
    syntax = extract_python_syntax(FILE_PATH)

    client = LspClient(PROJECT_ROOT)
    client.initialize()
    client.did_open(FILE_PATH)

    graph = {
        "nodes": [],
        "edges": [],
    }

    file_node_id = f"file:{FILE_PATH}"
    graph["nodes"].append({
        "id": file_node_id,
        "type": "file",
        "path": FILE_PATH,
    })

    # Add function nodes
    for fn in syntax["functions"]:
        fn_id = f"function:{FILE_PATH}:{fn['name']}"
        graph["nodes"].append({
            "id": fn_id,
            "type": "function",
            "name": fn["name"],
            "file": FILE_PATH,
            "start": fn["range"]["start"],
            "end": fn["range"]["end"],
        })

        graph["edges"].append({
            "from": file_node_id,
            "to": fn_id,
            "type": "DEFINES",
        })

    # Add call edges using LSP definition lookup
    for call in syntax["calls"]:
        line, character = call["start"]

        try:
            definition = client.definition(FILE_PATH, line, character)
            resolved = normalize_lsp_location(definition)
        except Exception as exc:
            resolved = None

        call_node_id = f"call:{FILE_PATH}:{line}:{character}:{call['callee_text']}"

        graph["nodes"].append({
            "id": call_node_id,
            "type": "call",
            "callee_text": call["callee_text"],
            "full_call": call["full_call"],
            "file": FILE_PATH,
            "line": line,
            "character": character,
            "resolved_definition": resolved,
        })

        if resolved:
            target_id = f"symbol:{resolved['uri']}:{resolved['line']}:{resolved['character']}"
            graph["nodes"].append({
                "id": target_id,
                "type": "resolved_symbol",
                "uri": resolved["uri"],
                "line": resolved["line"],
                "character": resolved["character"],
            })

            graph["edges"].append({
                "from": call_node_id,
                "to": target_id,
                "type": "RESOLVES_TO",
                "confidence": 1.0,
            })
        else:
            graph["edges"].append({
                "from": call_node_id,
                "to": call["callee_text"],
                "type": "UNRESOLVED_CALL_NAME",
                "confidence": 0.3,
            })

    client.shutdown()
    return graph


if __name__ == "__main__":
    graph = build_dependency_graph()
    pprint(graph)