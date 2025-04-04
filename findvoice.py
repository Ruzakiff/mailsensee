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
import ssl
from typing import List, Dict, Any, Tuple
import tiktoken
import json
from dotenv import load_dotenv
import concurrent.futures
from openai import OpenAI, AsyncOpenAI
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

# Second-stage filter prompt template
SECOND_STAGE_PROMPT = """
You are analyzing a corpus of emails to create an optimal dataset for training a generative AI model to mimic the author's writing style with such precision that readers cannot distinguish between AI-generated and authentic emails.

Approach this task using Andrej Karpathy's first principles thinking about model training and generalization:

## FUNDAMENTAL PRINCIPLES:

1. INFORMATION DENSITY
   - Each selected example should contribute unique stylistic information
   - Maximize the bits-per-token ratio by selecting emails that demonstrate clear stylistic patterns
   - Prioritize emails with distinctive vocabulary, sentence structures, and rhetorical devices

2. DISTRIBUTIONAL COVERAGE
   - Ensure the dataset covers the full distribution of the author's linguistic patterns
   - Include examples across different emotional states (formal, casual, excited, concerned, etc.)
   - Select examples with varying lengths, structures, and purposes

3. CONTEXT WINDOW OPTIMIZATION
   - Select emails that demonstrate how the author adapts tone for different recipients/situations
   - Include examples that show complete thought patterns and reasoning chains
   - Preserve emails that demonstrate characteristic opening/closing patterns

4. PATTERN GENERALIZATION VS. MEMORIZATION
   - Focus on examples that reveal generalizable patterns rather than one-off anomalies
   - Avoid highly specialized content unless it demonstrates a core stylistic element
   - Identify and include "archetype emails" that the author produces repeatedly with variations

## FILTERING METHODOLOGY:

1. CLUSTERING & SELECTION
   - Group stylistically similar emails and select representative examples from each cluster
   - For each type of email (informational, persuasive, personal, etc.), include diverse examples
   - When two emails demonstrate the same stylistic feature, keep the clearer/stronger example

2. INFORMATION GAIN RANKING
   - Prioritize emails that contain unique phrases, idioms, or syntactic structures
   - Evaluate each email's contribution to the overall stylistic fingerprint
   - Keep emails that demonstrate the author's distinctive approaches to common situations

3. REDUNDANCY ELIMINATION
   - Remove examples that don't add new information about the author's style
   - When similar emails exist, keep ones with the clearest demonstrations of style
   - Eliminate emails that follow generic templates unless they contain personal modifications

4. HIGHER-ORDER EFFECTS AWARENESS
   - Ensure the final dataset represents the author's best communication practices

TASK:
1. Examine each email in this corpus
2. Output ONLY the complete text of the most valuable emails that meet the criteria above
3. Completely discard emails that are redundant or don't add new stylistic information
4. Keep the email format intact for retained emails
5. Include NO explanations or commentary in your response, just the filtered content
6. IMPORTANT: The output must be under 4000 tokens total

INPUT CONTENT:
{filtered_content}
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

async def process_chunk(chunk: str, model: str, max_tokens: int, chunk_number: int, 
                        total_chunks: int, output_file: str, file_lock) -> int:
    """Process a text chunk through the OpenAI API and write results to file immediately."""
    prompt = FILTER_PROMPT.format(chunk=chunk)
    
    # Create AsyncOpenAI client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    # Implement retry logic with increased retries for SSL errors
    max_retries = 5  # Increased from 3 to 5
    base_retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            print(f"Processing chunk {chunk_number}/{total_chunks}...")
            
            # Use the official OpenAI client to make the API call
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a precise filter that keeps only emails showing authentic voice and style."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0  # Low temperature for consistent filtering
            )
            
            filtered_content = response.choices[0].message.content
            
            # Write this chunk's results to the output file immediately
            async with file_lock:
                with open(output_file, 'a', encoding='utf-8') as f:
                    f.write(filtered_content + "\n\n")
            
            output_tokens = count_tokens(filtered_content, model)
            print(f"✓ Processed chunk {chunk_number}/{total_chunks} - Tokens: {output_tokens}")
            return output_tokens
            
        except ssl.SSLError as e:
            # Special handling for SSL errors
            retry_delay = base_retry_delay * (attempt + 1) * 2  # Longer delay for SSL errors
            print(f"SSL Error processing chunk {chunk_number}: {str(e)}")
            print(f"This is likely a temporary network issue. Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
        except Exception as e:
            # General exception handling
            retry_delay = base_retry_delay * (attempt + 1)
            print(f"Error processing chunk {chunk_number}: {str(e)}")
            print(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
    
    print(f"Failed to process chunk {chunk_number} after {max_retries} attempts")
    
    # Write a failure notice to the output file
    error_message = f"[Processing failed for chunk {chunk_number}]"
    async with file_lock:
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(error_message + "\n\n")
    
    return 0  # Return 0 tokens for a failed chunk

async def apply_second_stage_filter(content: str, model: str, max_tokens: int, target_tokens: int = 4000) -> str:
    """Apply a second-stage filter to further reduce content to under target_tokens."""
    content_tokens = count_tokens(content, model)
    if content_tokens <= target_tokens:
        print(f"Content already under {target_tokens} tokens, skipping second-stage filter")
        return content
    
    print(f"Applying second-stage filter to reduce content from {content_tokens} tokens to under {target_tokens} tokens...")
    
    # If content is too large for context window, we need to chunk it again
    model_max_tokens = 120000  # Conservative estimate for model's max context length
    prompt_template_tokens = count_tokens(SECOND_STAGE_PROMPT.format(filtered_content=""), model)
    available_tokens = model_max_tokens - prompt_template_tokens - 1000  # Extra buffer
    
    if content_tokens > available_tokens:
        print(f"Content too large ({content_tokens} tokens) for second-stage filtering in one pass")
        print(f"Splitting into smaller chunks for incremental processing...")
        
        # Extract individual emails from the content
        email_pattern = r"(Email ID: [^\n]+\nDate: [^\n]+\nTo: [^\n]+\nSubject: [^\n]+\nYour Content:[\s\S]+?={80})"
        emails = re.findall(email_pattern, content)
        
        if not emails:
            print("Warning: Couldn't identify individual emails in the content. Using basic chunking.")
            # If we can't identify emails, use simple chunking by tokens
            encoder = get_encoder(model)
            tokens = encoder.encode(content)
            
            chunks = []
            chunk_size = available_tokens
            for i in range(0, len(tokens), chunk_size):
                chunk_tokens = tokens[i:i + chunk_size]
                chunks.append(encoder.decode(chunk_tokens))
        else:
            print(f"Identified {len(emails)} individual emails for incremental processing")
            chunks = [emails[i:i+50] for i in range(0, len(emails), 50)]
            chunks = ["\n\n".join(chunk_emails) for chunk_emails in chunks]
        
        # Process each chunk with the second stage filter and combine results
        combined_result = ""
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)} for second-stage filtering...")
            # Calculate proportional token target for this chunk
            proportional_target = max(int(target_tokens/len(chunks)), 1000)
            chunk_result = await process_single_second_stage_chunk(chunk, model, max_tokens, proportional_target)
            combined_result += chunk_result + "\n\n"
            
            # Monitor total tokens
            current_tokens = count_tokens(combined_result, model)
            print(f"Current total tokens after chunk {i+1}: {current_tokens}/{target_tokens}")
            
            # Stop if we've reached or exceeded target
            if current_tokens >= target_tokens:
                print(f"Reached target token count, stopping incremental processing")
                break
        
        # Final pass to ensure we meet target token count
        final_tokens = count_tokens(combined_result, model)
        if final_tokens > target_tokens:
            print(f"Final result ({final_tokens} tokens) exceeds target ({target_tokens}). Running final optimization pass...")
            # If still over target, do one final filtering pass on the combined result
            if final_tokens < available_tokens:
                combined_result = await process_single_second_stage_chunk(combined_result, model, max_tokens, target_tokens)
            else:
                # If too large, truncate to roughly target tokens
                print("Content still too large for final pass, truncating to target token count...")
                encoder = get_encoder(model)
                tokens = encoder.encode(combined_result)
                combined_result = encoder.decode(tokens[:target_tokens])
        
        return combined_result
    
    # If content fits in context window, process normally with second stage filter
    return await process_single_second_stage_chunk(content, model, max_tokens, target_tokens)

async def process_single_second_stage_chunk(content: str, model: str, max_tokens: int, target_tokens: int) -> str:
    """Process a single chunk through the second-stage filter."""
    # Update the prompt to specify the target token count for this chunk
    prompt = SECOND_STAGE_PROMPT.format(filtered_content=content)
    
    # Create AsyncOpenAI client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    max_retries = 5
    base_retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"You are an expert dataset curator focusing on stylistic signal optimization. Your task is to filter content to under {target_tokens} tokens while preserving the most valuable stylistic examples."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.1  # Low temperature for consistent filtering
            )
            
            optimized_content = response.choices[0].message.content
            token_count = count_tokens(optimized_content, model)
            
            print(f"Second-stage filtering complete for chunk. Tokens: {token_count}/{target_tokens}")
            
            return optimized_content
            
        except Exception as e:
            retry_delay = base_retry_delay * (attempt + 1)
            print(f"Error in second-stage filtering: {str(e)}")
            print(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
    
    print(f"Failed to apply second-stage filter after {max_retries} attempts")
    return ""  # Return empty string if filtering fails completely

async def process_chunks_parallel(chunks: List[str], model: str, max_tokens: int, output_file: str, 
                                 apply_second_filter: bool = False) -> int:
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
    
    # Return the total number of output tokens from first-stage filtering
    first_stage_tokens = sum(token_count for token_count in output_tokens if isinstance(token_count, int))
    print(f"First-stage filtering complete. Total tokens: {first_stage_tokens}")
    
    # Apply second-stage filtering if requested
    if apply_second_filter:
        # Read the first-stage output
        with open(output_file, 'r', encoding='utf-8') as f:
            first_stage_content = f.read()
        
        print(f"Applying second-stage filter to first-stage output ({first_stage_tokens} tokens)...")
        
        # Apply second-stage filter
        optimized_content = await apply_second_stage_filter(first_stage_content, model, max_tokens)
        optimized_tokens = count_tokens(optimized_content, model)
        
        # Save the optimized content to a new file
        optimized_file = output_file.replace('.txt', '_optimized.txt')
        with open(optimized_file, 'w', encoding='utf-8') as f:
            f.write(optimized_content)
        
        print(f"Optimized content saved to: {optimized_file} ({optimized_tokens} tokens)")
        
        # Return the token count of the second-stage output
        return optimized_tokens
    
    return first_stage_tokens

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
    parser.add_argument("--skip-to", type=int, default=0,
                       help="Skip to a specific chunk number (useful for resuming after errors)")
    parser.add_argument("--optimize", "-opt", action="store_true",
                       help="Apply second-stage optimization to reduce to under 4000 tokens")
    parser.add_argument("--target-tokens", type=int, default=4000,
                       help="Target token count for second-stage optimization (default: 4000)")
    
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
    output_token_count = await process_chunks_parallel(
        chunks, args.model, args.max_tokens, args.output, args.optimize)
    
    elapsed_time = time.time() - start_time
    print(f"Processing completed in {elapsed_time:.2f} seconds")
    
    if args.optimize:
        print(f"Final optimized content saved to: {args.output.replace('.txt', '_optimized.txt')}")
    else:
        print(f"Filtered content saved to: {args.output}")
    
    # Calculate token counts and reduction
    reduction = 100 - (output_token_count / token_count * 100)
    print(f"Input tokens: {token_count}, Output tokens: {output_token_count}")
    print(f"Reduced content by {reduction:.2f}%")
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())