# app/routers/get_file_url.py
from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
import boto3
from botocore.exceptions import ClientError
from datetime import timedelta
import os

router = APIRouter(prefix="/getFileUrl", tags=["File URLs"])

AWS_REGION = os.getenv("AWS_REGION")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)


@router.post("/")
async def get_presigned_url(request: Request):
    body = await request.json()
    key = body.get("key")

    if not key:
        raise HTTPException(status_code=400, detail="File key is required")

    if not BUCKET_NAME or not AWS_REGION:
        raise HTTPException(status_code=500, detail="Missing S3 configuration")

    try:
        url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=300   # 5 minutes
        )

        return {"url": url}

    except ClientError as e:
        return JSONResponse(
            status_code=500,
            content={
                "message": "Could not generate file URL.",
                "error": str(e)
            }
        )
