import json,subprocess,hashlib,os
from pathlib import Path
from job_output import commit_preview,discard_preview
import pymupdf
from PIL import Image
root=Path('validation/v31').resolve();state=json.loads((root/'ui-report.json').read_text(encoding='utf-8'));fixtures=Path(state['fixtures'])
exe=Path('dist/DdalKkak.exe').resolve();report={}
for source,target,options,save in [(fixtures/'기울어진 스캔.png','scan',{'mode':'bw','format':'png'},True),
                                  (fixtures/'다섯 쪽.pdf','split_pdf',{'chunk_pages':2},True),
                                  (fixtures/'다섯 쪽.pdf','split_pdf',{'chunk_pages':1},False)]:
 request,response=root/'packaged-request.json',root/'packaged-response.json';response.unlink(missing_ok=True)
 digest=hashlib.sha256(source.read_bytes()).hexdigest()
 request.write_text(json.dumps({'source':str(source),'target':target,'options':options,'preview':True}),encoding='utf-8')
 result_process=subprocess.run([str(exe),'--worker',str(request),str(response)],timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
 result=json.loads(response.read_text(encoding='utf-8'));assert result_process.returncode==0 and result.get('ok'),result
 assert result['_pending'] and result['_before_views'][0]
 if save:
  result=commit_preview(result)
  if target=='scan':
   with Image.open(result['files'][0]) as image:assert image.width<800 and len(image.getcolors())<=2
  else:
   counts=[]
   for path in result['files']:
    with pymupdf.open(path) as pdf:counts.append(len(pdf))
   assert counts==[2,2,1]
 else:
  stage=Path(result['_stage']);discard_preview(result);assert not stage.exists()
 assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
 report[target+(' save' if save else ' cancel')]={'ok':True,'original_preserved':True}
 print(target+': PASS',flush=True)
(root/'packaged-workers.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
