"""
Code parser for Ada Coding Agent
"""
import ast
import sys
from typing import Dict, Any, List

class CodeParser:
    """
    Parses code into abstract syntax trees for analysis
    """
    
    def parse(self, code: str) -> Dict[str, Any]:
        """
        Parse code into an abstract syntax tree
        """
        try:
            tree = ast.parse(code)
            return {
                'success': True,
                'tree': tree,
                'error': None
            }
        except SyntaxError as e:
            return {
                'success': False,
                'tree': None,
                'error': str(e)
            }
    
    def get_functions(self, code: str) -> List[Dict[str, Any]]:
        """
        Extract function definitions from code
        """
        try:
            tree = ast.parse(code)
            functions = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        'name': node.name,
                        'args': [arg.arg for arg in node.args.args],
                        'line_number': node.lineno
                    })
            
            return functions
        except SyntaxError:
            return []
    
    def get_classes(self, code: str) -> List[Dict[str, Any]]:
        """
        Extract class definitions from code
        """
        try:
            tree = ast.parse(code)
            classes = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append({
                        'name': node.name,
                        'line_number': node.lineno
                    })
            
            return classes
        except SyntaxError:
            return []