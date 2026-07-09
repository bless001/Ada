#!/usr/bin/env python3
"""
Main entry point for Ada Coding Agent
"""
import sys
from src.agent.core import AdaAgent
from src.utils.helpers import load_config

def main():
    """Main function to run the Ada agent"""
    print("Ada Coding Agent - Python Implementation")
    print("=" * 40)
    
    # Load configuration
    config = load_config()
    print(f"Configuration loaded: {config}")
    
    # Create agent
    agent = AdaAgent()
    
    # Example usage
    print("\nExample usage:")
    
    # 1. Analyze code
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
    
    print("1. Analyzing sample code...")
    analysis = agent.analyze_code(sample_code)
    print(f"Analysis successful: {analysis['success']}")
    if analysis['success']:
        print(f"Functions: {len(analysis['analysis']['functions'])}")
        print(f"Classes: {len(analysis['analysis']['classes'])}")
        print(f"Lines of code: {analysis['analysis']['lines_of_code']}")
    
    # 2. Generate code
    print("\n2. Generating new code...")
    generated_code = agent.generate_code("Create a function that calculates the factorial of a number")
    print("Generated code:")
    print(generated_code)
    
    # 3. Execute code (simplified)
    print("\n3. Demonstrating execution capability...")
    print("Code execution is possible but not executed in this demo")
    
    print("\nAda agent is ready for autonomous operation!")
    print("To enable autonomous mode, set 'enable_autonomous_mode': true in config.json")

if __name__ == "__main__":
    main()