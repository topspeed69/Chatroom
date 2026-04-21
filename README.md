# Chatroom with AI & Multimedia Compression

A chat application featuring persistent history, predefined bot interactions, and an advanced multimedia pipeline for image and audio processing.

## 🚀 Key Features

- **Real-time Chat**: High-performance messaging powered by WebSockets.
- **Persistent History**: Message history is saved in a SQLite database and automatically retrieved when you join.
- **Bot Interactions**: Built-in bot commands (e.g., `/bot` or `/chat`) to answer common queries.
- **Image Processing**:
    - Automatic conversion of all images to **WebP** format.
    - Real-time **PSNR** (Peak Signal-to-Noise Ratio) calculation to measure quality loss.
    - Display of compression percentage and quality stats.
- **Advanced Audio Pipeline**:
    - Upload audio files up to **5MB**.
    - Automatic compression using **FFmpeg** to **AAC 64kbps, 22050Hz, Mono**.
    - **Detailed Analytics**:
        - Compression ratio and size reduction.
        - Audio PSNR calculation.
        - **Frequency Band Analysis**: Analysis of energy retention across different frequency bands (Bass, Mid, High, etc.).
        - **Spectral Correlation**: Measures how closely the compressed audio matches the original spectrum.
        - Metadata comparison (Bitrate, Sample Rate, etc.).


## 🛠 Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **Database**: [SQLModel](https://sqlmodel.tiangolo.com/) (SQLite)
- **Multimedia**: [FFmpeg](https://ffmpeg.org/) (for audio), [Pillow](https://python-pillow.org/) (for images)
- **Analysis**: [NumPy](https://numpy.org/) (FFT and signal processing)
- **Frontend**: Vanilla HTML5, CSS3, and JavaScript (ES6+)

## 📦 Prerequisites

1. **Python 3.12+**
2. **FFmpeg**: Ensure `ffmpeg` and `ffprobe` are installed and available in your system's PATH.
   - *Windows*: Install via [Chocolatey](https://chocolatey.org/) (`choco install ffmpeg`) or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
   - *Linux*: `sudo apt install ffmpeg`
   - *macOS*: `brew install ffmpeg`

## ⚙️ Installation & Setup

This project uses `uv` for fast dependency management.

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd chatroom
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Initialize the database**:
   The database is automatically initialized when the application starts.

## 🏃 Running the Application

Start the FastAPI server:

```bash
uv run python app.py
```

The application will be available at `http://localhost:8000`.

## 📖 Usage

1. **Join**: Enter your name on the landing screen to enter the chat.
2. **Chat**: Type in the message box and hit enter.
3. **Bot**: Use buttons at the top or prefix your message with `/bot` to interact with the canned response system.
4. **Images**: Click the `+` button to upload images. See the quality metrics directly in the chat row.
5. **Audio**: Click the 🎵 button to upload audio. Once compressed, play it back and click **"Show detailed stats"** to view the spectral analysis and compression performance.

## 📂 Project Structure

- `app.py`: Main FastAPI application and multimedia processing logic.
- `db.py`: Database schema and persistence layer.
- `ui/`: Frontend assets (HTML, CSS, JS).
- `uploads/`:
    - `images/`: Processed WebP images.
    - `original_audio/`: Raw audio uploads.
    - `compressed_audio/`: Processed AAC files.
- `chat.db`: SQLite database file.

## ⚖️ Upload Limits

- **Audio**: Hard limit of **5MB** per file.
- **Images**: No hard limit, but quality is automatically optimized to 85% WebP.

