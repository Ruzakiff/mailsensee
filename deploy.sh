#!/bin/bash

# Bundle the application for Elastic Beanstalk
ZIP_FILE="mailsense-deployment.zip"

# Remove any old zip file
rm -f $ZIP_FILE

# Create a new zip file with explicitly selected files
zip $ZIP_FILE .dockerignore .ebignore .gitignore app.py Dockerfile findvoice.py generate.py gmail_history.py requirements.txt

# Add .ebextensions folder
zip -r $ZIP_FILE .ebextensions/

# Add only the mailsense package without unwanted files
zip -r $ZIP_FILE mailsense/ -x "*.pyc" "*__pycache__*" "*.DS_Store"

# Ensure user data and other sensitive directories are not included
echo "Deployment bundle created: $ZIP_FILE"
echo "Upload this file to Elastic Beanstalk"