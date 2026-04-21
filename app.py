import json
import logging
import os
import subprocess
import tempfile
import time
import math
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from PIL import Image

import db

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('chatroom')

app = FastAPI()

@app.on_event('startup')
def startup():
    db.init_db()
    (UPLOAD_ROOT / IMAGE_CATEGORY).mkdir(parents=True, exist_ok=True)
    (UPLOAD_ROOT / ORIGINAL_AUDIO_DIR).mkdir(parents=True, exist_ok=True)
    (UPLOAD_ROOT / COMPRESSED_AUDIO_DIR).mkdir(parents=True, exist_ok=True)

def calculate_psnr(img1: Image.Image, img2: Image.Image) -> float:
    """Calculate Peak Signal-to-Noise Ratio between two images."""
    # Convert images to RGB and ensure they have the same size
    i1 = img1.convert('RGB')
    i2 = img2.convert('RGB')
    if i1.size != i2.size:
        i2 = i2.resize(i1.size)
    
    arr1 = np.array(i1).astype(np.float64)
    arr2 = np.array(i2).astype(np.float64)
    
    mse = np.mean((arr1 - arr2) ** 2)
    if mse == 0:
        return 100.0
    
    return 20 * math.log10(255.0 / math.sqrt(mse))

UPLOAD_ROOT = Path('uploads')
IMAGE_CATEGORY = 'images'
ALLOWED_IMAGE_PREFIX = 'image/'
ORIGINAL_AUDIO_DIR = 'original_audio'
COMPRESSED_AUDIO_DIR = 'compressed_audio'
ALLOWED_AUDIO_PREFIX = 'audio/'
MAX_AUDIO_SIZE_BYTES = 5 * 1024 * 1024  # 5MB limit

class ConnectionManager:
    def __init__(self):
        self.connections: dict[WebSocket, str] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections[ws] = 'Guest'

    def disconnect(self, ws: WebSocket):
        self.connections.pop(ws, None)

    async def broadcast(self, message: dict):
        text = json.dumps(message)
        for ws in list(self.connections.keys()):
            try:
                await ws.send_text(text)
            except Exception:
                self.disconnect(ws)

manager = ConnectionManager()

ANSWERS = {
    "what services do you offer": "We offer 24/7 customer support, live chat assistance, and technical documentation.",
    "how can i get help": "Reach our support team through this chat, or email support@example.com.",
    "what are your hours": "Our team is available 24/7. Core hours: 9 AM - 6 PM.",
    "how do i contact support": "Use this live chat, or email support@example.com.",
    "hi":"Hi, How can i help you?",
    "Hi":"Hi, How can i help you?",
    "hello":"Hello, How can i help you?",
    "Hello":"Hello, How can i help you?",
    "hey":"Hey, How can i help you?",
    "Hey":"Hey, How can i help you?"
}

@app.on_event('startup')
def ensure_upload_dirs():
    (UPLOAD_ROOT / IMAGE_CATEGORY).mkdir(parents=True, exist_ok=True)
    (UPLOAD_ROOT / ORIGINAL_AUDIO_DIR).mkdir(parents=True, exist_ok=True)
    (UPLOAD_ROOT / COMPRESSED_AUDIO_DIR).mkdir(parents=True, exist_ok=True)

