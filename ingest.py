import os
import glob
from setuptools import setup, find_packages

def get_credentials_path():
    """Return the path to the OAuth credentials file."""
    # First check for environment variable
    env_path = os.environ.get('MAILSENSE_OAUTH_CREDENTIALS')
    if env_path and os.path.exists(env_path):
        return env_path
        
    # Look for client_secret*.json files
    client_secret_files = glob.glob("client_secret*.json")
    if client_secret_files:
        return client_secret_files[0]  # Use the first one found
        
    # Fall back to default location
    default_path = "oauth.json"
    return default_path

def validate_credentials_file():
    """Ensure the OAuth credentials file exists."""
    credentials_file = get_credentials_path()
    if not os.path.exists(credentials_file):
        raise FileNotFoundError(
            f"OAuth credentials file '{credentials_file}' not found. "
            f"Please place your credentials file at this location or set the "
            f"MAILSENSE_OAUTH_CREDENTIALS environment variable."
        )
    return credentials_file

def get_install_requires():
    """Return the list of required packages."""
    return [
        "google-auth",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "google-api-python-client",
        "flask",
        "requests",
    ]

def get_entry_points():
    """Return the entry points for the package."""
    return {
        'console_scripts': [
            'mailsense=mailsense.auth:main',
        ],
    }

def get_classifiers():
    """Return the list of classifiers."""
    return [
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Programming Language :: Python :: 3",
    ]

def run_setup():
    """Run the setup process."""
    credentials_file = validate_credentials_file()
    
    setup(
        name="mailsense",
        version="1.0.0",
        packages=find_packages(),
        install_requires=get_install_requires(),
        entry_points=get_entry_points(),
        author="Mailsense Team",
        author_email="info@mailsense.com",
        description="Mailsense Chrome Extension with Google OAuth",
        long_description="A Chrome extension that provides OAuth login with Google",
        keywords="email, chrome extension, oauth",
        classifiers=get_classifiers(),
        python_requires=">=3.6",
        include_package_data=True,
        package_data={
            "": [credentials_file],
        },
    )

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 1:
        # When run with no arguments, perform installation
        sys.argv.append("install")
        
    run_setup()


