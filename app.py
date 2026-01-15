import os
import uuid
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from compressor import compress_video, get_video_info

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024  # 10GB max upload
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['OUTPUT_FOLDER'] = Path(__file__).parent / 'outputs'

# Ensure folders exist
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['OUTPUT_FOLDER'].mkdir(exist_ok=True)

# Store job status
jobs = {}

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    # Generate unique job ID
    job_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    input_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"

    # Save uploaded file
    file.save(input_path)

    # Get video info
    try:
        info = get_video_info(str(input_path))
    except Exception as e:
        input_path.unlink(missing_ok=True)
        return jsonify({'error': f'Failed to read video: {str(e)}'}), 400

    # Store job info
    jobs[job_id] = {
        'status': 'uploaded',
        'progress': 0,
        'input_path': str(input_path),
        'original_filename': filename,
        'original_size': info['size'],
        'duration': info['duration']
    }

    return jsonify({
        'job_id': job_id,
        'original_size': info['size'],
        'duration': info['duration'],
        'filename': filename
    })


@app.route('/compress', methods=['POST'])
def compress():
    data = request.get_json()
    job_id = data.get('job_id')
    target_size = data.get('target_size')  # in bytes

    if not job_id or job_id not in jobs:
        return jsonify({'error': 'Invalid job ID'}), 400

    if not target_size or target_size <= 0:
        return jsonify({'error': 'Invalid target size'}), 400

    job = jobs[job_id]
    if job['status'] not in ['uploaded', 'completed', 'error']:
        return jsonify({'error': 'Job already in progress'}), 400

    # Prepare output path
    input_path = Path(job['input_path'])
    output_filename = f"compressed_{job['original_filename']}"
    output_path = app.config['OUTPUT_FOLDER'] / f"{job_id}_{output_filename}"

    job['status'] = 'compressing'
    job['progress'] = 0
    job['speed'] = 0
    job['eta'] = 0
    job['logs'] = []
    job['log_index'] = 0
    job['output_path'] = str(output_path)
    job['output_filename'] = output_filename

    def progress_callback(progress, speed, eta):
        job['progress'] = progress
        job['speed'] = speed
        job['eta'] = eta

    def log_callback(message):
        job['logs'].append(message)

    def run_compression():
        try:
            compress_video(
                str(input_path),
                str(output_path),
                target_size,
                progress_callback,
                log_callback
            )
            job['status'] = 'completed'
            job['progress'] = 1.0
            job['output_size'] = output_path.stat().st_size
        except Exception as e:
            job['status'] = 'error'
            job['error'] = str(e)

    # Run compression in background thread
    thread = threading.Thread(target=run_compression)
    thread.start()

    return jsonify({'status': 'started'})


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]
    response = {
        'status': job['status'],
        'progress': job.get('progress', 0),
        'speed': job.get('speed', 0),
        'eta': job.get('eta', 0)
    }

    # Return new log entries since last poll
    logs = job.get('logs', [])
    log_index = job.get('log_index', 0)
    if len(logs) > log_index:
        response['logs'] = logs[log_index:]
        job['log_index'] = len(logs)

    if job['status'] == 'completed':
        response['output_size'] = job.get('output_size', 0)

    if job['status'] == 'error':
        response['error'] = job.get('error', 'Unknown error')

    return jsonify(response)


@app.route('/download/<job_id>')
def download(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'File not ready'}), 400

    output_path = Path(job['output_path'])
    if not output_path.exists():
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        output_path,
        as_attachment=True,
        download_name=job['output_filename']
    )


@app.route('/cleanup/<job_id>', methods=['POST'])
def cleanup(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]

    # Delete input file
    input_path = Path(job['input_path'])
    input_path.unlink(missing_ok=True)

    # Delete output file if exists
    if 'output_path' in job:
        output_path = Path(job['output_path'])
        output_path.unlink(missing_ok=True)

    del jobs[job_id]
    return jsonify({'status': 'cleaned'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
