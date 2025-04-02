from mailsense.gmail import GmailClient
import base64
import time
import re
import email
import html
import os

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
    
    # Common patterns for quoted content
    quoted_patterns = [
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
        r'--',                       # Signature markers
    ]
    
    # Combine patterns
    combined_pattern = '|'.join(f'({p})' for p in quoted_patterns)
    
    in_quote = False
    for line in lines:
        # Check if this line starts a quote
        if re.match(combined_pattern, line.strip()):
            in_quote = True
            continue
        
        # If we're not in a quote, add the line
        if not in_quote:
            # Skip empty lines at the start
            if not your_content and not line.strip():
                continue
            your_content.append(line)
    
    # If we couldn't detect quotes, just return everything
    if not your_content and lines:
        return body
    
    return '\n'.join(your_content)

def main():
    # Create the Gmail client
    client = GmailClient()
    
    # Set the query to get sent emails from 2014 to 2022
    query = "in:sent after:2014/01/01 before:2022/01/01"
    
    print("Fetching sent emails from 2014-2022...")
    print("This may take a while depending on how many emails you have.")
    
    # Prepare output file
    output_file = "my_sent_emails_2014_2022.txt"
    
    # Check if we have a progress file
    progress_file = "email_fetch_progress.txt"
    processed_ids = set()
    
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            processed_ids = set(line.strip() for line in f if line.strip())
        print(f"Resuming from previous run, {len(processed_ids)} emails already processed.")
    
    # Open the output file in append mode
    with open(output_file, 'a', encoding='utf-8') as out_file:
        # Loop to handle pagination
        page_token = None
        total_fetched = 0
        
        while True:
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
                break
                
            batch_size = len(messages)
            print(f"Processing batch of {batch_size} emails...")
            
            # Process each message
            for i, message in enumerate(messages):
                msg_id = message['id']
                
                # Skip if already processed
                if msg_id in processed_ids:
                    continue
                
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
                    
                    # Write to file immediately
                    out_file.write(f"Email ID: {msg_id}\n")
                    out_file.write(f"Date: {date}\n")
                    out_file.write(f"To: {to}\n")
                    out_file.write(f"Subject: {subject}\n")
                    out_file.write("Your Content:\n")
                    out_file.write(your_content)
                    out_file.write("\n" + "="*80 + "\n\n")
                    
                    # Flush to ensure it's written to disk
                    out_file.flush()
                    
                    # Mark as processed
                    with open(progress_file, 'a') as prog:
                        prog.write(f"{msg_id}\n")
                    
                    processed_ids.add(msg_id)
                    
                    # Progress update
                    if (i + 1) % 10 == 0:
                        print(f"  Processed {i + 1}/{batch_size} in current batch")
                    
                except Exception as e:
                    print(f"Error processing message {msg_id}: {e}")
                
                # Sleep briefly to avoid hitting rate limits
                time.sleep(0.05)
            
            # Update total count
            total_fetched += batch_size - len([m for m in messages if m['id'] in processed_ids])
            print(f"Total emails processed so far: {total_fetched}")
            
            # Check if there are more pages
            page_token = results.get('nextPageToken')
            if not page_token:
                break
    
    print(f"\nCompleted! All emails saved to {output_file}")
    print(f"Total emails processed: {total_fetched}")

if __name__ == "__main__":
    main() 