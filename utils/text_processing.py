import tiktoken

def count_tokens(text):
    """
    Count the number of tokens in a text using tiktoken.
    
    Args:
        text (str): The text to count tokens for
        
    Returns:
        int: The number of tokens
    """
    # Using cl100k_base encoder which is used for GPT-4 and ChatGPT
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception:
        # Fallback to approximate token count if tiktoken fails
        return len(text.split()) * 1.3  # Approximate token count

def chunk_text(text, chunk_size=4000, context_size=1000):
    """
    Split text into chunks with overlapping context.
    
    Args:
        text (str): The text to split
        chunk_size (int): Maximum size of each chunk in tokens
        context_size (int): Size of the context to preserve between chunks
        
    Returns:
        list: List of dictionaries with text chunks and their positions
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)
        
        chunks = []
        i = 0
        chunk_id = 0
        
        while i < len(tokens):
            # Determine end of current chunk
            end = min(i + chunk_size, len(tokens))
            
            # Get context from previous chunk if possible
            start_with_context = max(0, i - context_size) if i > 0 else 0
            
            # Extract the chunk with context
            chunk_tokens = tokens[start_with_context:end]
            chunk_text = encoding.decode(chunk_tokens)
            
            chunks.append({
                'id': chunk_id,
                'text': chunk_text,
                'start_pos': start_with_context,
                'end_pos': end,
                'is_first': i == 0,
                'is_last': end == len(tokens),
                'has_prefix_context': i > 0,
                'context_size': i - start_with_context if i > 0 else 0
            })
            
            # Move to next chunk
            i = end
            chunk_id += 1
            
        return chunks
    
    except Exception:
        # Fallback to sentence-based chunking if tiktoken fails
        import re
        
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ""
        previous_context = ""
        chunk_id = 0
        
        for sentence in sentences:
            temp_chunk = current_chunk + " " + sentence if current_chunk else sentence
            
            # Approximate token count
            if len(temp_chunk.split()) > chunk_size:
                # Save current chunk
                chunks.append({
                    'id': chunk_id,
                    'text': previous_context + current_chunk if previous_context else current_chunk,
                    'start_pos': 0,  # Approximation
                    'end_pos': 0,    # Approximation
                    'is_first': chunk_id == 0,
                    'is_last': False,
                    'has_prefix_context': bool(previous_context),
                    'context_size': len(previous_context.split()) if previous_context else 0
                })
                
                # Keep context for next chunk
                words = current_chunk.split()
                if len(words) > context_size:
                    previous_context = " ".join(words[-context_size:]) + " "
                else:
                    previous_context = current_chunk + " "
                
                # Reset current chunk
                current_chunk = sentence
                chunk_id += 1
            else:
                current_chunk = temp_chunk
        
        # Add the last chunk
        if current_chunk:
            chunks.append({
                'id': chunk_id,
                'text': previous_context + current_chunk if previous_context else current_chunk,
                'start_pos': 0,  # Approximation
                'end_pos': 0,    # Approximation
                'is_first': chunk_id == 0,
                'is_last': True,
                'has_prefix_context': bool(previous_context),
                'context_size': len(previous_context.split()) if previous_context else 0
            })
        
        return chunks

def join_translations(translated_chunks):
    """
    Join translated chunks together, removing overlapping context.
    
    Args:
        translated_chunks (list): List of dictionaries with translated chunks
        
    Returns:
        str: Joined translation
    """
    # Sort chunks by ID to ensure correct order
    sorted_chunks = sorted(translated_chunks, key=lambda x: x['id'])
    
    final_text = ""
    
    for i, chunk in enumerate(sorted_chunks):
        text = chunk['translated_text']
        
        # For chunks with context, try to find where the actual content starts
        if i > 0 and chunk.get('has_prefix_context'):
            try:
                # Try to find the end of the overlapping context
                # This is an approximation and might not always work perfectly
                encoding = tiktoken.get_encoding("cl100k_base")
                prev_chunk_text = sorted_chunks[i-1]['translated_text']
                
                # Take the last part of the previous chunk as reference
                reference_tokens = encoding.encode(prev_chunk_text)[-100:]
                reference_text = encoding.decode(reference_tokens)
                
                # Find where the new content starts after the context
                overlap_pos = text.find(reference_text)
                
                if overlap_pos != -1:
                    # Skip the overlapping part
                    text = text[overlap_pos + len(reference_text):]
                else:
                    # If we can't find a clear overlap, use a simple heuristic
                    # Just skip approximately the context size
                    context_size = chunk.get('context_size', 0)
                    if context_size > 0:
                        # Rough estimation: 1 token ≈ 4 characters
                        text = text[context_size * 4:]
            except Exception:
                # If token-based approach fails, use a simpler method
                # Just append the text as is - some duplication may occur
                pass
        
        final_text += text
    
    return final_text
