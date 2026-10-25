"""Collect the notices for the exact Python packages used to build the installer."""
from importlib import metadata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PACKAGES = ('Pillow', 'PyMuPDF', 'pywin32', 'python-docx', 'openpyxl',
            'python-pptx', 'pystray', 'comtypes', 'pyinstaller', 'lxml',
            'et_xmlfile', 'typing_extensions', 'six', 'packaging','markdown')


def main():
    sections = [
        '딸깍변환 · 문수네집\n'
        'Source: https://github.com/moonsugugu/ddalkkak-converter\n'
        'The application source is licensed under AGPL-3.0.\n'
        'Third-party components retain their own copyrights and licenses.\n\n'
        + (ROOT / 'LICENSE').read_text(encoding='utf-8'),
    ]
    for name in PACKAGES:
        dist = metadata.distribution(name)
        notices = []
        for file in dist.files or ():
            # Only distribution notices, never arbitrary Python modules or caches.
            if '.dist-info/' in str(file) and Path(file).name.upper().startswith(('LICENSE', 'COPYING')):
                notices.append(str(file) + '\n' + Path(dist.locate_file(file)).read_text(encoding='utf-8', errors='replace'))
        info = dist.metadata
        sections.append(f'{name} {dist.version}\nhttps://pypi.org/project/{name}/{dist.version}/\n'
                        + '\n'.join(info.get_all('Project-URL', [])) + '\n'
                        + (info.get('License', '') or '') + '\n' + '\n\n'.join(notices))
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    sections.append('Python / Tcl / Tk\n' + python_license.read_text(encoding='utf-8', errors='replace'))
    sections.append((ROOT / 'FFmpeg-SOURCE.txt').read_text(encoding='utf-8'))
    sections.append((ROOT / 'vendor' / 'README.md').read_text(encoding='utf-8'))
    (ROOT / 'dist' / 'LICENSES.txt').write_text(('\n\n' + '=' * 78 + '\n\n').join(sections), encoding='utf-8')


if __name__ == '__main__':
    main()
