"""Initialize a private config from the example; keep existing local settings."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / 'xiaozhi-server/data/.config.yaml'
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists():
    print('KEEP existing local configuration')
else:
    shutil.copyfile(root / 'xiaozhi-server/config.example.yaml', target)
    print('Created local configuration. Fill in your own API key before starting app.py.')
