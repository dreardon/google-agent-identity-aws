import boto3
import os
import logging
import json
from token_agent.identity import fetch_gcp_identity_token
from google.genai.types import Part
import mimetypes
from google.adk.tools.tool_context import ToolContext


logger = logging.getLogger(__name__)

def _get_s3_client() -> boto3.client:
       # 1. Fetch GCP agent identity token
        # Use the configured audience, which matches the AWS OIDC provider config (defaults to AUDIENCE env var)
        audience = os.environ.get("AUDIENCE", "api://geappaudience")
        logger.info(f"Fetching GCP Agent Identity token with audience: {audience}")
        gcp_token = fetch_gcp_identity_token(audience=audience)
        
        # 2. Assume Role with Web Identity in AWS STS
        role_arn = os.environ.get("AWS_ROLE_ARN", "arn:aws:iam::679695450108:role/gcp_aws_agent_identity_role")
        logger.info(f"Assuming AWS IAM Role: {role_arn}")
        sts_client = boto3.client('sts')
        sts_response = sts_client.assume_role_with_web_identity(
            RoleArn=role_arn,
            RoleSessionName='AWSGCPWorkloadSession',
            WebIdentityToken=gcp_token
        )
        
        # 3. Retrieve temporary AWS credentials
        credentials = sts_response['Credentials']
        logger.info("Successfully acquired temporary AWS credentials.")
        
        # 4. Use credentials to initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
        
        return s3_client

def list_aws_bucket_data() -> str:
    """Retrieves list of files from the AWS S3 bucket by exchanging the Google Agent Identity OIDC token for AWS credentials.
    
    This tool should be used when the user requests data from AWS or wants to list files in the S3 bucket.
    """
    try:
        # 1. Get S3 client with agent identity credentials
        s3_client = _get_s3_client()
        
        # 2. List objects in the S3 bucket
        bucket_name = os.environ.get("AWS_BUCKET", "gcp-aws-bucket-data")
        logger.info(f"Listing objects in AWS S3 bucket: {bucket_name}")
        s3_response = s3_client.list_objects_v2(Bucket=bucket_name)
        
        # 3. Format the response
        if 'Contents' in s3_response:
            files = [obj['Key'] for obj in s3_response['Contents']]
            result = f"Successfully accessed S3 bucket '{bucket_name}' using Agent Identity. Files found:\n" + "\n".join(files)
        else:
            result = f"Successfully accessed S3 bucket '{bucket_name}' using Agent Identity, but the bucket is empty."
            
        return result

    except Exception as e:
        logger.error(f"Error accessing AWS S3 bucket using Agent Identity: {e}")
        return f"Failed to access AWS S3: {str(e)}"

async def get_aws_bucket_file(filename: str, tool_context: ToolContext) -> str:
    """Retrieves an file from the AWS S3 bucket using Agent Identity.
    
    This tool MUST be called whenever the user asks to view, describe, inspect, or analyze an file stored in S3.
    """
    try:
        # 1. Get S3 client with agent identity credentials
        s3_client = _get_s3_client()
        
        # 2. Get file from S3 bucket
        bucket_name = os.environ.get("AWS_BUCKET", "gcp-aws-bucket-data")
        logger.info(f"Retrieving file: {filename} from AWS S3 bucket: {bucket_name}")
        s3_response = s3_client.get_object(Bucket=bucket_name, Key=filename)
        s3_response_binary_data = s3_response['Body'].read()

        mime_type = s3_response.get('ContentType')
        
        if not mime_type or mime_type == 'application/octet-stream':
            guessed_mime_type, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime_type or 'application/pdf'


        artifact_id = f"s3_{filename}"
        file_part = Part(inline_data={"mime_type": mime_type, "data": s3_response_binary_data})

        await tool_context.save_artifact(filename=artifact_id, artifact=file_part)

        return {"status": "success", "artifact_id": artifact_id}
    
    except Exception as e:
        logger.error(f"Error processing or saving AWS S3 file using Agent Identity: {e}")
        return f"Failed to process or save AWS S3 file: {str(e)}"