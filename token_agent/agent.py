import os
import json
import jwt
import logging
from pydantic import BaseModel

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse

from token_agent.identity import fetch_gcp_identity_token
from token_agent.tools.aws import list_aws_bucket_data, get_aws_bucket_file

logger = logging.getLogger(__name__)


async def before_model_modifier(
    callback_context: CallbackContext, 
    llm_request: LlmRequest
) -> LlmResponse | None:
    logger.info("Running before_model_modifier callback...")
    for content in llm_request.contents:
        if not content.parts:
            continue
            
        modified_parts = []
        for part in content.parts:
            modified_parts.append(part)
 
            if part.function_response and part.function_response.name == "get_aws_bucket_file":
                logger.info(f"Intercepted FunctionResponse for get_aws_bucket_file: {part.function_response}")
                MyToolResponse = part.function_response.response

                if MyToolResponse and "artifact_id" in MyToolResponse:
                    MyArtifactId = MyToolResponse["artifact_id"]
                    logger.info(f"Loading artifact for file: {MyArtifactId}")

                    MyFilePart = await callback_context.load_artifact(filename=MyArtifactId)

                    if MyFilePart:
                        logger.info(f"Successfully loaded file artifact {MyArtifactId}, appending Part to LLM request.")
                        modified_parts.append(MyFilePart)
                    else:
                        logger.warning(f"Could not load artifact {MyArtifactId}")
                        
        content.parts = modified_parts

def fetch_agent_identity_token_details() -> str:
    """Fetches the agent's identity token from the metadata server and returns its decoded JSON payload.
    
    This tool should be used whenever the user requests the agent's identity token or credentials.
    """
    raw_token = fetch_gcp_identity_token()

    logger.info(f"Encoded ID Token JWT: {raw_token}")
    print(f"Encoded ID Token JWT: {raw_token}")

    payload = jwt.decode(raw_token, options={"verify_signature": False})
    return json.dumps(payload, indent=2)

root_agent = Agent(
    name="token_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are an ADK agent with full multimodal vision and document analysis capabilities. "
        "You can retrieve, analyze, and describe any file type stored in AWS S3 (primarily Images and PDFs).\n\n"
        "Follow these rules for tool usage:\n"
        "1. Token / Identity Queries: When the user asks specifically for your token or identity credentials, "
        "call `fetch_agent_identity_token_details` and return the JSON payload verbatim to the user.\n\n"
        "2. AWS Resource & File Requests: For all other requests (such as listing files, retrieving, viewing, analyzing, or summarizing data from AWS S3):\n"
        "   - Call `fetch_agent_identity_token_details` to retrieve the agent identity token.\n"
        "   - Then call `list_aws_bucket_data` to list files in the bucket and/or `get_aws_bucket_file` to fetch the specific file(s).\n\n"
        "3. Multimodal Analysis: You HAVE FULL MULTIMODAL CAPABILITIES for analyzing images, PDFs, and documents. "
        "When requested to inspect, describe, analyze, or summarize any file from S3, ALWAYS invoke `get_aws_bucket_file(filename=...)`. "
        "Once the file artifact is retrieved, analyze its content thoroughly and answer the user's questions. Never state that you lack file or image analysis capabilities."
    ),
    tools=[
        FunctionTool(fetch_agent_identity_token_details),
        FunctionTool(list_aws_bucket_data),
        FunctionTool(get_aws_bucket_file),
    ],
    before_model_callback=before_model_modifier
)

app = App(
    name="token_agent",
    root_agent=root_agent,
)