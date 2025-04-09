import os
import boto3
from botocore.exceptions import ClientError
import io
import pickle

# Get S3 bucket name from environment variable with a default
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'mailusers')
S3_PREFIX = os.environ.get('S3_PREFIX', 'mailsense')

# Initialize S3 client
s3_client = boto3.client('s3')

def ensure_bucket_exists():
    """Ensure the S3 bucket exists."""
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            # Bucket doesn't exist, create it
            s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
        else:
            # Other error
            raise

def get_s3_path(user_id, file_name):
    """Get the S3 path for a file."""
    return f"{S3_PREFIX}/{user_id}/{file_name}"

def file_exists(user_id, file_name):
    """Check if a file exists in S3."""
    s3_path = get_s3_path(user_id, file_name)
    try:
        s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_path)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            raise

def read_file(user_id, file_name):
    """Read a file from S3."""
    s3_path = get_s3_path(user_id, file_name)
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_path)
        return response['Body'].read().decode('utf-8')
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise FileNotFoundError(f"File not found: {s3_path}")
        else:
            raise

def write_file(user_id, file_name, content):
    """Write content to a file in S3."""
    s3_path = get_s3_path(user_id, file_name)
    s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_path, Body=content.encode('utf-8'))

def append_to_file(user_id, file_name, content):
    """Append content to a file in S3."""
    # S3 doesn't support direct append, so we need to read, modify, and write
    s3_path = get_s3_path(user_id, file_name)
    try:
        # Try to read the existing file
        existing_content = read_file(user_id, file_name)
        new_content = existing_content + content
    except FileNotFoundError:
        # File doesn't exist yet
        new_content = content
    
    # Write the new content
    write_file(user_id, file_name, new_content)

def read_pickle(user_id, file_name):
    """Read a pickle file from S3."""
    s3_path = get_s3_path(user_id, file_name)
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_path)
        data = response['Body'].read()
        return pickle.loads(data)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise FileNotFoundError(f"File not found: {s3_path}")
        else:
            raise

def write_pickle(user_id, file_name, data):
    """Write pickle data to a file in S3."""
    s3_path = get_s3_path(user_id, file_name)
    pickled_data = pickle.dumps(data)
    s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_path, Body=pickled_data)

def list_files(user_id, prefix=''):
    """List files in S3 for a user with an optional prefix."""
    s3_path = get_s3_path(user_id, prefix)
    response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=s3_path)
    
    if 'Contents' not in response:
        return []
    
    # Extract just the filenames (without the full path)
    base_prefix = f"{S3_PREFIX}/{user_id}/"
    files = [item['Key'][len(base_prefix):] for item in response['Contents'] 
             if item['Key'].startswith(base_prefix)]
    
    return files

def delete_file(user_id, file_name):
    """Delete a file from S3."""
    s3_path = get_s3_path(user_id, file_name)
    s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_path)

def get_file_size(user_id, file_name):
    """Get the size of a file in S3."""
    s3_path = get_s3_path(user_id, file_name)
    try:
        response = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_path)
        return response['ContentLength']
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            raise FileNotFoundError(f"File not found: {s3_path}")
        else:
            raise 