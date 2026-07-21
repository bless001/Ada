# Ada Coding Agent

Ada is an intelligent coding assistant that can analyze, understand, and modify code in real-time. This implementation focuses on Python development with the capability to become fully autonomous.

## Features

- **Code Analysis**: Parse and understand existing Python code
- **Code Generation**: Create new Python code based on requirements
- **Code Execution**: Execute Python code safely
- **Code Modification**: Modify existing code based on specifications
- **Autonomous Operation**: Plan and execute tasks autonomously

## Project Structure

```
ada/
├── src/
│   ├── agent/          # Main agent components
│   ├── parser/         # Code parsing functionality
│   ├── analysis/       # Code analysis capabilities
│   ├── generation/     # Code generation functionality
│   ├── execution/      # Code execution capabilities
│   ├── utils/          # Utility functions
│   └── core/           # Core modules
├── main.py             # Main entry point
├── config.json         # Configuration file
└── requirements.txt    # Dependencies
```

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the agent:
   ```bash
   python main.py
   ```

## Usage

The Ada agent can be used programmatically:

```python
from src.agent.core import AdaAgent

# Create agent
agent = AdaAgent()

# Analyze code
analysis = agent.analyze_code("def hello(): pass")

# Generate code
generated = agent.generate_code("Create a factorial function")

# Execute code
result = agent.execute_code("print('Hello World')")
```

## Architecture

The system follows a modular architecture:
- **Parser**: Converts code into AST for analysis
- **Analyzer**: Understands code structure and relationships
- **Generator**: Creates new code based on requirements
- **Executor**: Runs code safely in isolated environments
- **Plan Executor**: Manages autonomous task execution

## Autonomous Mode

Set `enable_autonomous_mode` to `true` in `config.json` to enable autonomous operation. The agent can then plan and execute complex coding tasks without human intervention.

## License

Apache 2.0