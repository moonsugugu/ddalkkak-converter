"""Prepare assets locally. Publishing installers precedes publishing latest.json."""
import hashlib
import json
from pathlib import Path
from product import VERSION, APP_ID

root=Path(__file__).parent/'dist'
setup=root/f'DdalKkak-Setup-{VERSION}.exe'
digest=hashlib.sha256(setup.read_bytes()).hexdigest()
metadata={'app_id':APP_ID,'version':VERSION,'channel':'stable','os':'windows','arch':'x86',
          'url':f'https://github.com/moonsugugu/ddalkkak-converter/releases/download/v{VERSION}/{setup.name}',
          'sha256':digest,'size':setup.stat().st_size,
          'notes':'전후 미리보기와 저장·취소, 스캔 사진 보정, PDF 자동 분리, 사용자 지정 단축키, 첫 실행 튜토리얼'}
(root/'latest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
lines=[]
for path in (setup,root/'LICENSES.txt',root/'latest.json'):
    lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
(root/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
print(setup)
