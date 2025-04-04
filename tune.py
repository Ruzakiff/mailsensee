#!/usr/bin/env python3
"""
tune.py - Extract the most distinctive voice content from already filtered emails.

This script takes the output from findvoice.py and further filters it to retain
only the most distinctive examples that reveal the writer's unique voice and style.
"""

import os
import re
import argparse
import asyncio
import time
from typing import List, Dict, Any, Tuple
import tiktoken
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

# Load environment variables from .env file (including OPENAI_API_KEY)
load_dotenv()

# Get API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY environment variable. Set this in a .env file or export it.")

# Default model and token settings
DEFAULT_MODEL = "gpt-4o"
DEFAULT_CHUNK_SIZE = 8192  # tokens per chunk
DEFAULT_OVERLAP = 200      # token overlap between chunks
DEFAULT_MAX_TOKENS = 4096  # max tokens for completion

# The prompt for extracting distinctive voice content
DISTINCTIVE_PROMPT = """i just want the raw text email content no formatting no headers no metadata, just whatever text content is in email bodys
INPUT CORPUS:
{chunk}
"""



def get_encoder(model: str) -> tiktoken.Encoding:
    """Get the appropriate tokenizer for the specified model."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")  # Default encoding
    return encoding

def count_tokens(text: str, model: str) -> int:
    """Count the number of tokens in a text string."""
    encoder = get_encoder(model)
    return len(encoder.encode(text))

def split_into_chunks(text: str, chunk_size: int, overlap: int, model: str) -> List[str]:
    """Split text into chunks, being careful to preserve email boundaries."""
    # Use regex to find email boundaries
    email_pattern = r"(?:^|\n\n)(?:Email ID:|={20,}|---\n\n)[\s\S]+?(?=\n\n(?:Email ID:|={20,}|---\n\n)|$)"
    emails = re.findall(email_pattern, text, re.MULTILINE)
    
    if not emails:
        # If no emails found, fall back to basic chunking
        return basic_chunking(text, chunk_size, overlap, model)
    
    chunks = []
    current_chunk = ""
    current_tokens = 0
    encoder = get_encoder(model)
    
    for email in emails:
        email_tokens = len(encoder.encode(email))
        
        # If a single email is larger than chunk_size, we need to split it
        if email_tokens > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
                current_tokens = 0
            
            # Split this large email and add it as its own chunk(s)
            email_chunks = basic_chunking(email, chunk_size, overlap, model)
            chunks.extend(email_chunks)
            continue
        
        # If adding this email would exceed chunk_size, start a new chunk
        if current_tokens + email_tokens > chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = email
            current_tokens = email_tokens
        else:
            current_chunk += "\n\n" + email if current_chunk else email
            current_tokens += email_tokens
    
    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def basic_chunking(text: str, chunk_size: int, overlap: int, model: str) -> List[str]:
    """Basic text chunking when email boundaries can't be preserved."""
    encoder = get_encoder(model)
    tokens = encoder.encode(text)
    chunks = []
    
    i = 0
    while i < len(tokens):
        # Get chunk_size tokens or whatever is left
        chunk_end = min(i + chunk_size, len(tokens))
        chunk_tokens = tokens[i:chunk_end]
        chunk_text = encoder.decode(chunk_tokens)
        chunks.append(chunk_text)
        
        # Move forward by chunk_size - overlap
        i += max(1, chunk_size - overlap)
    
    return chunks

