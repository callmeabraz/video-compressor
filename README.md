# Video Compressor

A simple local web application to compress videos to a target file size using FFmpeg.

## Features

- Drag-and-drop video upload
- Target size slider (100 MB - 2 GB)
- Two-pass encoding for accurate file size targeting
- Real-time progress tracking
- Supports MP4, AVI, MOV, MKV, WMV, FLV, and WebM

## Prerequisites

### FFmpeg

This application requires FFmpeg to be installed on your system.

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
1. Download from https://ffmpeg.org/download.html
2. Extract and add the `bin` folder to your system PATH

### Python 3.8+

Ensure Python 3.8 or higher is installed.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/video-compressor.git
cd video-compressor
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the server:
```bash
python app.py
```

2. Open your browser and go to:
```
http://localhost:5000
```

3. Upload a video, select your target size with the slider, and click "Compress Video"

4. Download your compressed video when complete

## How It Works

The application uses FFmpeg's two-pass encoding to achieve accurate target file sizes:

1. **Pass 1**: Analyzes the video to determine optimal encoding parameters
2. **Pass 2**: Encodes the video with the calculated bitrate to match your target size

The target bitrate is calculated as:
```
video_bitrate = (target_size_bytes * 8 / duration) - audio_bitrate
```

## License

MIT
