"""Prepare assets locally. Publishing installers precedes publishing latest.json."""
import hashlib
import json
import zipfile
from pathlib import Path
from product import VERSION, APP_ID

root=Path(__file__).parent/'dist'
setup=root/f'DdalKkak-Setup-{VERSION}.exe'
digest=hashlib.sha256(setup.read_bytes()).hexdigest()
metadata={'app_id':APP_ID,'version':VERSION,'channel':'stable','os':'windows','arch':'x86',
          'url':f'https://github.com/moonsugugu/ddalkkak-converter/releases/download/v{VERSION}/{setup.name}',
          'sha256':digest,'size':setup.stat().st_size,
          'notes':'백신 오진을 줄이도록 설치 방식을 바꿨어요(한 파일 → 폴더형). 기능 변화는 없어요. 설정과 변환 파일은 그대로 남아요.'}
(root/'latest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
# Same installer inside a plain zip (no password) for browsers/messengers that block .exe downloads.
# latest.json keeps pointing at the .exe, which the auto-updater of older versions expects.
archive=root/f'DdalKkak-Setup-{VERSION}.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
    bundle.write(setup,setup.name)
lines=[]
for path in (setup,archive,root/'LICENSES.txt',root/'latest.json'):
    lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
(root/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
print(setup)
