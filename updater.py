"""Fixed HTTPS release feed, SemVer ordering and SHA-256 before installer execution."""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from product import VERSION, APP_ID, UPDATE_FEED, RELEASE_HOSTS, STATE_DIR


def semver(value):
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?', value)
    if not match:
        raise ValueError('올바르지 않은 업데이트 버전이에요.')
    major, minor, patch, pre = match.groups()
    identifiers = pre.split('.') if pre else []
    if any(not s or (s.isdigit() and len(s)>1 and s[0]=='0') for s in identifiers):
        raise ValueError('올바르지 않은 시험판 버전이에요.')
    return (int(major),int(minor),int(patch),1 if not pre else 0,
            tuple((0,int(s)) if s.isdigit() else (1,s) for s in identifiers))


def allowed_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in RELEASE_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('공식 HTTPS 업데이트 주소가 아니에요.')
    return url


def check():
    try:
        request = urllib.request.Request(UPDATE_FEED, headers={'User-Agent':f'DdalKkak/{VERSION}'})
        with urllib.request.urlopen(request, timeout=12) as response:
            allowed_url(response.url)
            raw = response.read(256*1024+1)
        if len(raw)>256*1024:
            raise ValueError('업데이트 정보가 너무 커요.')
        return validate(json.loads(raw))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError('확인 실패: 공식 업데이트 피드가 아직 공개되지 않았어요. 현재 설치본은 계속 사용할 수 있어요.') from None
        raise ValueError('업데이트 확인 실패: 서버 응답 '+str(e.code)) from None
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise ValueError('업데이트 확인 실패: 네트워크 연결을 확인한 뒤 다시 시도해 주세요.') from e


def validate(data):
    if not isinstance(data,dict) or data.get('app_id') != APP_ID or data.get('os') != 'windows' or data.get('arch') != 'x86' or data.get('channel') != 'stable':
        raise ValueError('이 앱·Windows·아키텍처·채널에 맞는 업데이트 정보가 아니에요.')
    version = data.get('version','')
    order = semver(version)
    if order[3] != 1:
        raise ValueError('정식 채널에서 시험판을 설치할 수 없어요.')
    allowed_url(data.get('url',''))
    if not re.fullmatch('[a-fA-F0-9]{64}',data.get('sha256','')):
        raise ValueError('설치파일의 검증 해시가 없어요.')
    if not isinstance(data.get('size'),int) or not 1024 <= data['size'] <= 1024**3:
        raise ValueError('설치파일 크기 정보가 올바르지 않아요.')
    data['available'] = order > semver(VERSION)
    return data


def download(data):
    data = validate(dict(data))
    if not data['available']:
        raise ValueError('현재 버전보다 새 버전만 설치할 수 있어요.')
    folder = STATE_DIR/'updates'
    folder.mkdir(parents=True,exist_ok=True)
    fd,name = tempfile.mkstemp(prefix='download-',suffix='.part',dir=folder)
    temporary=Path(name)
    digest=hashlib.sha256()
    size=0
    try:
        with os.fdopen(fd,'wb') as output:
            with urllib.request.urlopen(urllib.request.Request(data['url'],headers={'User-Agent':f'DdalKkak/{VERSION}'}), timeout=25) as response:
                allowed_url(response.url)
                while chunk:=response.read(1024*1024):
                    size+=len(chunk)
                    if size>data['size']:
                        raise ValueError('설치파일 크기가 업데이트 정보와 달라요.')
                    output.write(chunk)
                    digest.update(chunk)
        if size != data['size'] or digest.hexdigest().lower() != data['sha256'].lower():
            raise ValueError('설치파일 검증에 실패했어요. 파일을 실행하지 않았어요. 다시 확인해 주세요.')
        destination=folder/f'DdalKkak-Setup-{data["version"]}.exe'
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
