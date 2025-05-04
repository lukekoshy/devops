import boto3
import os
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class S3Manager:
    def __init__(self):
        # Validate AWS credentials
        self._validate_credentials()
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION')
            )
            # Test the connection
            self.s3_client.list_buckets()
            logger.info("Successfully connected to AWS S3")
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise
        except PartialCredentialsError:
            logger.error("Incomplete AWS credentials")
            raise
        except ClientError as e:
            logger.error(f"AWS authentication error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error initializing S3 client: {str(e)}")
            raise

        self.word_bucket = os.getenv('WORD_DOCUMENTS_BUCKET')
        self.pdf_bucket = os.getenv('PDF_FILES_BUCKET')
        
        if not self.word_bucket or not self.pdf_bucket:
            raise ValueError("S3 bucket names not configured in .env file")
            
        self._ensure_buckets_exist()

    def _validate_credentials(self):
        """Validate AWS credentials are present and properly formatted"""
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        region = os.getenv('AWS_REGION')

        if not all([access_key, secret_key, region]):
            missing = []
            if not access_key: missing.append('AWS_ACCESS_KEY_ID')
            if not secret_key: missing.append('AWS_SECRET_ACCESS_KEY')
            if not region: missing.append('AWS_REGION')
            raise ValueError(f"Missing required AWS credentials: {', '.join(missing)}")

        if not access_key.startswith('AKIA'):
            raise ValueError("Invalid AWS access key format")

    def _ensure_buckets_exist(self):
        """Ensure required S3 buckets exist, create if they don't"""
        for bucket_name in [self.word_bucket, self.pdf_bucket]:
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                logger.info(f"Bucket {bucket_name} exists")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code in ['404', '403']:
                    logger.info(f"Bucket {bucket_name} exists but is not owned by you or not accessible")
                    continue
                else:
                    logger.error(f"Error checking bucket {bucket_name}: {str(e)}")
                    raise

    def upload_file(self, file_path, file_name, is_pdf=False):
        """
        Upload a file to S3
        Args:
            file_path (str): Local path to the file
            file_name (str): Name to give the file in S3
            is_pdf (bool): Whether the file is a PDF (determines which bucket to use)
        Returns:
            str: URL of the uploaded file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Local file not found: {file_path}")

        bucket = self.pdf_bucket if is_pdf else self.word_bucket
        try:
            self.s3_client.upload_file(file_path, bucket, file_name)
            url = f"https://{bucket}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{file_name}"
            logger.info(f"Successfully uploaded {file_name} to {bucket}")
            return self.get_presigned_url(file_name, is_pdf)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                logger.error(f"Bucket {bucket} does not exist")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to bucket {bucket}. Check your AWS permissions.")
            else:
                logger.error(f"Error uploading {file_name} to {bucket}: {str(e)}")
            raise

    def download_file(self, filename):
        """
        Download a file from S3
        Args:
            filename (str): Name of the file in S3
        Returns:
            str: Local path where the file was downloaded, or None if not found
        """
        # Try PDF bucket first
        local_path = os.path.join('converted', filename)
        try:
            self.s3_client.download_file(self.pdf_bucket, filename, local_path)
            logger.info(f"Successfully downloaded {filename} from {self.pdf_bucket}")
            return local_path
        except ClientError as e:
            # If not in PDF bucket, try Word bucket
            try:
                local_path = os.path.join('uploads', filename)
                self.s3_client.download_file(self.word_bucket, filename, local_path)
                logger.info(f"Successfully downloaded {filename} from {self.word_bucket}")
                return local_path
            except ClientError:
                logger.error(f"File {filename} not found in either bucket")
                return None

    def delete_file(self, file_name, is_pdf=False):
        """
        Delete a file from S3
        Args:
            file_name (str): Name of the file to delete
            is_pdf (bool): Whether the file is a PDF (determines which bucket to use)
        """
        bucket = self.pdf_bucket if is_pdf else self.word_bucket
        try:
            self.s3_client.delete_object(Bucket=bucket, Key=file_name)
            logger.info(f"Successfully deleted {file_name} from {bucket}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"File {file_name} not found in bucket {bucket}")
            elif error_code == 'NoSuchBucket':
                logger.error(f"Bucket {bucket} does not exist")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to delete file {file_name} from bucket {bucket}")
            else:
                logger.error(f"Error deleting {file_name} from {bucket}: {str(e)}")
            raise

    def get_file_url(self, file_name, is_pdf=False):
        """
        Get the URL of a file in S3
        Args:
            file_name (str): Name of the file
            is_pdf (bool): Whether the file is a PDF (determines which bucket to use)
        Returns:
            str: URL of the file
        """
        bucket = self.pdf_bucket if is_pdf else self.word_bucket
        return f"https://{bucket}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{file_name}"

    def get_presigned_url(self, filename, is_pdf=False, expiration=3600):
        """
        Generate a presigned URL for secure file download
        Args:
            filename (str): Name of the file in S3
            is_pdf (bool): Whether the file is in the PDF bucket
            expiration (int): URL expiration time in seconds (default 1 hour)
        Returns:
            str: Presigned URL for the file
        """
        try:
            bucket = self.pdf_bucket if is_pdf else self.word_bucket
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket,
                    'Key': filename
                },
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return None 