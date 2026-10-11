#!/usr/bin/env python3
"""Apply CORS rules to the Backblaze B2 buckets (audio + covers).

    pip install -r scripts/requirements.txt
    python scripts/setup_b2_cors.py

Reads S3_* and CORS_ORIGINS straight from the repo's .env (via python-dotenv) - the same
credentials, bucket names and allowed origins the services themselves use, never hardcoded here.
Re-runnable: put_bucket_cors replaces the bucket's CORS config each time, so running this twice
is harmless.
"""
import os
import sys
from pathlib import Path

import boto3
from botocore.client import Config
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

REQUIRED = ["S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET_AUDIO", "S3_BUCKET_COVERS"]


def main() -> None:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing from .env: {', '.join(missing)}. Copy .env.example to .env and fill in your B2 details first.")

    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if not origins:
        sys.exit("CORS_ORIGINS is empty in .env - set it to your real frontend origin(s) first.")

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ["S3_REGION"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "auto"}, retries={"max_attempts": 3}),
    )

    cors_config = {
        "CORSRules": [{
            "AllowedOrigins": origins,
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["Range", "Authorization", "Content-Type"],
            "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "Cache-Control"],
            "MaxAgeSeconds": 3600,
        }],
    }

    for bucket in (os.environ["S3_BUCKET_AUDIO"], os.environ["S3_BUCKET_COVERS"]):
        s3.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_config)
        print(f"CORS applied to '{bucket}': origins={origins}")


if __name__ == "__main__":
    main()
