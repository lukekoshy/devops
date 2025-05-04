#!/bin/bash

# Exit on error
set -e

# Configuration
EC2_USER="ubuntu"
EC2_HOST="$EC2_PUBLIC_IP"
APP_DIR="/home/ubuntu/word-to-pdf-converter"
ENV_FILE=".env"

# Create deployment package
echo "Creating deployment package..."
zip -r deploy.zip . -x "*.git*" "*.env*" "*.pytest_cache*" "tests/*"

# Copy files to EC2
echo "Copying files to EC2..."
scp -i ~/.ssh/deploy_key -o StrictHostKeyChecking=no deploy.zip $EC2_USER@$EC2_HOST:~

# Deploy on EC2
echo "Deploying on EC2..."
ssh -i ~/.ssh/deploy_key -o StrictHostKeyChecking=no $EC2_USER@$EC2_HOST << 'ENDSSH'
    # Create app directory if it doesn't exist
    mkdir -p $APP_DIR
    
    # Move to app directory
    cd $APP_DIR
    
    # Stop existing application if running
    if pgrep -f "python app.py" > /dev/null; then
        pkill -f "python app.py"
    fi
    
    # Extract new deployment
    unzip -o ~/deploy.zip -d .
    
    # Install/update dependencies
    pip install -r requirements.txt
    
    # Set up environment variables
    echo "Setting up environment variables..."
    cat > $ENV_FILE << EOL
# Application Configuration
MAX_CONTENT_LENGTH=16777216
ALLOWED_EXTENSIONS=docx
FLASK_DEBUG=0

# AWS Configuration
AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
AWS_REGION=$AWS_REGION
AWS_DEFAULT_REGION=$AWS_REGION

# S3 Configuration
WORD_DOCUMENTS_BUCKET=$WORD_DOCUMENTS_BUCKET
PDF_FILES_BUCKET=$PDF_FILES_BUCKET

# EC2 Configuration
EC2_KEY_PAIR_NAME=$EC2_KEY_PAIR_NAME
EC2_INSTANCE_TYPE=$EC2_INSTANCE_TYPE
EC2_AMI_ID=$EC2_AMI_ID
EC2_SECURITY_GROUP=$EC2_SECURITY_GROUP
EOL
    
    # Start the application
    echo "Starting application..."
    nohup python app.py > app.log 2>&1 &
    
    # Clean up
    rm ~/deploy.zip
    
    echo "Deployment complete!"
ENDSSH

# Clean up local deployment package
rm deploy.zip

echo "Deployment completed successfully!" 