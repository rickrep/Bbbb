import os
import json
import asyncio
import aiohttp
import logging
from flask import session

# Configure logging
logger = logging.getLogger(__name__)

async def translate_chunk(session, chunk, source_lang, target_lang, custom_prompt, api_key):
    """
    Translate a single text chunk using DeepSeek API
    
    Args:
        session (aiohttp.ClientSession): HTTP session
        chunk (dict): Text chunk with metadata
        source_lang (str): Source language code (or 'auto' for auto-detection)
        target_lang (str): Target language code
        custom_prompt (str): Custom translation instructions
        api_key (str): DeepSeek API key
        
    Returns:
        dict: Translated chunk with metadata
    """
    # Default system prompt if none provided
    if not custom_prompt:
        if source_lang == 'auto':
            system_prompt = f"""Вы профессиональный литературный переводчик. 
            Переведите следующий текст на русский язык.
            Сохраняйте оригинальный стиль, тон и литературное качество.
            Сохраняйте разбивку на абзацы и форматирование."""
        else:
            system_prompt = f"""Вы профессиональный литературный переводчик. 
            Переведите следующий текст с {source_lang} на {target_lang}. 
            Сохраняйте оригинальный стиль, тон и литературное качество.
            Сохраняйте разбивку на абзацы и форматирование."""
    else:
        system_prompt = custom_prompt
    
    # Add context information to the prompt if needed
    if chunk.get('has_prefix_context'):
        user_prompt = f"""Этот текст является частью большого документа. Первая часть (примерно {chunk.get('context_size', 0)} токенов) предоставлена только для контекста и уже была переведена.
        
        Переведите только НОВЫЙ контент, который следует после контекстной части, сохраняя согласованность со стилем и терминологией, установленными в контекстной части.
        
        Текст: {chunk['text']}"""
    else:
        user_prompt = f"Текст: {chunk['text']}"
    
    # Prepare payload for DeepSeek API
    url = "https://api.deepseek.com/v1/chat/completions"
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": 0.3,  # Lower temperature for more consistent translations
        "max_tokens": 8000
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Make API request with retry mechanism
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Get the translated text from the API response
                    translated_text = data["choices"][0]["message"]["content"]
                    
                    # Return the chunk with the translation
                    return {
                        'id': chunk['id'],
                        'original_text': chunk['text'],
                        'translated_text': translated_text,
                        'has_prefix_context': chunk.get('has_prefix_context', False),
                        'context_size': chunk.get('context_size', 0)
                    }
                else:
                    error_data = await response.text()
                    logger.error(f"API error: {response.status}, {error_data}")
                    
                    if response.status == 429:  # Rate limit
                        # Wait longer between retries for rate limit errors
                        await asyncio.sleep(retry_delay * 2)
                    else:
                        await asyncio.sleep(retry_delay)
            
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            await asyncio.sleep(retry_delay)
    
    # If all retries failed, return error
    return {
        'id': chunk['id'],
        'original_text': chunk['text'],
        'translated_text': f"[TRANSLATION ERROR] Failed to translate chunk {chunk['id']}",
        'error': True
    }

async def update_job_progress(app, job_id, progress):
    """Update the progress of a translation job in the session"""
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:5000/update_progress/{job_id}"
        payload = {"progress": progress}
        headers = {"Content-Type": "application/json"}
        
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Failed to update progress: {str(e)}")
            return {"success": False}

async def translate_chunks(chunks, job_id, max_parallel, app, source_lang, target_lang, custom_prompt):
    """
    Translate multiple text chunks in parallel
    
    Args:
        chunks (list): List of text chunks to translate
        job_id (str): Unique job identifier
        max_parallel (int): Maximum number of parallel requests
        app (Flask): Flask application for context
        source_lang (str): Source language code
        target_lang (str): Target language code
        custom_prompt (str): Custom translation instructions
        
    Returns:
        list: List of translated chunks
    """
    # Get the DeepSeek API key from environment
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DeepSeek API key not found in environment variables. Set DEEPSEEK_API_KEY.")
    
    # Calculate total chunks for progress tracking
    total_chunks = len(chunks)
    completed_chunks = 0
    results = []
    
    # Using semaphore to limit concurrent API calls
    semaphore = asyncio.Semaphore(max_parallel)
    
    async def fetch_with_limit(chunk):
        nonlocal completed_chunks
        
        async with semaphore:
            result = await translate_chunk(
                client_session, 
                chunk, 
                source_lang, 
                target_lang, 
                custom_prompt,
                api_key
            )
            
            # Update progress
            completed_chunks += 1
            progress = int((completed_chunks / total_chunks) * 100)
            await update_job_progress(app, job_id, progress)
            
            return result
    
    async with aiohttp.ClientSession() as client_session:
        # Create tasks for all chunks
        tasks = [fetch_with_limit(chunk) for chunk in chunks]
        
        # Process chunks in parallel and collect results
        for completed_task in asyncio.as_completed(tasks):
            result = await completed_task
            results.append(result)
    
    # Sort results by chunk ID to maintain order
    sorted_results = sorted(results, key=lambda x: x['id'])
    
    # Check for errors
    errors = [r for r in sorted_results if r.get('error')]
    if errors:
        logger.error(f"Translation completed with {len(errors)} chunk errors")
    
    return sorted_results