async def process_chunk(chunk: str, model: str, max_tokens: int, chunk_number: int, 
                         total_chunks: int, output_file: str, file_lock) -> int:
    """Process a text chunk through the OpenAI API and write results to file immediately."""
    prompt = DISTINCTIVE_PROMPT.format(chunk=chunk)
    
    # Create AsyncOpenAI client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    # Implement retry logic with increased retries for SSL errors
    max_retries = 5
    base_retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            print(f"Processing chunk {chunk_number}/{total_chunks}...")
            
            # Use the official OpenAI client to make the API call
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You clean email metadata to only the raw body text Format your response as valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0,  # Low temperature for consistent filtering
                response_format={"type": "json_object"}  # Ensure JSON format output
            )
            
            filtered_content = response.choices[0].message.content
            
            # Debug: Print the first 100 characters of the response
            print(f"Response (first 100 chars): {filtered_content[:100]}...")
            
            # Verify JSON validity before writing
            try:
                # Try to parse the JSON response
                if filtered_content.strip():
                    json_content = json.loads(filtered_content)
                    filtered_content = json.dumps(json_content, indent=2)  # Pretty-print JSON
                else:
                    print(f"Warning: Empty response received (attempt {attempt+1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(base_retry_delay * (attempt + 1))
                        continue
            except json.JSONDecodeError as e:
                print(f"Warning: Response is not valid JSON (attempt {attempt+1}): {e}")
                print(f"Response excerpt: {filtered_content[:200]}...")
                if attempt < max_retries - 1:
                    # Try again
                    await asyncio.sleep(base_retry_delay * (attempt + 1))
                    continue
            
            # Write this chunk's results to the output file immediately
            async with file_lock:
                with open(output_file, 'a', encoding='utf-8') as f:
                    f.write(filtered_content + "\n\n")
            
            output_tokens = count_tokens(filtered_content, model)
            print(f"✓ Processed chunk {chunk_number}/{total_chunks} - Tokens: {output_tokens}")
            return output_tokens
            
        except Exception as e:
            # General exception handling
            retry_delay = base_retry_delay * (attempt + 1)
            print(f"Error processing chunk {chunk_number}: {str(e)}")
            print(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
    
    print(f"Failed to process chunk {chunk_number} after {max_retries} attempts")
    return 0

async def process_chunks_parallel(chunks: List[str], model: str, max_tokens: int, output_file: str) -> int:
    """Process all chunks in parallel with rate limiting and write to file as they complete."""
    # Initialize output file with empty content
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("")  # Create or clear the file
    
    # Create a lock for file access
    file_lock = asyncio.Lock()
    
    # Create tasks for all chunks at once with some spreading
    tasks = []
    for i, chunk in enumerate(chunks):
        # Add a tiny stagger to avoid exact simultaneous connections
        await asyncio.sleep(0.1)
        tasks.append(process_chunk(chunk, model, max_tokens, i+1, len(chunks), output_file, file_lock))
    
    # Start all requests simultaneously but with slight staggering
    print(f"Starting parallel processing of {len(chunks)} chunks...")
    
    # Process all chunks and wait for them to complete
    output_tokens = await asyncio.gather(*tasks, return_exceptions=False)
    
    # Return the total number of output tokens
    return sum(token_count for token_count in output_tokens if isinstance(token_count, int))

async def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Extract distinctive voice content from filtered emails")
    parser.add_argument("input_file", nargs="?", default="filtered_voice_emails.txt",
                      help="Path to the filtered email corpus (default: filtered_voice_emails.txt)")
    parser.add_argument("--output", "-o", default="distinctive_voice_emails.txt", 
                       help="Output file path (default: distinctive_voice_emails.txt)")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                       help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--chunk-size", "-c", type=int, default=DEFAULT_CHUNK_SIZE,
                       help=f"Token size for each chunk (default: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP,
                       help=f"Token overlap between chunks (default: {DEFAULT_OVERLAP})")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                       help=f"Maximum tokens for model response (default: {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--skip-to", type=int, default=0,
                       help="Skip to a specific chunk number (useful for resuming after errors)")
    
    args = parser.parse_args()
    
    # Verify input file exists
    if not os.path.isfile(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        return 1
    
    # Read the input file
    print(f"Reading input file: {args.input_file}")
    with open(args.input_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Calculate token count
    token_count = count_tokens(text, args.model)
    print(f"Total input tokens: {token_count}")
    
    # Split into chunks
    print(f"Splitting text into chunks of {args.chunk_size} tokens with {args.overlap} token overlap")
    chunks = split_into_chunks(text, args.chunk_size, args.overlap, args.model)
    print(f"Created {len(chunks)} chunks")
    
    # Handle skip-to option
    if args.skip_to > 0 and args.skip_to <= len(chunks):
        print(f"Skipping to chunk {args.skip_to}/{len(chunks)}")
        chunks = chunks[args.skip_to-1:]
    
    # Process chunks in parallel and write to file as they complete
    start_time = time.time()
    print(f"Processing chunks with {args.model} in parallel...")
    output_token_count = await process_chunks_parallel(chunks, args.model, args.max_tokens, args.output)
    
    elapsed_time = time.time() - start_time
    print(f"Processing completed in {elapsed_time:.2f} seconds")
    print(f"Distinctive content saved to: {args.output}")
    
    # Calculate token counts and reduction
    reduction = 100 - (output_token_count / token_count * 100)
    print(f"Input tokens: {token_count}, Output tokens: {output_token_count}")
    print(f"Reduced content by {reduction:.2f}%")
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())
