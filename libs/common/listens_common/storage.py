"""Thin S3 wrapper (boto3). Targets Backblaze B2's S3-compatible API in production; the test
suite points the same client at an in-process moto server instead (see listens_common.testing)."""
from functools import lru_cache

import boto3
from botocore.client import Config

from .config import Settings, get_settings


@lru_cache
def get_s3():
    s: Settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": s.s3_addressing_style}, retries={"max_attempts": 3}),
    )


def delete_prefix(client, bucket: str, prefix: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objs})