@app.post('/upload')
async def upload_image(file: UploadFile = File(...), username: str = Form('Guest')):
    if not file.content_type.startswith(ALLOWED_IMAGE_PREFIX):
        raise HTTPException(status_code=400, detail='Only image uploads are allowed.')

    filename = Path(file.filename).name
    if not filename:
        raise HTTPException(status_code=400, detail='Invalid file name.')

    image_dir = UPLOAD_ROOT / IMAGE_CATEGORY
    image_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{Path(filename).stem}_{int(time.time() * 1000)}.webp"
    output_path = image_dir / output_name

    try:
        file.file.seek(0, os.SEEK_END)
        source_size = file.file.tell()
        file.file.seek(0)

        original_image = Image.open(file.file)
        if original_image.mode not in ('RGB', 'RGBA'):
            img_to_save = original_image.convert('RGBA' if 'A' in original_image.mode else 'RGB')
        else:
            img_to_save = original_image

        img_to_save.save(output_path, format='WEBP', quality=85, method=6)
        
        # Calculate PSNR
        compressed_image = Image.open(output_path)
        psnr_value = calculate_psnr(original_image, compressed_image)

        compressed_size = output_path.stat().st_size
        logger.info(
            'Compressed image %s (%s, %s bytes) -> %s (%s bytes) at quality %s | PSNR: %.2f dB',
            filename,
            file.content_type,
            source_size,
            output_path.name,
            compressed_size,
            85,
            psnr_value
        )
    except Exception as exc:
        logger.error('Image compression failed for %s: %s', filename, exc)
        raise HTTPException(status_code=400, detail=f'Unable to process image: {exc}')

    url = f'/uploads/{IMAGE_CATEGORY}/{output_name}'
    compression_loss = round((1 - (compressed_size / source_size)) * 100, 1) if source_size else 0
    compression_info = {
        'original_bytes': source_size,
        'compressed_bytes': compressed_size,
        'quality': 85,
        'format': 'WEBP',
        'loss_percent': compression_loss,
        'psnr': round(psnr_value, 2)
    }

    # Save image to database
    db.save_image_message(username, filename, url, compression_info)

    await manager.broadcast({
        'type': 'image',
        'username': username.strip() or 'Guest',
        'url': url,
        'filename': filename,
        'compression': compression_info,
    })

    return {
        'message': 'Image uploaded successfully.',
        'url': url,
        'filename': filename,
        'compression': compression_info,
    }

# ─── Audio helpers ────────────────────────────────────────────────────────────

def _ffprobe_info(filepath: str) -> dict:
    """Use ffprobe to extract audio stream metadata."""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        logger.error('ffprobe failed: %s', result.stderr)
        return {}
    return json.loads(result.stdout)


def _decode_to_pcm(filepath: str) -> np.ndarray:
    """Decode an audio file to raw 16-bit PCM samples via ffmpeg."""
    cmd = [
        'ffmpeg', '-i', filepath,
        '-f', 's16le', '-acodec', 'pcm_s16le',
        '-ar', '22050', '-ac', '1',
        '-v', 'quiet', '-y', 'pipe:1'
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg decode failed: {result.stderr.decode()}')
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float64)


def _audio_psnr(original_path: str, compressed_path: str) -> float:
    """Calculate PSNR between original and compressed audio."""
    try:
        orig = _decode_to_pcm(original_path)
        comp = _decode_to_pcm(compressed_path)
        # Align lengths
        min_len = min(len(orig), len(comp))
        orig = orig[:min_len]
        comp = comp[:min_len]
        if min_len == 0:
            return 0.0
        mse = np.mean((orig - comp) ** 2)
        if mse == 0:
            return 100.0
        max_val = 32767.0  # 16-bit signed max
        return float(20 * math.log10(max_val / math.sqrt(mse)))
    except Exception as exc:
        logger.error('Audio PSNR calculation failed: %s', exc)
        return 0.0


def _frequency_analysis(original_path: str, compressed_path: str) -> dict:
    """Compare frequency spectra of original vs compressed audio."""
    try:
        orig = _decode_to_pcm(original_path)
        comp = _decode_to_pcm(compressed_path)
        min_len = min(len(orig), len(comp))
        orig = orig[:min_len]
        comp = comp[:min_len]
        if min_len == 0:
            return {}

        sample_rate = 22050
        # Compute magnitude spectra
        orig_fft = np.abs(np.fft.rfft(orig))
        comp_fft = np.abs(np.fft.rfft(comp))
        freqs = np.fft.rfftfreq(min_len, d=1.0 / sample_rate)

        # Define frequency bands
        bands = {
            'sub_bass': (20, 60),
            'bass': (60, 250),
            'low_mid': (250, 500),
            'mid': (500, 2000),
            'upper_mid': (2000, 4000),
            'high': (4000, 11025),
        }

        band_analysis = {}
        for band_name, (lo, hi) in bands.items():
            mask = (freqs >= lo) & (freqs < hi)
            if not np.any(mask):
                continue
            orig_energy = float(np.sum(orig_fft[mask] ** 2))
            comp_energy = float(np.sum(comp_fft[mask] ** 2))
            if orig_energy > 0:
                retention = round((comp_energy / orig_energy) * 100, 1)
            else:
                retention = 100.0
            band_analysis[band_name] = {
                'range_hz': f'{lo}-{hi}',
                'retention_percent': retention
            }

        # Overall spectral similarity (correlation)
        if np.std(orig_fft) > 0 and np.std(comp_fft) > 0:
            correlation = float(np.corrcoef(orig_fft, comp_fft)[0, 1])
        else:
            correlation = 1.0

        return {
            'spectral_correlation': round(correlation, 4),
            'bands': band_analysis
        }
    except Exception as exc:
        logger.error('Frequency analysis failed: %s', exc)
        return {}


