document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('uploadForm');
    const fileInput = form.querySelector('input[type="file"]');
    const fileInfo = document.getElementById('fileInfo');
    const convertBtn = document.getElementById('convertBtn');
    const dropZone = document.getElementById('dropZone');
    const progressContainer = document.getElementById('progressContainer');
    const progress = document.getElementById('progress');
    const statusText = document.getElementById('statusText');
    const errorContainer = document.getElementById('errorContainer');
    const errorMessage = document.getElementById('errorMessage');

    // File drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    dropZone.addEventListener('drop', handleDrop, false);

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function highlight(e) {
        dropZone.classList.add('drag-over');
    }

    function unhighlight(e) {
        dropZone.classList.remove('drag-over');
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        fileInput.files = files;
        updateFileInfo();
    }

    // File input change
    fileInput.addEventListener('change', updateFileInfo);

    function updateFileInfo() {
        const file = fileInput.files[0];
        if (file) {
            const size = (file.size / (1024 * 1024)).toFixed(2); // Convert to MB
            if (size > 16) {
                showError('File size exceeds 16MB limit');
                fileInput.value = '';
                fileInfo.textContent = 'No file selected';
                convertBtn.disabled = true;
                return;
            }
            if (!file.name.endsWith('.docx')) {
                showError('Please select a .docx file');
                fileInput.value = '';
                fileInfo.textContent = 'No file selected';
                convertBtn.disabled = true;
                return;
            }
            fileInfo.textContent = `${file.name} (${size}MB)`;
            convertBtn.disabled = false;
        } else {
            fileInfo.textContent = 'No file selected';
            convertBtn.disabled = true;
        }
    }

    // Form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(form);
        
        try {
            progressContainer.style.display = 'block';
            convertBtn.disabled = true;
            
            // Simulate progress
            let progressValue = 0;
            const progressInterval = setInterval(() => {
                if (progressValue < 90) {
                    progressValue += 10;
                    progress.style.width = `${progressValue}%`;
                    statusText.textContent = 'Converting...';
                }
            }, 500);

            const response = await fetch('/convert', {
                method: 'POST',
                body: formData
            });

            clearInterval(progressInterval);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Conversion failed');
            }

            // Complete the progress bar
            progress.style.width = '100%';
            statusText.textContent = 'Done!';

            // Get the blob
            const blob = await response.blob();
            
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = formData.get('word_file').name.replace('.docx', '.pdf');
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);

            // Reset form after short delay
            setTimeout(() => {
                form.reset();
                progressContainer.style.display = 'none';
                progress.style.width = '0%';
                fileInfo.textContent = 'No file selected';
                convertBtn.disabled = true;
            }, 2000);

        } catch (error) {
            showError(error.message);
            progressContainer.style.display = 'none';
            progress.style.width = '0%';
            convertBtn.disabled = false;
        }
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorContainer.style.display = 'flex';
    }
});

function dismissError() {
    document.getElementById('errorContainer').style.display = 'none';
}
