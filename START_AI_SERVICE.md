# Starting AI Service

## Quick Start

```bash
cd ai
source venv/bin/activate
python main.py
```

## If you get "command not found: python"

On macOS, Python 3 is typically installed as `python3`. Use one of these:

### Option 1: Use python3 directly
```bash
cd ai
source venv/bin/activate
python3 main.py
```

### Option 2: Create alias (recommended)
Add to your `~/.zshrc` or `~/.bashrc`:
```bash
alias python=python3
```

Then reload:
```bash
source ~/.zshrc
```

### Option 3: Use virtual environment (recommended)
The virtual environment should have `python` available:
```bash
cd ai
source venv/bin/activate  # This activates venv
python main.py           # Now python should work
```

## Verify Setup

```bash
# Check Python is available
python3 --version

# Check virtual environment
cd ai
source venv/bin/activate
python --version
which python  # Should point to venv/bin/python
```

## Troubleshooting

### "python: command not found"
- Use `python3` instead
- Or activate virtual environment first: `source venv/bin/activate`

### "venv/bin/activate: No such file or directory"
- Create virtual environment: `python3 -m venv venv`

### "ModuleNotFoundError"
- Install dependencies: `pip install -r requirements.txt`
- Make sure virtual environment is activated

