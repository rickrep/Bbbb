document.addEventListener('DOMContentLoaded', function() {
    const translationForm = document.getElementById('translation-form');
    const submitBtn = document.getElementById('submit-btn');
    const progressSection = document.getElementById('translation-progress-section');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const downloadSection = document.getElementById('download-section');
    const downloadLink = document.getElementById('download-link');
    
    let currentJobId = null;
    let progressCheckInterval = null;
    
    // Handle form submission
    if (translationForm) {
        translationForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Validate file input
            const novelFile = document.getElementById('novel-file').files[0];
            if (!novelFile) {
                showAlert('Please select a novel file to translate.', 'danger');
                return;
            }
            
            // Check file extension
            const fileExt = novelFile.name.split('.').pop().toLowerCase();
            if (fileExt !== 'txt') {
                showAlert('Only .txt files are supported.', 'danger');
                return;
            }
            
            // Create FormData object
            const formData = new FormData(translationForm);
            
            // Disable form and show progress section
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Uploading...';
            progressSection.classList.remove('d-none');
            progressBar.style.width = '0%';
            progressBar.textContent = '0%';
            progressStatus.textContent = 'Uploading file...';
            downloadSection.classList.add('d-none');
            
            try {
                // Upload file
                const uploadResponse = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const uploadData = await uploadResponse.json();
                
                if (uploadData.success) {
                    // Store job ID
                    currentJobId = uploadData.job_id;
                    
                    // Update status
                    progressStatus.textContent = 'Processing text and preparing translation...';
                    
                    // Start translation process
                    await startTranslation(currentJobId);
                    
                    // Start progress checking
                    progressCheckInterval = setInterval(() => {
                        checkTranslationProgress(currentJobId);
                    }, 2000);
                    
                } else {
                    // Show error
                    showAlert(uploadData.message || 'Upload failed.', 'danger');
                    resetForm();
                }
                
            } catch (error) {
                console.error('Error:', error);
                showAlert('An error occurred during the upload.', 'danger');
                resetForm();
            }
        });
    }
    
    // Start the translation process
    async function startTranslation(jobId) {
        try {
            const response = await fetch(`/translate/${jobId}`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Update UI for completed translation
                progressBar.style.width = '100%';
                progressBar.textContent = '100%';
                progressBar.classList.remove('progress-bar-animated');
                progressStatus.textContent = 'Translation completed!';
                
                // Show download link
                downloadSection.classList.remove('d-none');
                downloadLink.href = `/download/${jobId}`;
                
                // Stop checking progress
                clearInterval(progressCheckInterval);
            } else {
                // Show error
                showAlert(data.message || 'Translation failed.', 'danger');
                resetForm();
                clearInterval(progressCheckInterval);
            }
            
        } catch (error) {
            console.error('Error:', error);
            showAlert('An error occurred during translation.', 'danger');
            resetForm();
            clearInterval(progressCheckInterval);
        }
    }
    
    // Check translation progress
    async function checkTranslationProgress(jobId) {
        try {
            const response = await fetch(`/check_progress/${jobId}`);
            const data = await response.json();
            
            // Update progress bar
            const progress = data.progress || 0;
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `${progress}%`;
            
            // Update status text based on progress
            if (data.status === 'completed') {
                progressStatus.textContent = 'Translation completed!';
                progressBar.classList.remove('progress-bar-animated');
                
                // Show download link
                downloadSection.classList.remove('d-none');
                downloadLink.href = `/download/${jobId}`;
                
                // Stop checking progress
                clearInterval(progressCheckInterval);
                
                // Enable form
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-language me-2"></i>Start Translation';
                
            } else if (data.status === 'failed') {
                progressStatus.textContent = 'Translation failed!';
                showAlert('Translation process failed.', 'danger');
                resetForm();
                clearInterval(progressCheckInterval);
                
            } else {
                // Update status based on progress
                if (progress < 5) {
                    progressStatus.textContent = 'Preparing translation...';
                } else if (progress < 20) {
                    progressStatus.textContent = 'Starting parallel processing...';
                } else {
                    progressStatus.textContent = `Translating... ${progress}% complete`;
                }
            }
            
        } catch (error) {
            console.error('Error checking progress:', error);
        }
    }
    
    // Reset form and UI
    function resetForm() {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-language me-2"></i>Start Translation';
        progressSection.classList.add('d-none');
    }
    
    // Show bootstrap alert
    function showAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        const container = document.querySelector('.container');
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, 5000);
    }
    
    // Handle custom prompt file selection
    const promptFileInput = document.getElementById('prompt-file');
    const customPromptTextarea = document.getElementById('custom-prompt-text');
    
    if (promptFileInput && customPromptTextarea) {
        promptFileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                // If a file is selected, disable the textarea
                customPromptTextarea.disabled = true;
                customPromptTextarea.placeholder = 'Using custom prompt from file...';
            } else {
                // If no file is selected, enable the textarea
                customPromptTextarea.disabled = false;
                customPromptTextarea.placeholder = 'Enter custom translation instructions...';
            }
        });
    }
});