def _extract_audio_features(filepath: str) -> dict:
    """Extract audio features from an audio file via ffprobe."""
    info = _ffprobe_info(filepath)
    if not info:
        return {}
    stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), {})
    fmt = info.get('format', {})
    return {
        'codec': stream.get('codec_name', 'unknown'),
        'sample_rate': int(stream.get('sample_rate', 0)),
        'channels': int(stream.get('channels', 0)),
        'channel_layout': stream.get('channel_layout', 'unknown'),
        'bitrate_kbps': round(int(fmt.get('bit_rate', 0)) / 1000),
        'duration_sec': round(float(fmt.get('duration', 0)), 2),
        'format_name': fmt.get('format_name', 'unknown'),
    }


@app.post('/upload-audio')
async def upload_audio(file: UploadFile = File(...), username: str = Form('Guest')):
    """Upload an audio file, compress to AAC 64kbps/22050Hz/mono, and return stats."""
    if not file.content_type or not file.content_type.startswith(ALLOWED_AUDIO_PREFIX):
        raise HTTPException(status_code=400, detail='Only audio uploads are allowed.')

    filename = Path(file.filename).name
    if not filename:
        raise HTTPException(status_code=400, detail='Invalid file name.')

    ts = int(time.time() * 1000)
    stem = Path(filename).stem

    # Save original
    original_dir = UPLOAD_ROOT / ORIGINAL_AUDIO_DIR
    original_dir.mkdir(parents=True, exist_ok=True)
    original_name = f'{stem}_{ts}{Path(filename).suffix}'
    original_path = original_dir / original_name

    raw_bytes = await file.read()
    original_size = len(raw_bytes)

    if original_size > MAX_AUDIO_SIZE_BYTES:
        original_path.unlink(missing_ok=True) # Cleanup just in case (though not written yet)
        raise HTTPException(status_code=413, detail=f'Audio file is too large. Maximum size allowed is 5MB.')

    original_path.write_bytes(raw_bytes)

    # Compress with ffmpeg -> AAC 64kbps, 22050 Hz, mono
    compressed_dir = UPLOAD_ROOT / COMPRESSED_AUDIO_DIR
    compressed_dir.mkdir(parents=True, exist_ok=True)
    compressed_name = f'{stem}_{ts}.m4a'
    compressed_path = compressed_dir / compressed_name

    try:
        cmd = [
            'ffmpeg', '-i', str(original_path),
            '-acodec', 'aac', '-b:a', '64k',
            '-ar', '22050', '-ac', '1',
            '-v', 'quiet', '-y',
            str(compressed_path)
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode())
    except Exception as exc:
        logger.error('Audio compression failed for %s: %s', filename, exc)
        # Cleanup
        original_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f'Audio compression failed: {exc}')

    compressed_size = compressed_path.stat().st_size

    # Stats
    psnr = _audio_psnr(str(original_path), str(compressed_path))
    freq_analysis = _frequency_analysis(str(original_path), str(compressed_path))
    original_features = _extract_audio_features(str(original_path))
    compressed_features = _extract_audio_features(str(compressed_path))

    compression_ratio = round(original_size / compressed_size, 2) if compressed_size else 0
    loss_percent = round((1 - (compressed_size / original_size)) * 100, 1) if original_size else 0

    url = f'/uploads/{COMPRESSED_AUDIO_DIR}/{compressed_name}'
    original_url = f'/uploads/{ORIGINAL_AUDIO_DIR}/{original_name}'

    audio_info = {
        'original_bytes': original_size,
        'compressed_bytes': compressed_size,
        'compression_ratio': compression_ratio,
        'loss_percent': loss_percent,
        'psnr': round(psnr, 2),
        'target_codec': 'AAC',
        'target_bitrate': '64 kbps',
        'target_sample_rate': '22050 Hz',
        'target_channels': 'Mono',
        'original_features': original_features,
        'compressed_features': compressed_features,
        'frequency_analysis': freq_analysis,
    }

    logger.info(
        'Compressed audio %s (%s bytes) -> %s (%s bytes) ratio=%.2f PSNR=%.2f dB',
        filename, original_size, compressed_name, compressed_size,
        compression_ratio, psnr
    )

    # Save to database
    db.save_audio_message(username, filename, url, original_url, audio_info)

    await manager.broadcast({
        'type': 'audio',
        'username': username.strip() or 'Guest',
        'url': url,
        'original_url': original_url,
        'filename': filename,
        'audio_info': audio_info,
    })

    return {
        'message': 'Audio uploaded successfully.',
        'url': url,
        'original_url': original_url,
        'filename': filename,
        'audio_info': audio_info,
    }


