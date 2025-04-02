from mailsense.gmail import GmailClient

def main():
    # Create the Gmail client
    client = GmailClient()
    
    # Get the 10 most recent sent emails
    print("Fetching your 10 most recent sent emails...")
    emails = client.get_emails(label="SENT", max_results=10)
    
    # Display email details
    print(f"\nFound {len(emails)} emails\n")
    
    for i, email in enumerate(emails):
        print(f"Email {i+1}:")
        print(f"  Subject: {email['subject']}")
        print(f"  To: {email['to']}")
        print(f"  Date: {email['date']}")
        print("  " + "-"*40)

if __name__ == "__main__":
    main() 