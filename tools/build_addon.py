"""Package first-party Python files only; never include references, secrets or venv."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
out = root/'dist'/'blender_bridge-0.1.0.zip'
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((root/'src'/'blender_bridge').glob('*.py')):
        z.write(p,Path('blender_bridge')/p.name)
print(out)
