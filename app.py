import os
import json
import time
import logging
import asyncio
import tempfile
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
from utils.text_processing import chunk_text, count_tokens, join_translations
from utils.translation import translate_chunks

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key-for-development")

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'txt'}
MAX_PARALLEL_REQUESTS = 40
DEFAULT_PROMPT_PATH = "default_prompt.txt"

# Load default prompt from file
DEFAULT_PROMPT = ""
try:
    with open(DEFAULT_PROMPT_PATH, 'r', encoding='utf-8') as f:
        DEFAULT_PROMPT = f.read()
        logger.info(f"Loaded default prompt from {DEFAULT_PROMPT_PATH}")
except Exception as e:
    logger.error(f"Error loading default prompt: {str(e)}")

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        # Check if files were uploaded
        if 'novel_file' not in request.files:
            flash('Файл не найден', 'danger')
            return redirect(url_for('index'))
        
        novel_file = request.files['novel_file']
        
        # If user didn't select a file
        if novel_file.filename == '':
            flash('Файл не выбран', 'danger')
            return redirect(url_for('index'))
        
        # Set default languages - auto-detect source and Russian as target
        source_lang = 'auto'
        target_lang = 'ru'
        
        # Use default prompt from file or get custom prompt from text input
        custom_prompt = DEFAULT_PROMPT
        
        if request.form.get('custom_prompt'):
            custom_prompt = request.form.get('custom_prompt')
        
        # Validate and save the novel file
        if novel_file and allowed_file(novel_file.filename):
            filename = secure_filename(novel_file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            novel_file.save(filepath)
            
            # Read the text file
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Generate a unique session ID for this translation job
            session_id = str(int(time.time()))
            session[f'translation_job_{session_id}'] = {
                'original_filename': filename,
                'filepath': filepath,
                'total_tokens': count_tokens(text),
                'status': 'processing',
                'progress': 0,
                'source_lang': source_lang,
                'target_lang': target_lang,
                'custom_prompt': custom_prompt
            }
            
            # Start the background translation task
            return jsonify({
                'success': True,
                'message': 'Файл успешно загружен, перевод начат.',
                'job_id': session_id
            })
        else:
            flash('Неверный формат файла. Разрешены только файлы .txt', 'danger')
            return redirect(url_for('index'))
    
    except Exception as e:
        logger.error(f"Error in upload: {str(e)}")
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/translate/<job_id>', methods=['POST'])
async def translate(job_id):
    try:
        job_key = f'translation_job_{job_id}'
        if job_key not in session:
            return jsonify({'success': False, 'message': 'Translation job not found'})
        
        job = session[job_key]
        filepath = job['filepath']
        
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Chunk the text with context
        chunks = chunk_text(text, chunk_size=4000, context_size=1000)
        
        # Get custom parameters
        source_lang = job['source_lang']
        target_lang = job['target_lang']
        custom_prompt = job['custom_prompt']
        
        # Start translation process
        translation_results = await translate_chunks(
            chunks, 
            job_id, 
            MAX_PARALLEL_REQUESTS, 
            app, 
            source_lang, 
            target_lang, 
            custom_prompt
        )
        
        # Join all translated chunks
        final_translation = join_translations(translation_results)
        
        # Save the translated file
        output_filename = f"{job['original_filename'].rsplit('.', 1)[0]}_translated_{target_lang}.txt"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_translation)
        
        # Update job status
        job['status'] = 'completed'
        job['progress'] = 100
        job['output_path'] = output_path
        job['output_filename'] = output_filename
        session[job_key] = job
        
        return jsonify({
            'success': True, 
            'message': 'Translation completed', 
            'output_filename': output_filename
        })
    
    except Exception as e:
        logger.error(f"Error in translation: {str(e)}")
        if job_key in session:
            job = session[job_key]
            job['status'] = 'failed'
            session[job_key] = job
        
        return jsonify({
            'success': False,
            'message': f'Translation failed: {str(e)}'
        })

@app.route('/check_progress/<job_id>')
def check_progress(job_id):
    job_key = f'translation_job_{job_id}'
    if job_key not in session:
        return jsonify({'success': False, 'message': 'Translation job not found'})
    
    job = session[job_key]
    return jsonify({
        'status': job['status'],
        'progress': job['progress']
    })

@app.route('/download/<job_id>')
def download_translation(job_id):
    job_key = f'translation_job_{job_id}'
    if job_key not in session:
        flash('Translation job not found', 'danger')
        return redirect(url_for('index'))
    
    job = session[job_key]
    if job['status'] != 'completed':
        flash('Translation is not completed yet', 'warning')
        return redirect(url_for('index'))
    
    return send_file(
        job['output_path'],
        as_attachment=True,
        download_name=job['output_filename']
    )

@app.route('/update_progress/<job_id>', methods=['POST'])
def update_progress(job_id):
    data = request.json
    job_key = f'translation_job_{job_id}'
    
    if job_key in session:
        job = session[job_key]
        job['progress'] = data.get('progress', job['progress'])
        session[job_key] = job
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Job not found'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
