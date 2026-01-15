import subprocess
import json
import os
import re
from pathlib import Path


def get_video_info(input_path: str) -> dict:
    """Get video metadata using ffprobe."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        input_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    duration = float(data['format'].get('duration', 0))
    size = int(data['format'].get('size', 0))

    return {
        'duration': duration,
        'size': size,
        'format': data['format'].get('format_name', 'unknown')
    }


def calculate_bitrate(target_size_bytes: int, duration_seconds: float, audio_bitrate: int = 128000) -> int:
    """Calculate video bitrate needed to achieve target file size."""
    if duration_seconds <= 0:
        raise ValueError("Video duration must be positive")

    # Target size in bits, minus audio overhead
    target_bits = target_size_bytes * 8
    audio_bits = audio_bitrate * duration_seconds
    video_bits = target_bits - audio_bits

    # Calculate video bitrate with 5% safety margin
    video_bitrate = int((video_bits / duration_seconds) * 0.95)

    # Minimum bitrate of 100kbps
    return max(video_bitrate, 100000)


def compress_video(input_path: str, output_path: str, target_size_bytes: int,
                   progress_callback=None) -> str:
    """
    Compress video to target file size using two-pass encoding.

    Args:
        input_path: Path to input video
        output_path: Path for output video
        target_size_bytes: Target file size in bytes
        progress_callback: Optional callback function(progress: float) for progress updates

    Returns:
        Path to compressed video
    """
    # Get video info
    info = get_video_info(input_path)
    duration = info['duration']

    # Calculate target bitrate
    audio_bitrate = 128000  # 128kbps
    video_bitrate = calculate_bitrate(target_size_bytes, duration, audio_bitrate)

    # Create temp directory for pass logs
    temp_dir = Path(output_path).parent
    passlog_prefix = temp_dir / 'ffmpeg2pass'

    # Pass 1: Analyze
    if progress_callback:
        progress_callback(0.0)

    pass1_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', str(video_bitrate),
        '-pass', '1',
        '-passlogfile', str(passlog_prefix),
        '-an',
        '-f', 'null',
        '/dev/null'
    ]

    process = subprocess.Popen(
        pass1_cmd,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # Parse progress from stderr
    for line in process.stderr:
        if progress_callback and 'time=' in line:
            match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
            if match:
                h, m, s = match.groups()
                current_time = int(h) * 3600 + int(m) * 60 + float(s)
                # Pass 1 is 0-45% of total progress
                progress = min((current_time / duration) * 0.45, 0.45)
                progress_callback(progress)

    process.wait()
    if process.returncode != 0:
        raise RuntimeError("FFmpeg pass 1 failed")

    if progress_callback:
        progress_callback(0.45)

    # Pass 2: Encode
    pass2_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', str(video_bitrate),
        '-pass', '2',
        '-passlogfile', str(passlog_prefix),
        '-c:a', 'aac',
        '-b:a', '128k',
        output_path
    ]

    process = subprocess.Popen(
        pass2_cmd,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    for line in process.stderr:
        if progress_callback and 'time=' in line:
            match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
            if match:
                h, m, s = match.groups()
                current_time = int(h) * 3600 + int(m) * 60 + float(s)
                # Pass 2 is 45-100% of total progress
                progress = 0.45 + min((current_time / duration) * 0.55, 0.55)
                progress_callback(progress)

    process.wait()
    if process.returncode != 0:
        raise RuntimeError("FFmpeg pass 2 failed")

    # Cleanup pass log files
    for log_file in temp_dir.glob('ffmpeg2pass*'):
        try:
            log_file.unlink()
        except OSError:
            pass

    if progress_callback:
        progress_callback(1.0)

    return output_path
