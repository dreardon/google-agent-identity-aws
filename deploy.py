import os
import vertexai
from vertexai import agent_engines, types
import warnings
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning, message=r".*\[EXPERIMENTAL\].*")

# Load environment variables from .env file
load_dotenv()

# 1. Initialize Vertex AI
client = vertexai.Client(
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
    http_options=dict(api_version="v1beta1")
)

# 2. Instantiate your agent locally
from token_agent import app
adk_app = agent_engines.AdkApp(app=app)

config_params = {
    "identity_type": types.IdentityType.AGENT_IDENTITY,
    "staging_bucket": os.environ["STAGING_BUCKET"],
    "requirements": ["google-cloud-aiplatform[agent_engines,adk]==1.151.0", "google-adk[agent-identity]==1.32.0", "boto3==1.43.51"],
    "display_name": "Identity Token Agent: Certificates",
    "python_version": "3.13",
    "agent_framework": "google-adk",
    "env_vars": {
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "False",
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
        "ADK_TRIGGER_MAX_RETRIES": "5",
        "ADK_TRIGGER_RETRY_BASE_DELAY": "2.0",
        "ADK_TRIGGER_RETRY_MAX_DELAY": "30.0",
        "AUDIENCE": os.environ["AUDIENCE"],
        "AWS_ROLE_ARN": os.environ["AWS_ROLE_ARN"],
        "AWS_BUCKET": os.environ["AWS_BUCKET"]
    },
    "extra_packages": ["token_agent"]
}

# 3. Get the Most Recent Instance Deployment for AGENT_RUNTIME_DISPLAY_NAME, If Available
print("Checking for Existing Agent Runtime Deployment...")
agents_iterator = client.agent_engines.list(
    config={
        "filter": f'display_name="{config_params['display_name']}"',
    }    
)

all_matches = list(agents_iterator)
if all_matches:
    target_agent = max(all_matches, key=lambda x: x.api_resource.create_time)
else:
    target_agent = None

# 4. Create or Update the Agent Runtime
try:
    if target_agent:
        AGENT_RUNTIME_NAME = target_agent.api_resource.name
        print(f"Found Existing Agent Runtime Deployment ({AGENT_RUNTIME_NAME}). Updating ...")
        remote_app = client.agent_engines.update(
            name=AGENT_RUNTIME_NAME,
            agent=adk_app,
            config=config_params    
        )
        print(f"Agent Runtime Instance Updated Successfully!")
    else:
        print("Agent Runtime Not Found. Creating Agent Runtime Instance...")
        remote_app = client.agent_engines.create(
            agent=adk_app,
            config=config_params     
        )
        print(f"Agent Runtime Instance Created Successfully!")
    print(f"Resource Name: {remote_app.api_resource.name}")
    print(f"Agent Identity: principal://{remote_app.api_resource.spec.effective_identity}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Failed to deploy agent: {str(e)}")
