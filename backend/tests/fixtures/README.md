Put test images in this folder to run the API tests with realistic inputs.

- Default path used by tests: `backend/tests/fixtures/test.png`
- Or set `TEST_IMAGE_PATH` to point at any image file on disk.

Example (from repo root, Windows PowerShell):

```powershell
$env:TEST_IMAGE_PATH="C:\path\to\my\whiteboard.png"
backend/venv/Scripts/python.exe -m unittest discover -s backend/tests -p "test_*.py"
```

