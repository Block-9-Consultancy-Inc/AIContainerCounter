#!/usr/bin/env python3
import argparse
import boto3
import sys

'''
python download_from_s3.py \
  --access-key YOUR_ACCESS_KEY \
  --secret-key YOUR_SECRET_KEY \
  --bucket my-bucket \
  --object-key path/to/object.txt \
  --destination /tmp/object.txt

'''

def download_file_from_s3(access_key, secret_key, bucket_name, object_key, destination_file):
    """
    Download a single file from S3 using the provided credentials.
    """
    s3 = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    try:
        s3.download_file(bucket_name, object_key, destination_file)
        print(f"Downloaded '{object_key}' from bucket '{bucket_name}' to '{destination_file}'")
    except Exception as e:
        print(f"Failed to download: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Download a file from an S3 bucket to a local path."
    )
    parser.add_argument(
        "--access-key", "-a",
        required=True,
        help="AWS Access Key ID"
    )
    parser.add_argument(
        "--secret-key", "-s",
        required=True,
        help="AWS Secret Access Key"
    )
    parser.add_argument(
        "--bucket", "-b",
        required=True,
        help="Name of the S3 bucket"
    )
    parser.add_argument(
        "--object-key", "-k",
        required=True,
        help="Key (path) of the object in the bucket"
    )
    parser.add_argument(
        "--destination", "-d",
        required=True,
        help="Local file path where the object will be saved"
    )
    args = parser.parse_args()

    download_file_from_s3(
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket_name=args.bucket,
        object_key=args.object_key,
        destination_file=args.destination
    )

if __name__ == "__main__":
    main()
