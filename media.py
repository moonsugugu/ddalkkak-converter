"""Local FFmpeg conversions. Commands receive only validated local file paths."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VIDEOS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
AUDIO = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}


class MediaCancelled(Exception):
    pass


def executable(name='ffmpeg'):
    for folder in (Path(sys.executable).parent/'tools', Path(__file__).parent/'vendor'/'ffmpeg'):
        path = folder / (name+'.exe')
        if path.is_file():
            return str(path)
    found = shutil.which(name)
    if found:
        return found
    winget = Path(os.environ.get('LOCALAPPDATA', ''))/'Microsoft/WinGet/Packages'
    return next((str(p) for p in winget.glob('Gyan.FFmpeg*/ffmpeg-*/bin/'+name+'.exe')), None)


def probe(source):
    tool = executable('ffprobe')
    if not tool:
        return {}
    try:
        result = subprocess.run([tool, '-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(source)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def convert(source, out, stem, target, quality, progress_path=None, cancel_path=None, options=None):
    options = options or {}
    if target not in {'compress','mp4','mov','mkv','webm','gif','mp3','wav','m4a','flac','ogg'}:
        raise ValueError('지원하지 않는 영상·음성 형식이에요.')
    tool = executable()
    if not tool:
        raise ValueError('영상·음성 변환에는 FFmpeg가 필요해요. FFmpeg를 설치한 뒤 다시 실행해 주세요.')
    audio_only = target in {'mp3', 'wav', 'm4a', 'flac', 'ogg'}
    info = probe(source)
    if audio_only and info and not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
        raise ValueError('소리가 없는 영상이에요. MP3·WAV로 꺼낼 음성 트랙이 없어요.')
    duration = float(info.get('format', {}).get('duration', 0) or 0)
    from advanced import timestamp
    start = timestamp(options.get('start', 0))
    end = timestamp(options['end']) if str(options.get('end', '')).strip() else duration
    if (start or options.get('end')) and (end <= start or duration and (start >= duration or end > duration+.1)):
        raise ValueError(f'시작·끝 시간은 전체 길이 {duration:.2f}초 안에서 지정해 주세요.')
    segment_duration = end-start if end > start else duration
    budget = int(options.get('max_bytes') or 0)
    bitrate = None
    if budget:
        if not segment_duration:
            raise ValueError('영상 길이를 확인하지 못해 목표 용량을 계산할 수 없어요.')
        bitrate = int(budget*.90*8/segment_duration)-64000
        if bitrate < 32000:
            raise ValueError('지정한 용량이 너무 작아요. 더 큰 목표 용량을 선택해 주세요.')
    ext = 'mp4' if target == 'compress' else target
    destination = out / f'{stem}.{ext}'
    command = [tool, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
               '-protocol_whitelist', 'file,pipe,crypto,data', '-filter_threads', '2',
               '-filter_complex_threads', '2', '-i', str(source)]
    if start:
        command += ['-ss', str(start)]
    if end > start:
        command += ['-t', str(segment_duration)]
    if audio_only:
        command += ['-map', '0:a:0', '-vn']
        command += {'mp3': ['-c:a', 'libmp3lame', '-b:a', {'small':'96k','balanced':'192k','high':'320k'}[quality]],
                    'wav': ['-c:a', 'pcm_s16le'], 'm4a': ['-c:a', 'aac', '-b:a', '192k'],
                    'flac': ['-c:a', 'flac'], 'ogg': ['-c:a', 'libvorbis', '-q:a', '5']}[target]
    elif target == 'gif':
        width = {'small':480, 'balanced':640, 'high':960}[quality]
        command += ['-filter_complex', f'[0:v:0]fps=12,scale=min({width}\\,iw):-1:flags=lanczos,split[a][b];'
                    '[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer', '-an', '-loop', '0']
    else:
        command += ['-map', '0:v:0', '-map', '0:a:0?']
        if target == 'compress':
            width, height, crf = {'small':(1280,720,30), 'balanced':(1920,1080,27), 'high':(2560,1440,23)}[quality]
            command += ['-vf', f'scale=w=min({width}\\,iw):h=min({height}\\,ih):'
                        'force_original_aspect_ratio=decrease:force_divisible_by=2']
        else:
            crf = {'small':28, 'balanced':23, 'high':19}[quality]
            command += ['-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2']
        if target == 'webm':
            command += ['-c:v', 'libvpx-vp9', '-deadline', 'realtime', '-cpu-used', '6', '-crf', str(crf+7),
                        '-b:v', '0', '-c:a', 'libopus', '-b:a', '128k']
        else:
            command += ['-c:v', 'libx264', '-preset', 'fast', '-crf', str(crf),
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k']
            if bitrate:
                crf_index = command.index('-crf')
                del command[crf_index:crf_index+2]
                command += ['-b:v', str(bitrate), '-maxrate', str(bitrate), '-bufsize', str(bitrate*2),
                            '-b:a', '64k']
        if ext in {'mp4', 'mov'}:
            command += ['-movflags', '+faststart']
    command += ['-threads', '2', '-progress', 'pipe:1', '-nostats', str(destination)]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True,
                    encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for line in process.stdout:
                if cancel_path and Path(cancel_path).exists():
                    process.terminate()
                    raise MediaCancelled('영상 변환을 중지했어요. 원본은 그대로예요.')
                if progress_path and line.startswith('out_time_us='):
                    seconds = max(0, int(line.split('=', 1)[1]) / 1_000_000)
                    message = (f'{min(99, int(seconds/segment_duration*100))}% 처리 중' if segment_duration else
                               f'{int(seconds//60):02d}:{int(seconds%60):02d} 처리 중')
                    Path(progress_path).write_text(message, encoding='utf-8')
            code = process.wait()
            if code:
                errors.seek(0)
                detail = errors.read().decode('utf-8', errors='replace')[-700:]
                raise ValueError('영상·음성 변환을 완료하지 못했어요. 손상되거나 지원하지 않는 파일인지 확인해 주세요.\n'+detail)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()
    if not destination.is_file() or not destination.stat().st_size:
        raise ValueError('영상·음성 변환 결과가 비어 있어요.')
