import json
import logging
import os
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
