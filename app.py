import os
from flask import Flask, request, render_template, send_file, jsonify, redirect, make_response
from werkzeug.utils import secure_filename
from word_to_pdf import convert_word_to_pdf
from s3_manager import S3Manager
import logging
from datetime import datetime
from dotenv import load_dotenv
from waitress import serve
import ssl
import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, ProcessCollector, start_http_server
import boto3
import yaml

# Load environment variables
load_dotenv()

# Load version information
with open('version.txt', 'r') as f:
    version_info = yaml.safe_load(f)

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Prometheus metrics
CONVERSION_REQUEST_COUNT = Counter('pdf_conversion_requests_total', 'Total number of PDF conversion requests')
CONVERSION_SUCCESS_COUNT = Counter('pdf_conversion_success_total', 'Total number of successful PDF conversions')
CONVERSION_FAILURE_COUNT = Counter('pdf_conversion_failure_total', 'Total number of failed PDF conversions')
CONVERSION_DURATION = Histogram('pdf_conversion_duration_seconds', 'Time spent processing PDF conversion')
FILE_SIZE = Histogram('uploaded_file_size_bytes', 'Size of uploaded files', buckets=[1024*1024, 2*1024*1024, 5*1024*1024, 10*1024*1024])
S3_UPLOAD_SUCCESS = Counter('s3_upload_success_total', 'Successful S3 uploads')
S3_UPLOAD_FAILURE = Counter('s3_upload_failure_total', 'Failed S3 uploads')

# Initialize process collector
ProcessCollector()

app = Flask(__name__)

# Enable CORS
from flask_cors import CORS
CORS(app)

# Security headers
@app.after_request
def add_security_headers(response):
    if os.getenv('FLASK_DEBUG') == '1':
        # Less restrictive headers for development
        response.headers['Content-Security-Policy'] = "default-src 'self' http: https:; style-src 'self' 'unsafe-inline' http: https:; script-src 'self' 'unsafe-inline'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
    else:
        # Strict headers for production
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'self' https:; style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# Initialize S3 manager
s3_manager = S3Manager()

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
CONVERTED_FOLDER = 'converted'
ALLOWED_EXTENSIONS = {'docx'}

# Ensure upload and converted directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize AWS clients
s3 = boto3.client('s3')
bucket_name = 'word-to-pdf-converters'
pdf_bucket_name = 'word-to-pdf-converters'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html', version=version_info)

@app.route('/version')
def version():
    return jsonify(version_info)

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/convert', methods=['POST'])
def convert():
    CONVERSION_REQUEST_COUNT.inc()
    start_time = time.time()
    
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            logger.error("No file part in the request")
            CONVERSION_FAILURE_COUNT.inc()
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        
        # Check if a file was selected
        if file.filename == '':
            logger.error("No file selected")
            CONVERSION_FAILURE_COUNT.inc()
            return jsonify({"error": "No file selected"}), 400
            
        # Check if file is a Word document
        if not allowed_file(file.filename):
            logger.error(f"Invalid file type: {file.filename}")
            CONVERSION_FAILURE_COUNT.inc()
            return jsonify({"error": "Only .docx files are allowed"}), 400

        # Save the uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Record file size
        file_size = os.path.getsize(file_path)
        FILE_SIZE.observe(file_size)
        
        # Upload Word document to S3
        try:
            s3_manager.upload_file(file_path, filename, is_pdf=False)
            logger.info(f"Word document uploaded to S3: {filename}")
            S3_UPLOAD_SUCCESS.inc()
        except Exception as e:
            logger.error(f"Failed to upload Word document to S3: {str(e)}")
            S3_UPLOAD_FAILURE.inc()
        
        try:
            # Convert to PDF
            pdf_filename = os.path.splitext(filename)[0] + '.pdf'
            pdf_path = os.path.join(CONVERTED_FOLDER, pdf_filename)
            
            convert_word_to_pdf(file_path, pdf_path)
            
            # Try to upload PDF to S3
            try:
                s3_manager.upload_file(pdf_path, pdf_filename, is_pdf=True)
                download_url = s3_manager.get_presigned_url(pdf_filename, is_pdf=True)
                logger.info(f"PDF uploaded to S3 and presigned URL generated")
                S3_UPLOAD_SUCCESS.inc()
            except Exception as e:
                logger.error(f"Failed to upload PDF to S3: {str(e)}")
                S3_UPLOAD_FAILURE.inc()
                download_url = f"/download/{pdf_filename}"
            
            # Clean up the original Word file
            os.remove(file_path)
            
            CONVERSION_SUCCESS_COUNT.inc()
            CONVERSION_DURATION.observe(time.time() - start_time)
            
            return jsonify({
                "message": "Conversion successful",
                "download_url": download_url
            })
                
        except Exception as e:
            logger.error(f"PDF conversion failed: {str(e)}")
            CONVERSION_FAILURE_COUNT.inc()
            # Clean up files in case of error
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            return jsonify({"error": "Conversion failed"}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        CONVERSION_FAILURE_COUNT.inc()
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        CONVERSION_DURATION.observe(time.time() - start_time)

@app.route('/download/<filename>')
def download_file(filename):
    try:
        # First check if file exists locally
        pdf_path = os.path.join(CONVERTED_FOLDER, filename)
        if os.path.exists(pdf_path):
            return send_file(pdf_path, as_attachment=True)
        
        # If not found locally, try to get from S3
        try:
            download_url = s3_manager.get_presigned_url(filename, is_pdf=True)
            if download_url:
                return redirect(download_url)
        except Exception as e:
            logger.error(f"Failed to get S3 presigned URL: {str(e)}")
        
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({"error": "Download failed"}), 404

@app.errorhandler(413)
def request_entity_too_large(error):
    CONVERSION_FAILURE_COUNT.inc()
    return jsonify({"error": "File too large"}), 413

from prometheus_client import ProcessCollector

def register_process_collector():
    ProcessCollector()

if __name__ == '__main__':
    # Register Prometheus process collector only in main process
    register_process_collector()
    # Start Prometheus metrics server
    start_http_server(8000)
    app.run(debug=True, host='0.0.0.0', port=5000)
