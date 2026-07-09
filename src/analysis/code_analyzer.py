"""
Code analyzer for Ada Coding Agent
"""
import ast
from typing import Dict, Any, List
from src.parser.code_parser import CodeParser

class CodeAnalyzer:
    """
    Analyzes code for understanding and modification
    """
    
    def __init__(self):
        self.parser = CodeParser()
    
    def analyze(self, code: str) -> Dict[str, Any]:
        """
        Analyze code and return comprehensive understanding
        """
        parse_result = self.parser.parse(code)
        
        if not parse_result['success']:
            return {
                'success': False,
                'error': parse_result['error'],
                'analysis': None
            }
        
        tree = parse_result['tree']
        functions = self.parser.get_functions(code)
        classes = self.parser.get_classes(code)
        
        # Perform basic analysis
        complexity = self._calculate_complexity(tree)
        dependencies = self._find_dependencies(tree)
        
        return {
            'success': True,
            'analysis': {
                'functions': functions,
                'classes': classes,
                'complexity': complexity,
                'dependencies': dependencies,
                'lines_of_code': len(code.split('\n')),
                'file_type': 'python'
            }
        }
    
    def _calculate_complexity(self, tree) -> Dict[str, Any]:
        """
        Calculate code complexity metrics
        """
        cyclomatic_complexity = 0
        nodes = 0
        
        # Simple complexity calculation based on control flow statements
        for node in ast.walk(tree):
            nodes += 1
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
                cyclomatic_complexity += 1
            elif isinstance(node, ast.Try):
                cyclomatic_complexity += 1
        
        return {
            'cyclomatic_complexity': cyclomatic_complexity,
            'nodes': nodes
        }
    
    def _find_dependencies(self, tree) -> List[str]:
        """
        Find dependencies in the code
        """
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        return imports
    
    def modify(self, code: str, modifications: List[str]) -> str:
        """
        Modify code based on specified modifications
        """
        # This is a simplified implementation - in a real system this would be more sophisticated
        modified_code = code
        
        # For now, we'll just add comments to indicate modifications
        for modification in modifications:
            modified_code += f"\n# Modification: {modification}"
        
        return modified_code