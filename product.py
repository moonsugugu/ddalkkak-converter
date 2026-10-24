"""Stable identity and release version. Storage/IPC keep the original identity for upgrades."""
from pathlib import Path
import os

TITLE = '딸깍변환'
VERSION = '3.1.0'
APP_ID = 'com.moonsunezip.docq'
EXE_NAME = 'DdalKkak.exe'
STATE_DIR = Path(os.environ['LOCALAPPDATA']) / 'Moonsunezip' / 'DocQ'
# This fixed public feed is provisioned when the first public release is published.
UPDATE_FEED = 'https://github.com/moonsugugu/ddalkkak-converter/releases/latest/download/latest.json'
RELEASE_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
