"""
Code executor for Ada Coding Agent
"""
import subprocess
import sys
import tempfile
import os
from typing import Dict, Any

class CodeExecutor:
    """
    Executes code and returns results
    """
    
    def execute(self, code: str) -> Dict[str, Any]:
        """
        Execute Python code and return results
        """
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            # Execute the code
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            # Clean up temporary file
            os.unlink(temp_file)
            
            return {
                'success': True,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'execution_time': None  # Would be measured in a real implementation
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Execution timed out',
                'return_code': -1,
                'stdout': '',
                'stderr': 'Execution exceeded timeout limit'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'return_code': -1,
                'stdout': '',
                'stderr': str(e)
            }
    
    def execute_and_get_result(self, code: str) -> Dict[str, Any]:
        """
        Execute code and return only the result (not stdout/stderr)
        """
        # This is a simplified implementation
        # In a real system, we might need to capture actual return values
        # from functions, not just stdout
        try:
            exec(code)
            return {
                'success': True,
                'result': 'Code executed successfully'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }