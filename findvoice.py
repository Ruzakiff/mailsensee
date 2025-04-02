#!/usr/bin/env python3
"""
findvoice.py - Extract authentic voice content from email corpus.

This script chunks a large text file into manageable pieces, processes them 
through OpenAI's API to filter out content that doesn't represent the sender's 
authentic voice, and saves the filtered content.
"""

import os
import re
import argparse
import asyncio
import time
from typing import List, Dict, Any, Tuple
import tiktoken
import aiohttp
import json
from dotenv import load_dotenv

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

# Filter prompt template
FILTER_PROMPT = """
You are processing a dataset of sent emails to extract only those that genuinely capture the sender's authentic voice, writing style, and communication patterns. Approach this as a filtering task with clear signal/noise discrimination:

## FILTERING CRITERIA - REMOVE:

1. EMPTY OR NEAR-EMPTY EMAILS
   - Emails with no content or only "Attached" or similar minimal text
   - Single line responses with no substantive content

2. URL/LINK COLLECTIONS
   - Lists of URLs or bookmarks with no personal commentary
   - References to files or attachments without meaningful message content

3. NOTES-TO-SELF
   - Lists that appear to be personal reminders
   - Fragments of incomplete thoughts or drafts
   - Repeated/duplicate content with minor variations

4. PURELY TRANSACTIONAL
   - One-line administrative responses (e.g., "5447 Potter St, Pittsburgh, PA 15232")
   - Emails that only contain form information

## RETENTION CRITERIA - KEEP:

1. AUTHENTIC PERSONAL COMMUNICATION
   - Emails with natural conversational flow
   - Messages explaining concepts or providing instructions
   - Emails showing opinion, reasoning, or decision-making

2. DISTINCTIVE EXPRESSIONS
   - Content with unique phrasing or vocabulary choices
   - Messages exhibiting humor, enthusiasm, or other emotional tones
   - Writing that reflects the sender's thought process

3. ADVISORY CONTENT
   - Emails providing advice, feedback, or recommendations
   - Messages showing how the sender approaches explaining things

TASK:
1. Examine each email in this chunk
2. Output ONLY the complete text of emails that meet the retention criteria (with their headers)
3. Completely discard emails that should be filtered out
4. Keep the email format intact for retained emails
5. Include NO explanations or commentary in your response, just the filtered content

INPUT CHUNK:
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
    """Split the text into chunks of specified token size with overlap."""
    encoder = get_encoder(model)
    
    # Extract email boundaries for smart chunking
    email_pattern = r"(Email ID: [^\n]+\nDate: [^\n]+\nTo: [^\n]+\nSubject: [^\n]+\nYour Content:[\s\S]+?={80})"
    emails = re.findall(email_pattern, text)
    
    chunks = []
    current_chunk = ""
    current_tokens = 0
    
    for email in emails:
        email_tokens = len(encoder.encode(email))
        
        # If this email alone exceeds chunk size, we need to split it
        if email_tokens > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
                current_tokens = 0
            
            # Add a note that this is a large email that was split
            chunks.append(f"[Large email split into multiple chunks]\n{email[:chunk_size]}")
            continue
            
        # If adding this email would exceed the chunk size, start a new chunk
        if current_tokens + email_tokens > chunk_size:
            chunks.append(current_chunk)
            current_chunk = email
            current_tokens = email_tokens
        else:
            current_chunk += ("\n" if current_chunk else "") + email
            current_tokens += email_tokens
    
    # Add the last chunk if it has content
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

async def process_chunk(chunk: str, session: aiohttp.ClientSession, 
                        model: str, max_tokens: int, chunk_number: int, 
                        total_chunks: int) -> str:
    """Process a text chunk through the OpenAI API."""
    prompt = FILTER_PROMPT.format(chunk=chunk)
    
    # Prepare the API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise filter that keeps only emails showing authentic voice and style."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,  # Low temperature for consistent filtering
    }
    
    # Implement retry logic
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            print(f"Processing chunk {chunk_number}/{total_chunks}...")
            async with session.post("https://api.openai.com/v1/chat/completions", 
                                  headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    filtered_content = result["choices"][0]["message"]["content"]
                    print(f"✓ Processed chunk {chunk_number}/{total_chunks}")
                    return filtered_content
                else:
                    error_info = await response.text()
                    print(f"API error (status {response.status}): {error_info}")
                    if response.status == 429:  # Rate limit
                        wait_time = 20 * (attempt + 1)  # Exponential backoff
                        print(f"Rate limited. Waiting {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                    else:
                        await asyncio.sleep(retry_delay)
        except Exception as e:
            print(f"Error processing chunk {chunk_number}: {str(e)}")
            await asyncio.sleep(retry_delay)
    
    print(f"Failed to process chunk {chunk_number} after {max_retries} attempts")
    return f"[Processing failed for chunk {chunk_number}]"

async def process_chunks(chunks: List[str], model: str, max_tokens: int) -> str:
    """Process all chunks in parallel with rate limiting."""
    # Use connection pool to manage connections
    conn = aiohttp.TCPConnector(limit=5)  # Limit connections to avoid overwhelming the API
    timeout = aiohttp.ClientTimeout(total=120)  # 2 minute timeout
    
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        # Create tasks for each chunk
        tasks = []
        for i, chunk in enumerate(chunks):
            # Add some delay between task creation to avoid rate limits
            await asyncio.sleep(0.5)
            tasks.append(process_chunk(chunk, session, model, max_tokens, i+1, len(chunks)))
        
        # Process chunks and collect results
        results = await asyncio.gather(*tasks)
        return "\n\n".join(results)

async def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Process email corpus to extract authentic voice")
    parser.add_argument("input_file", help="Path to the input email corpus text file")
    parser.add_argument("--output", "-o", default="filtered_voice_emails.txt", 
                       help="Output file path (default: filtered_voice_emails.txt)")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                       help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--chunk-size", "-c", type=int, default=DEFAULT_CHUNK_SIZE,
                       help=f"Token size for each chunk (default: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP,
                       help=f"Token overlap between chunks (default: {DEFAULT_OVERLAP})")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                       help=f"Maximum tokens for model response (default: {DEFAULT_MAX_TOKENS})")
    
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
    
    # Process chunks
    start_time = time.time()
    print(f"Processing chunks with {args.model}...")
    filtered_content = await process_chunks(chunks, args.model, args.max_tokens)
    
    # Write output file
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(filtered_content)
    
    elapsed_time = time.time() - start_time
    print(f"Processing completed in {elapsed_time:.2f} seconds")
    print(f"Filtered content saved to: {args.output}")
    
    # Calculate token counts
    output_token_count = count_tokens(filtered_content, args.model)
    reduction = 100 - (output_token_count / token_count * 100)
    print(f"Input tokens: {token_count}, Output tokens: {output_token_count}")
    print(f"Reduced content by {reduction:.2f}%")
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())