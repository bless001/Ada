"""
Code generator for Ada Coding Agent
"""
from typing import Dict, Any, List
import random
import string

class CodeGenerator:
    """
    Generates code based on requirements and context
    """
    
    def generate(self, requirements: str, context: Dict[str, Any] = None) -> str:
        """
        Generate code based on requirements and context
        """
        # Basic implementation - in a real system this would be much more sophisticated
        # and potentially use AI/ML models
        
        # Generate a basic Python function based on requirements
        function_name = self._generate_function_name(requirements)
        parameters = self._generate_parameters(requirements)
        
        # Create function skeleton
        code = f"def {function_name}({', '.join(parameters)}):\n"
        code += "    \"\"\"Generated based on requirements: {requirements}\"\"\"\n"
        code += "    # TODO: Implement based on requirements\n"
        code += "    pass\n\n"
        
        # Add context if provided
        if context:
            code += "# Context provided:\n"
            for key, value in context.items():
                code += f"# {key}: {value}\n"
        
        return code
    
    def _generate_function_name(self, requirements: str) -> str:
        """
        Generate a function name based on requirements
        """
        # Simple approach - extract keywords from requirements
        words = requirements.lower().split()
        keywords = [word.strip('.,!?;:') for word in words if len(word) > 3]
        
        if keywords:
            return ''.join([word.capitalize() for word in keywords[:2]]) + 'Function'
        else:
            # Fallback to random name
            return 'generated_function_' + ''.join(random.choices(string.ascii_lowercase, k=5))
    
    def _generate_parameters(self, requirements: str) -> List[str]:
        """
        Generate parameters based on requirements
        """
        # Simple approach - generate generic parameters
        return ['param1', 'param2']
    
    def generate_class(self, class_name: str, methods: List[str]) -> str:
        """
        Generate a class with specified methods
        """
        code = f"class {class_name}:\n"
        code += "    \"\"\"Generated class\"\"\"\n\n"
        
        for method in methods:
            code += f"    def {method}(self):\n"
            code += "        # TODO: Implement method\n"
            code += "        pass\n\n"
        
        return code