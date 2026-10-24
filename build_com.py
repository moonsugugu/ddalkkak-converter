"""Ship HWP's typed COM calls so frozen builds marshal document operations correctly."""
from pathlib import Path
import win32com
import win32com.gen_py
from win32com.client import gencache, makepy

folder = Path('vendor/comgen').resolve()
folder.mkdir(parents=True, exist_ok=True)
win32com.__gen_path__ = str(folder)
win32com.gen_py.__path__ = [str(folder)]
gencache.is_readonly = False
makepy.GenerateFromTypeLibSpec(('{7D2B6F3C-1D95-4E0C-BF5A-5EE564186FBC}', 0, 1, 0),
                               bForDemand=False, bBuildHidden=1)
