"""Portable browser selection; use Playwright's installed Chromium by default."""
import os
from pathlib import Path


def chromium_options():
    explicit = os.environ.get('RAMSES_BROWSER_EXECUTABLE')
    if explicit:
        if not Path(explicit).is_file():
            raise FileNotFoundError('RAMSES_BROWSER_EXECUTABLE must name an installed browser')
        return {'executable_path': explicit}
    for candidate in ('/usr/bin/chromium',
                      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
        if Path(candidate).is_file():
            return {'executable_path': candidate}
    return {}
