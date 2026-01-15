document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const removeFileBtn = document.getElementById('remove-file');
    const sliderSection = document.getElementById('slider-section');
    const sizeSlider = document.getElementById('size-slider');
    const sliderValue = document.getElementById('slider-value');
    const compressBtn = document.getElementById('compress-btn');
    const progressSection = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const etaText = document.getElementById('eta-text');
    const logSection = document.getElementById('log-section');
    const logContent = document.getElementById('log-content');
    const toggleLogBtn = document.getElementById('toggle-log');
    const resultSection = document.getElementById('result-section');
    const resultSize = document.getElementById('result-size');
    const downloadBtn = document.getElementById('download-btn');
    const newVideoBtn = document.getElementById('new-video-btn');
    const errorSection = document.getElementById('error-section');
    const errorMessage = document.getElementById('error-message');
    const retryBtn = document.getElementById('retry-btn');

    let currentJobId = null;
    let originalSize = 0;
    let pollInterval = null;

    // Utility functions
    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function formatEta(seconds) {
        if (seconds <= 0 || !isFinite(seconds)) return '';

        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hrs > 0) {
            return `ETA: ${hrs}h ${mins}m`;
        } else if (mins > 0) {
            return `ETA: ${mins}m ${secs}s`;
        } else {
            return `ETA: ${secs}s`;
        }
    }

    function showElement(el) {
        el.classList.remove('hidden');
    }

    function hideElement(el) {
        el.classList.add('hidden');
    }

    function resetUI() {
        hideElement(fileInfo);
        hideElement(sliderSection);
        hideElement(compressBtn);
        hideElement(progressSection);
        hideElement(logSection);
        hideElement(resultSection);
        hideElement(errorSection);
        showElement(uploadZone);
        progressFill.style.width = '0%';
        etaText.textContent = '';
        logContent.innerHTML = '';
        currentJobId = null;
        originalSize = 0;
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    function appendLog(message) {
        const p = document.createElement('p');
        p.textContent = message;
        logContent.appendChild(p);
        logContent.scrollTop = logContent.scrollHeight;
    }

    // Toggle log visibility
    toggleLogBtn.addEventListener('click', () => {
        logContent.classList.toggle('collapsed');
        toggleLogBtn.textContent = logContent.classList.contains('collapsed') ? 'Show' : 'Hide';
    });

    // Upload zone events
    uploadZone.addEventListener('click', () => fileInput.click());

    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });

    // Handle file upload
    async function handleFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        hideElement(uploadZone);
        showElement(progressSection);
        progressText.textContent = 'Uploading...';
        etaText.textContent = '';
        progressFill.style.width = '0%';

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Upload failed');
            }

            currentJobId = data.job_id;
            originalSize = data.original_size;

            // Show file info
            fileName.textContent = data.filename;
            fileSize.textContent = `Original size: ${formatBytes(data.original_size)}`;
            hideElement(progressSection);
            showElement(fileInfo);
            showElement(sliderSection);
            showElement(compressBtn);

            // Set slider max based on original size
            const maxSizeMB = Math.min(2000, Math.floor(data.original_size / (1024 * 1024)));
            sizeSlider.max = maxSizeMB;
            sizeSlider.value = Math.min(500, Math.floor(maxSizeMB / 2));
            updateSliderValue();

        } catch (error) {
            showError(error.message);
        }
    }

    // Remove file
    removeFileBtn.addEventListener('click', async () => {
        if (currentJobId) {
            try {
                await fetch(`/cleanup/${currentJobId}`, { method: 'POST' });
            } catch (e) {
                // Ignore cleanup errors
            }
        }
        resetUI();
        fileInput.value = '';
    });

    // Slider update
    sizeSlider.addEventListener('input', updateSliderValue);

    function updateSliderValue() {
        const value = parseInt(sizeSlider.value);
        if (value >= 1000) {
            sliderValue.textContent = `${(value / 1000).toFixed(1)} GB`;
        } else {
            sliderValue.textContent = `${value} MB`;
        }
    }

    // Compress button
    compressBtn.addEventListener('click', async () => {
        if (!currentJobId) return;

        const targetSizeBytes = parseInt(sizeSlider.value) * 1024 * 1024;

        hideElement(sliderSection);
        hideElement(compressBtn);
        hideElement(fileInfo);
        showElement(progressSection);
        showElement(logSection);
        logContent.innerHTML = '';
        logContent.classList.remove('collapsed');
        toggleLogBtn.textContent = 'Hide';
        progressText.textContent = 'Starting compression...';
        etaText.textContent = '';
        progressFill.style.width = '0%';

        try {
            const response = await fetch('/compress', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: currentJobId,
                    target_size: targetSizeBytes
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Compression failed');
            }

            // Start polling for progress
            pollProgress();

        } catch (error) {
            showError(error.message);
        }
    });

    // Poll for compression progress
    function pollProgress() {
        pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${currentJobId}`);
                const data = await response.json();

                // Append new logs
                if (data.logs && data.logs.length > 0) {
                    data.logs.forEach(log => appendLog(log));
                }

                if (data.status === 'compressing') {
                    const percent = Math.round(data.progress * 100);
                    progressFill.style.width = `${percent}%`;
                    progressText.textContent = `Compressing... ${percent}%`;

                    // Update ETA
                    if (data.eta > 0) {
                        etaText.textContent = formatEta(data.eta);
                    } else {
                        etaText.textContent = '';
                    }
                } else if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    showResult(data.output_size);
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    showError(data.error || 'Compression failed');
                }
            } catch (error) {
                clearInterval(pollInterval);
                pollInterval = null;
                showError('Connection lost');
            }
        }, 500);
    }

    // Show result
    function showResult(outputSize) {
        hideElement(progressSection);
        showElement(resultSection);
        const reduction = ((1 - outputSize / originalSize) * 100).toFixed(1);
        resultSize.textContent = `${formatBytes(outputSize)} (${reduction}% reduction)`;
    }

    // Download button
    downloadBtn.addEventListener('click', () => {
        if (currentJobId) {
            window.location.href = `/download/${currentJobId}`;
        }
    });

    // New video button
    newVideoBtn.addEventListener('click', async () => {
        if (currentJobId) {
            try {
                await fetch(`/cleanup/${currentJobId}`, { method: 'POST' });
            } catch (e) {
                // Ignore cleanup errors
            }
        }
        resetUI();
        fileInput.value = '';
    });

    // Error handling
    function showError(message) {
        hideElement(uploadZone);
        hideElement(fileInfo);
        hideElement(sliderSection);
        hideElement(compressBtn);
        hideElement(progressSection);
        hideElement(resultSection);
        showElement(errorSection);
        errorMessage.textContent = message;
    }

    retryBtn.addEventListener('click', async () => {
        if (currentJobId) {
            try {
                await fetch(`/cleanup/${currentJobId}`, { method: 'POST' });
            } catch (e) {
                // Ignore cleanup errors
            }
        }
        resetUI();
        fileInput.value = '';
    });
});
