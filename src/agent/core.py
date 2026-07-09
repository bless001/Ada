"""
Core agent functionality for Ada Coding Agent
"""
from typing import List, Dict, Any
from src.parser.code_parser import CodeParser
from src.analysis.code_analyzer import CodeAnalyzer
from src.generation.code_generator import CodeGenerator
from src.execution.code_executor import CodeExecutor


class AdaAgent:
    """
    Main Ada Coding Agent that coordinates parsing, analysis, generation, and execution
    """
    
    def __init__(self):
        self.parser = CodeParser()
        self.analyzer = CodeAnalyzer()
        self.generator = CodeGenerator()
        self.executor = CodeExecutor()
    
    def analyze_code(self, code: str) -> Dict[str, Any]:
        """Analyze code for understanding and modification"""
        return self.analyzer.analyze(code)
    
    def generate_code(self, requirements: str, context: Dict[str, Any] = None) -> str:
        """Generate code based on requirements"""
        return self.generator.generate(requirements, context)
    
    def execute_code(self, code: str) -> Dict[str, Any]:
        """Execute code and return results"""
        return self.executor.execute(code)
    
    def modify_code(self, code: str, modifications: List[str]) -> str:
        """Modify existing code based on specified modifications"""
        return self.analyzer.modify(code, modifications)
    
    def plan_and_execute(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute a plan of tasks autonomously"""
        from src.core.plan_executor import PlanExecutor
        executor = PlanExecutor(self)
        return executor.execute_plan(plan)