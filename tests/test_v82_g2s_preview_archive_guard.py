"""A missing private preview workbook must never silently create an empty archive."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        (root/'scripts').mkdir()
        shutil.copy2(ROOT/'scripts/free_preview.py',root/'scripts/free_preview.py')
        proc=subprocess.run([sys.executable,str(root/'scripts/free_preview.py'),
            '--local-only','--archive','--port','8189'],cwd=root,timeout=15,
            capture_output=True,text=True)
        assert proc.returncode!=0,proc.stdout
        assert 'Historical archive workbook is not bundled' in (proc.stdout+proc.stderr),(proc.stdout,proc.stderr)
        assert not (root/'.env').exists()
        assert not (root/'data').exists()
    print('PASS G2S: missing historical archive fails before creating any demo data')

if __name__=='__main__':run()
