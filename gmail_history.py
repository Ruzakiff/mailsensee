from mailsense.gmail import GmailClient
import base64
import time
import re
import email
import html
import os
import argparse
from mailsense.storage import read_file, write_file, append_to_file, file_exists

def clean_html(html_content):
    """Remove HTML tags from content."""
    if not html_content:
        return ""
    # Convert HTML entities and remove tags
    text = html.unescape(html_content)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def decode_body(body_data):
    """Decode the base64 body data."""
    if not body_data:
        return ""
    try:
        # The body data is base64url encoded
        body_bytes = base64.urlsafe_b64decode(body_data + '=' * (4 - len(body_data) % 4))
        return body_bytes.decode('utf-8')
    except Exception as e:
        print(f"Error decoding email body: {e}")
        return "[Body decoding error]"

def extract_your_content(body, email_date):
    """Extract only the content that the user wrote (not quoted replies)."""
    if not body:
        return ""
    
    # Split into lines
    lines = body.split('\n')
    your_content = []
    
    # Common patterns for quoted content start
    quoted_start_patterns = [
        r'^On .+ wrote:$',           # Standard Gmail quote format
        r'^>.+',                     # Line starting with >
        r'^From: ',                  # Quoted headers
        r'^Date: ',
        r'^Subject: ',
        r'^To: ',
        r'^Sent from ',              # Common mobile signatures
        r'^-+Original Message-+',    # Forwarded message markers
        r'^-+Forwarded message-+',
        r'^_+',                      # Horizontal rule markers
    ]
    
    # Signature markers - these typically end the user's content
    signature_patterns = [
        r'^--\s*$',                  # Standard signature marker
        r'^__+\s*$',                 # Underscores as signature marker
        r'^-+\s*$',                  # Dashes as signature marker
        r'^Regards,\s*$',            # Common signature starter
        r'^Best,\s*$',               # Common signature starter
        r'^Thanks,\s*$',             # Common signature starter
        r'^Thank you,\s*$',          # Common signature starter
        r'^Sincerely,\s*$',          # Common signature starter
        r'^Cheers,\s*$',             # Common signature starter
    ]
    
    # Combine start patterns
    start_pattern = '|'.join(f'({p})' for p in quoted_start_patterns)
    
    # Combine signature patterns
    sig_pattern = '|'.join(f'({p})' for p in signature_patterns)
    
    in_quote = False
    reached_signature = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Check if this line starts a quote
        if re.match(start_pattern, line_stripped):
            in_quote = True
            continue
        
        # Check if this line is likely a signature marker
        if not in_quote and your_content and re.match(sig_pattern, line_stripped):
            reached_signature = True
        
        # Special case: if we see a pattern like "On [date], [name] <[email]> wrote:",
        # everything after that is a quoted reply
        if re.match(r'^On .+, .+ wrote:$', line_stripped):
            in_quote = True
            continue
        
        # If we're not in a quote and haven't reached signature, add the line
        if not in_quote and not reached_signature:
            # Skip empty lines at the start
            if not your_content and not line_stripped:
                continue
            your_content.append(line)
    
    # If we couldn't detect quotes, just return everything
    if not your_content and lines:
        return body
    
    # Join the lines back together
    result = '\n'.join(your_content)
    
    # Remove common automatic signatures that might not be caught by markers
    result = re.sub(r'\n+Sent from my iPhone\s*$', '', result)
    result = re.sub(r'\n+Sent from my Android\s*$', '', result)
    result = re.sub(r'\n+Get Outlook for (iOS|Android)\s*$', '', result)
    
    return result.strip()

