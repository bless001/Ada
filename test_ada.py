#!/usr/bin/env python3
"""
Test script to verify Ada Coding Agent components work correctly
"""
import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that all modules can be imported"""
    try:
        from agent.core import AdaAgent
        from parser.code_parser import CodeParser
        from analysis.code_analyzer import CodeAnalyzer
        from generation.code_generator import CodeGenerator
        from execution.code_executor import CodeExecutor
        from core.plan_executor import PlanExecutor
        from utils.helpers import load_config
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_agent_functionality():
    """Test basic agent functionality"""
    try:
        from agent.core import AdaAgent
        
        # Create agent
        agent = AdaAgent()
        print("✓ Agent creation successful")
        
        # Test code analysis
        sample_code = """
def hello_world(name):
    print(f"Hello, {name}!")
    return True

class SampleClass:
    def __init__(self):
        self.value = 0
    
    def increment(self):
        self.value += 1
"""
        
        analysis = agent.analyze_code(sample_code)
        if analysis['success']:
            print("✓ Code analysis successful")
            print(f"  Functions: {len(analysis['analysis']['functions'])}")
            print(f"  Classes: {len(analysis['analysis']['classes'])}")
        else:
            print(f"✗ Code analysis failed: {analysis.get('error')}")
            return False
        
        # Test code generation
        generated = agent.generate_code("Create a function that calculates the factorial of a number")
        if generated:
            print("✓ Code generation successful")
        else:
            print("✗ Code generation failed")
            return False
            
        print("✓ All agent functionality tests passed")
        return True
        
    except Exception as e:
        print(f"✗ Agent functionality test failed: {e}")
        return False

def test_config():
    """Test configuration loading"""
    try:
        from utils.helpers import load_config
        config = load_config()
        print("✓ Configuration loading successful")
        print(f"  Debug mode: {config.get('debug', False)}")
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Ada Coding Agent components...")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_agent_functionality,
        test_config
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! Ada Coding Agent is working correctly.")
        return 0
    else:
        print("❌ Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())