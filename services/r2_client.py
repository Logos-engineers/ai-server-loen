import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{os.getenv('CLOUDFLARE_ACCOUNT_ID')}.r2.cloudflarestorage.com",
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
)

BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

 
def download_file(key: str) -> bytes:
    response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    return response["Body"].read()


def upload_file(key: str, data: bytes, content_type: str = "application/pdf") -> str:
    s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=data, ContentType=content_type)
    return key


def delete_file(key: str):
    s3.delete_object(Bucket=BUCKET_NAME, Key=key)
