# Quick Start - AI Service

## Start the Service

```bash
cd ai
source venv/bin/activate
python3 main.py
```

**Note**: On macOS, use `python3` instead of `python`.

## Alternative: If python3 doesn't work

After activating the virtual environment, `python` should work:

```bash
cd ai
source venv/bin/activate
python main.py  # This should work after activation
```

## Verify It's Running

```bash
curl http://localhost:8000/health
```

Should return: `{"status":"UP"}`

## Access API Docs

Open in browser: http://localhost:8000/docs

## Troubleshooting

### "command not found: python"
- Use `python3` instead
- Or activate virtual environment first: `source venv/bin/activate`

### Dependency Installation Issues
If you see build errors with pydantic-core, try:
```bash
pip install --upgrade pip
pip install pydantic==2.5.3 --no-build-isolation
pip install -r requirements.txt
```

### Port Already in Use
```bash
lsof -i :8000
kill -9 <PID>
```

