# treesitter_extract.py

from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python


PY_LANGUAGE = Language(tree_sitter_python.language())


def node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def extract_python_syntax(file_path: str):
    path = Path(file_path)
    source = path.read_bytes()

    parser = Parser(PY_LANGUAGE)
    tree = parser.parse(source)
    root = tree.root_node

    result = {
        "file": str(path),
        "functions": [],
        "classes": [],
        "calls": [],
        "assignments": [],
        "imports": [],
    }

    for node in walk(root):
        # Function definitions
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                result["functions"].append({
                    "name": node_text(source, name_node),
                    "start": name_node.start_point,
                    "end": name_node.end_point,
                    "range": {
                        "start": node.start_point,
                        "end": node.end_point,
                    },
                })

        # Class definitions
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                result["classes"].append({
                    "name": node_text(source, name_node),
                    "start": name_node.start_point,
                    "end": name_node.end_point,
                    "range": {
                        "start": node.start_point,
                        "end": node.end_point,
                    },
                })

        # Function/method calls
        elif node.type == "call":
            function_node = node.child_by_field_name("function")
            if function_node:
                result["calls"].append({
                    "callee_text": node_text(source, function_node),
                    "callee_node_type": function_node.type,
                    "start": function_node.start_point,
                    "end": function_node.end_point,
                    "full_call": node_text(source, node),
                })

        # Assignments
        elif node.type == "assignment":
            left_node = node.child_by_field_name("left")
            right_node = node.child_by_field_name("right")
            result["assignments"].append({
                "left": node_text(source, left_node) if left_node else None,
                "right": node_text(source, right_node) if right_node else None,
                "start": node.start_point,
                "end": node.end_point,
            })

        # Imports
        elif node.type in {"import_statement", "import_from_statement"}:
            result["imports"].append({
                "text": node_text(source, node),
                "start": node.start_point,
                "end": node.end_point,
            })

    return result


if __name__ == "__main__":
    data = extract_python_syntax("sample_project/main.py")

    from pprint import pprint
    pprint(data)