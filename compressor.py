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


def parse_ffmpeg_progress(line: str, duration: float) -> dict:
    """Parse FFmpeg progress line and extract useful info."""
    info = {}

    # Parse time
    time_match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
    if time_match:
        h, m, s = time_match.groups()
        info['current_time'] = int(h) * 3600 + int(m) * 60 + float(s)

    # Parse frame
    frame_match = re.search(r'frame=\s*(\d+)', line)
    if frame_match:
        info['frame'] = int(frame_match.group(1))

    # Parse fps
    fps_match = re.search(r'fps=\s*([\d.]+)', line)
    if fps_match:
        info['fps'] = float(fps_match.group(1))

    # Parse speed
    speed_match = re.search(r'speed=\s*([\d.]+)x', line)
    if speed_match:
        info['speed'] = float(speed_match.group(1))

    # Parse bitrate
    bitrate_match = re.search(r'bitrate=\s*([\d.]+)kbits/s', line)
    if bitrate_match:
        info['bitrate'] = float(bitrate_match.group(1))

    # Parse size
    size_match = re.search(r'size=\s*(\d+)kB', line)
    if size_match:
        info['size_kb'] = int(size_match.group(1))

    return info


def compress_video(input_path: str, output_path: str, target_size_bytes: int,
                   progress_callback=None, log_callback=None) -> str:
    """
    Compress video to target file size using two-pass encoding.

    Args:
        input_path: Path to input video
        output_path: Path for output video
        target_size_bytes: Target file size in bytes
        progress_callback: Optional callback(progress: float, speed: float, eta: float)
        log_callback: Optional callback(message: str) for FFmpeg log output

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

    if log_callback:
        log_callback(f"Input: {Path(input_path).name}")
        log_callback(f"Duration: {duration:.1f}s")
        log_callback(f"Target size: {target_size_bytes / (1024*1024):.1f} MB")
        log_callback(f"Target video bitrate: {video_bitrate // 1000} kbps")
        log_callback("---")
        log_callback("Starting Pass 1: Analyzing video...")

    # Pass 1: Analyze
    if progress_callback:
        progress_callback(0.0, 0, 0)

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
        if 'time=' in line:
            ffmpeg_info = parse_ffmpeg_progress(line, duration)
            if 'current_time' in ffmpeg_info:
                current_time = ffmpeg_info['current_time']
                # Pass 1 is 0-45% of total progress
                progress = min((current_time / duration) * 0.45, 0.45)
                speed = ffmpeg_info.get('speed', 0)
                # ETA for remaining work (both passes)
                if speed > 0:
                    remaining_pass1 = (duration - current_time) / speed
                    remaining_pass2 = duration / speed
                    eta = remaining_pass1 + remaining_pass2
                else:
                    eta = 0
                if progress_callback:
                    progress_callback(progress, speed, eta)
                if log_callback and ffmpeg_info.get('frame'):
                    log_callback(f"Pass 1: frame={ffmpeg_info.get('frame', 0)} fps={ffmpeg_info.get('fps', 0):.1f} speed={speed:.2f}x")

    process.wait()
    if process.returncode != 0:
        raise RuntimeError("FFmpeg pass 1 failed")

    if log_callback:
        log_callback("Pass 1 complete!")
        log_callback("---")
        log_callback("Starting Pass 2: Encoding video...")

    if progress_callback:
        progress_callback(0.45, 0, 0)

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
        if 'time=' in line:
            ffmpeg_info = parse_ffmpeg_progress(line, duration)
            if 'current_time' in ffmpeg_info:
                current_time = ffmpeg_info['current_time']
                # Pass 2 is 45-100% of total progress
                progress = 0.45 + min((current_time / duration) * 0.55, 0.55)
                speed = ffmpeg_info.get('speed', 0)
                # ETA for remaining pass 2 only
                if speed > 0:
                    eta = (duration - current_time) / speed
                else:
                    eta = 0
                if progress_callback:
                    progress_callback(progress, speed, eta)
                if log_callback and ffmpeg_info.get('frame'):
                    size_kb = ffmpeg_info.get('size_kb', 0)
                    log_callback(f"Pass 2: frame={ffmpeg_info.get('frame', 0)} fps={ffmpeg_info.get('fps', 0):.1f} size={size_kb}KB speed={speed:.2f}x")

    process.wait()
    if process.returncode != 0:
        raise RuntimeError("FFmpeg pass 2 failed")

    # Cleanup pass log files
    for log_file in temp_dir.glob('ffmpeg2pass*'):
        try:
            log_file.unlink()
        except OSError:
            pass

    if log_callback:
        output_size = Path(output_path).stat().st_size
        log_callback("---")
        log_callback(f"Compression complete!")
        log_callback(f"Output size: {output_size / (1024*1024):.1f} MB")

    if progress_callback:
        progress_callback(1.0, 0, 0)

    return output_path