def fetch_emails(user_id, query="in:sent after:2014/01/01 before:2022/01/01", limit=1000):
    """Fetch emails from Gmail and store in S3."""
    # Create the Gmail client
    client = GmailClient(user_id)
    
    print(f"Fetching emails matching query: {query}")
    print("This may take a while depending on how many emails you have.")
    
    # Prepare output file names
    output_file = "sent_emails.txt"
    progress_file = "email_fetch_progress.txt"
    
    # Initialize or read progress
    processed_ids = set()
    if file_exists(user_id, progress_file):
        progress_content = read_file(user_id, progress_file)
        processed_ids = set(line.strip() for line in progress_content.split('\n') if line.strip())
        print(f"Resuming from previous run, {len(processed_ids)} emails already processed.")
    
    # Create or clear the output file if no progress
    if not processed_ids:
        write_file(user_id, output_file, "")  # Create empty file
    
    # Initialize counters
    page_token = None
    total_fetched = 0
    limit_reached = False
    actual_processed = 0
    
    # Loop to handle pagination
    while not limit_reached:
        # Fetch a batch of emails
        try:
            results = client.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=100,
                pageToken=page_token
            ).execute()
        except Exception as e:
            print(f"Error fetching messages: {e}")
            print("Waiting 30 seconds before retrying...")
            time.sleep(30)
            continue
        
        messages = results.get('messages', [])
        if not messages:
            print("No more messages to fetch.")
            break
            
        batch_size = len(messages)
        print(f"Processing batch of {batch_size} emails...")
        
        batch_content = ""  # Accumulate content before writing to S3
        new_processed_ids = ""  # Accumulate processed IDs
        
        # Process each message
        for i, message in enumerate(messages):
            msg_id = message['id']
            
            # Skip if already processed
            if msg_id in processed_ids:
                continue
            
            # Check if we've reached the limit
            if total_fetched >= limit:
                print(f"Reached the limit of {limit} emails.")
                limit_reached = True
                break
            
            try:
                # Get full message details
                msg = client.service.users().messages().get(
                    userId='me', id=msg_id, format='full'
                ).execute()
                
                # Extract email details
                headers = msg['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                
                # Extract body
                body = ""
                if 'parts' in msg['payload']:
                    for part in msg['payload']['parts']:
                        if part['mimeType'] == 'text/plain':
                            body = decode_body(part['body'].get('data', ''))
                            break
                        elif part['mimeType'] == 'text/html' and not body:
                            body = clean_html(decode_body(part['body'].get('data', '')))
                elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                    body = decode_body(msg['payload']['body'].get('data', ''))
                
                # Extract only the content you wrote
                your_content = extract_your_content(body, date)
                
                # Format the email for storage
                email_entry = f"Email ID: {msg_id}\n"
                email_entry += f"Date: {date}\n"
                email_entry += f"To: {to}\n"
                email_entry += f"Subject: {subject}\n"
                email_entry += "Your Content:\n"
                email_entry += your_content
                email_entry += "\n" + "="*80 + "\n\n"
                
                # Add to batch content
                batch_content += email_entry
                
                # Add to processed IDs
                new_processed_ids += f"{msg_id}\n"
                
                # Add to processed set
                processed_ids.add(msg_id)
                
                # Count as processed
                actual_processed += 1
                
                # Progress update
                if (i + 1) % 10 == 0:
                    print(f"  Processed {i + 1}/{batch_size} in current batch")
                
                # Write to S3 every 20 emails or at the end
                if (i + 1) % 20 == 0 or i == batch_size - 1:
                    if batch_content:
                        append_to_file(user_id, output_file, batch_content)
                        append_to_file(user_id, progress_file, new_processed_ids)
                        batch_content = ""
                        new_processed_ids = ""
                
            except Exception as e:
                print(f"Error processing message {msg_id}: {e}")
            
            # Increment counter
            total_fetched += 1
            
            # Sleep briefly to avoid hitting rate limits
            time.sleep(0.05)
        
        # Check if there are more pages
        page_token = results.get('nextPageToken')
        if not page_token:
            print("No more pages to fetch.")
            break
    
    # Stats about the extraction
    stats = {
        "total_fetched": total_fetched,
        "actual_processed": actual_processed,
        "limit_reached": limit_reached,
        "limit": limit,
        "query": query,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Write stats to S3
    stats_content = "\n".join([f"{k}: {v}" for k, v in stats.items()])
    write_file(user_id, "email_extraction_stats.txt", stats_content)
    
    print(f"\nCompleted! All emails saved to S3 for user {user_id}")
    print(f"Total emails processed: {total_fetched}")
    print(f"Emails with user content extracted: {actual_processed}")
    
    return stats

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Fetch and process Gmail emails")
    parser.add_argument("--user-id", default="default", 
                      help="User ID for S3 storage (default: default)")
    parser.add_argument("--query", default="in:sent after:2014/01/01 before:2022/01/01",
                      help="Gmail search query (default: sent emails 2014-2022)")
    parser.add_argument("--limit", type=int, default=1000,
                      help="Maximum number of emails to process (default: 1000)")
    
    args = parser.parse_args()
    
    # Fetch emails with the specified parameters
    fetch_emails(user_id=args.user_id, query=args.query, limit=args.limit)

if __name__ == "__main__":
    main()

# Add a new function that can be called from the async job
def async_fetch_emails(user_id, job_id, query="in:sent after:2014/01/01 before:2022/01/01", limit=1000, 
                       update_callback=None):
    """Fetch emails from Gmail with callback for status updates."""
    # Create the Gmail client
    client = GmailClient(user_id)
    
    print(f"Fetching emails matching query: {query}")
    print("This may take a while depending on how many emails you have.")
    
    # Prepare output file names
    output_file = "sent_emails.txt"
    progress_file = "email_fetch_progress.txt"
    
    # Initialize or read progress
    processed_ids = set()
    if file_exists(user_id, progress_file):
        progress_content = read_file(user_id, progress_file)
        processed_ids = set(line.strip() for line in progress_content.split('\n') if line.strip())
        print(f"Resuming from previous run, {len(processed_ids)} emails already processed.")
    
    # Create or clear the output file if no progress
    if not processed_ids:
        write_file(user_id, output_file, "")  # Create empty file
    
    # Initialize counters
    page_token = None
    total_fetched = 0
    limit_reached = False
    actual_processed = 0
    
    # Loop to handle pagination
    while not limit_reached:
        # Fetch a batch of emails
        try:
            results = client.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=100,
                pageToken=page_token
            ).execute()
        except Exception as e:
            print(f"Error fetching messages: {e}")
            print("Waiting 30 seconds before retrying...")
            time.sleep(30)
            continue
        
        messages = results.get('messages', [])
        if not messages:
            print("No more messages to fetch.")
            break
            
        batch_size = len(messages)
        print(f"Processing batch of {batch_size} emails...")
        
        batch_content = ""  # Accumulate content before writing to S3
        new_processed_ids = ""  # Accumulate processed IDs
        
        # Process each message
        for i, message in enumerate(messages):
            msg_id = message['id']
            
            # Skip if already processed
            if msg_id in processed_ids:
                continue
            
            # Check if we've reached the limit
            if total_fetched >= limit:
                print(f"Reached the limit of {limit} emails.")
                limit_reached = True
                break
            
            try:
                # Get full message details
                msg = client.service.users().messages().get(
                    userId='me', id=msg_id, format='full'
                ).execute()
                
                # Extract email details
                headers = msg['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                
                # Extract body
                body = ""
                if 'parts' in msg['payload']:
                    for part in msg['payload']['parts']:
                        if part['mimeType'] == 'text/plain':
                            body = decode_body(part['body'].get('data', ''))
                            break
                        elif part['mimeType'] == 'text/html' and not body:
                            body = clean_html(decode_body(part['body'].get('data', '')))
                elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                    body = decode_body(msg['payload']['body'].get('data', ''))
                
                # Extract only the content you wrote
                your_content = extract_your_content(body, date)
                
                # Format the email for storage
                email_entry = f"Email ID: {msg_id}\n"
                email_entry += f"Date: {date}\n"
                email_entry += f"To: {to}\n"
                email_entry += f"Subject: {subject}\n"
                email_entry += "Your Content:\n"
                email_entry += your_content
                email_entry += "\n" + "="*80 + "\n\n"
                
                # Add to batch content
                batch_content += email_entry
                
                # Add to processed IDs
                new_processed_ids += f"{msg_id}\n"
                
                # Add to processed set
                processed_ids.add(msg_id)
                
                # Count as processed
                actual_processed += 1
                
                # Call the update callback if provided
                if update_callback and (i + 1) % 10 == 0:
                    update_callback(total_fetched, actual_processed, limit_reached)
                
                # Write to S3 every 20 emails or at the end
                if (i + 1) % 20 == 0 or i == batch_size - 1:
                    if batch_content:
                        append_to_file(user_id, output_file, batch_content)
                        append_to_file(user_id, progress_file, new_processed_ids)
                        batch_content = ""
                        new_processed_ids = ""
                
            except Exception as e:
                print(f"Error processing message {msg_id}: {e}")
            
            # Increment counter
            total_fetched += 1
            
            # Sleep briefly to avoid hitting rate limits
            time.sleep(0.05)
        
        # Check if there are more pages
        page_token = results.get('nextPageToken')
        if not page_token:
            print("No more pages to fetch.")
            break
        
        # Call the update callback after each batch if provided
        if update_callback:
            update_callback(total_fetched, actual_processed, limit_reached)
    
    # Stats about the extraction
    stats = {
        "total_fetched": total_fetched,
        "actual_processed": actual_processed,
        "limit_reached": limit_reached,
        "limit": limit,
        "query": query,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Write stats to S3
    stats_content = "\n".join([f"{k}: {v}" for k, v in stats.items()])
    write_file(user_id, "email_extraction_stats.txt", stats_content)
    
    print(f"\nCompleted! All emails saved to S3 for user {user_id}")
    print(f"Total emails processed: {total_fetched}")
    print(f"Emails with user content extracted: {actual_processed}")
    
    return stats 