@app.websocket('/ws')
async def chat_endpoint(ws: WebSocket):
    await manager.connect(ws)
    await ws.send_text(json.dumps({'type': 'system', 'text': 'Connected.'}))
    
    try:
        while True:
            try:
                data = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                continue

            msg_type, content = data.get('type'), data.get('content', '').strip()
            
            if msg_type == 'join':
                user_name = data.get('username', 'Guest').strip() or 'Guest'
                manager.connections[ws] = user_name
                
                # Get or create user and fetch history
                user = db.get_or_create_user(user_name)
                history = db.get_messages_since(user.joined_at)
                
                # Send history to the joined user
                for msg in history:
                    if msg.msg_type == 'image':
                        extra = json.loads(msg.extra_data) if msg.extra_data else {}
                        await ws.send_text(json.dumps({
                            'type': 'image',
                            'username': msg.username,
                            'url': extra.get('url'),
                            'filename': extra.get('filename'),
                            'compression': extra.get('compression'),
                            'is_history': True
                        }))
                    elif msg.msg_type == 'audio':
                        extra = json.loads(msg.extra_data) if msg.extra_data else {}
                        await ws.send_text(json.dumps({
                            'type': 'audio',
                            'username': msg.username,
                            'url': extra.get('url'),
                            'original_url': extra.get('original_url'),
                            'filename': extra.get('filename'),
                            'audio_info': extra.get('audio_info'),
                            'is_history': True
                        }))
                    else:
                        await ws.send_text(json.dumps({
                            'type': 'message',
                            'username': msg.username,
                            'content': msg.content,
                            'is_history': True
                        }))

                await manager.broadcast({'type': 'system', 'text': f"{user_name} joined."})
                
            elif msg_type == 'message' and content:
                is_bot = content.startswith('/bot ')
                is_chat = content.startswith('/chat ')
                is_cmd = is_bot or is_chat
                prefix_len = 5 if is_bot else (6 if is_chat else 0)
                display = content[prefix_len:].strip() if is_cmd else content
                username = manager.connections[ws]

                # Persist message
                db.save_message(username, display)
                
                await manager.broadcast({'type': 'message', 'username': username, 'content': display})
                
                if is_cmd:
                    reply = ANSWERS.get(display.lower().rstrip('?'), 'invalid question try again')
                    db.save_message('Bot', reply)
                    await manager.broadcast({'type': 'message', 'username': 'Bot', 'content': reply})
                    
    except WebSocketDisconnect:
        user = manager.connections.get(ws, 'Guest')
        manager.disconnect(ws)
        await manager.broadcast({'type': 'system', 'text': f'{user} left.'})

app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')
app.mount('/', StaticFiles(directory='ui', html=True), name='ui')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)
