"""
Plan executor for Ada Coding Agent
"""
from typing import List, Dict, Any
from src.agent.core import AdaAgent

class PlanExecutor:
    """
    Executes plans created by the Ada agent
    """
    
    def __init__(self, agent: AdaAgent):
        self.agent = agent
    
    def execute_plan(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute a plan consisting of multiple tasks
        """
        results = []
        
        for task in plan:
            try:
                task_result = self._execute_task(task)
                results.append({
                    'task': task,
                    'result': task_result,
                    'success': True
                })
            except Exception as e:
                results.append({
                    'task': task,
                    'result': str(e),
                    'success': False
                })
        
        return {
            'plan': plan,
            'results': results,
            'success': all(result['success'] for result in results)
        }
    
    def _execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single task
        """
        task_type = task.get('type')
        
        if task_type == 'analyze':
            return self.agent.analyze_code(task.get('code', ''))
        elif task_type == 'generate':
            return self.agent.generate_code(task.get('requirements', ''), task.get('context'))
        elif task_type == 'execute':
            return self.agent.execute_code(task.get('code', ''))
        elif task_type == 'modify':
            return self.agent.modify_code(task.get('code', ''), task.get('modifications', []))
        else:
            raise ValueError(f"Unknown task type: {task_type}")