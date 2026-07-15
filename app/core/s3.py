import boto3
import uuid
import logging
from typing import Optional
from fastapi import UploadFile
from app.core.config import settings

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self):
        self.enabled = all([
            settings.AWS_ACCESS_KEY_ID,
            settings.AWS_SECRET_ACCESS_KEY,
            settings.AWS_S3_BUCKET
        ])
        if not self.enabled:
            logger.warning("AWS S3 credentials not fully configured. Uploads will be skipped or mock URLs returned.")
            self.s3_client = None
            self.bucket_name = None
        else:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            self.bucket_name = settings.AWS_S3_BUCKET

    async def upload_file(self, file: UploadFile, folder: str = "vehicles") -> str:
        """
        Uploads a file to AWS S3 bucket and returns its public URL.
        If S3 is not configured, returns a mock URL.
        """
        if not self.enabled:
            logger.warning("AWS S3 is not configured. Simulating file upload.")
            # return a mock URL for local development/testing
            return f"https://mock-s3-bucket.s3.amazonaws.com/{folder}/{uuid.uuid4().hex}_{file.filename}"

        # Generate a unique key for S3
        file_extension = file.filename.split(".")[-1] if "." in file.filename else ""
        unique_key = f"{folder}/{uuid.uuid4().hex}"
        if file_extension:
            unique_key = f"{unique_key}.{file_extension}"

        try:
            # Read contents
            content = await file.read()
            # Seek back to 0 just in case something else reads it later
            await file.seek(0)
            
            # Put object in bucket
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=unique_key,
                Body=content,
                ContentType=file.content_type
            )
            
            # Form S3 URL
            # Note: s3.{region}.amazonaws.com works for standard S3 buckets.
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{unique_key}"
            logger.info(f"Successfully uploaded file to S3: {url}")
            return url
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            raise Exception(f"Failed to upload file to S3: {str(e)}")

    async def delete_file_by_url(self, file_url: str):
        """
        Deletes a file from S3 bucket using its public URL.
        """
        if not self.enabled or not file_url:
            return

        prefix = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/"
        if file_url.startswith(prefix):
            key = file_url[len(prefix):]
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
                logger.info(f"Successfully deleted file from S3: {key}")
            except Exception as e:
                logger.error(f"Failed to delete S3 file {key}: {str(e)}")
