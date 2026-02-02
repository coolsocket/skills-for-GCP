import os
import logging
from google.auth import default
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai

logger = logging.getLogger(__name__)

class AuthManager:
    """
    Handles Dual-Track Authentication:
    1. Workspace Identity (Docs/Slides): Always uses local User Credentials (ADC).
    2. Cloud Identity (Vertex/GCS): Uses Service Account Key if provided/env set, otherwise falls back to User Creds.
    """
    def __init__(self, sa_key_path=None):
        # Priority: 1. Argument -> 2. Env Var -> 3. Standard Global Path
        self.sa_key_path = sa_key_path or os.getenv("GCP_SA_KEY")
        if not self.sa_key_path:
             # Check for standard global path from GEMINI.md rule
             std_path = os.path.expanduser("~/.gemini/credentials/cloud-resource-key.json")
             if os.path.exists(std_path):
                 self.sa_key_path = std_path
        
        # 1. Primary Identity: Workspace (Slides, Drive)
        # Always use the local user's login (gcloud auth login)
        self.workspace_creds, self.workspace_project = default(scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/cloud-platform'])
        # Explicitly set quota project to bypass ADC config issues with Drive/Slides API
        if hasattr(self.workspace_creds, 'with_quota_project'):
            self.workspace_creds = self.workspace_creds.with_quota_project('cloud-llm-preview1')
        logger.info(f"Authenticated as User (Workspace): {self.workspace_project} (Quota: cloud-llm-preview1)")

        # 2. Resource Identity: Cloud Resources (Vertex AI, GCS)
        if self.sa_key_path and os.path.exists(self.sa_key_path):
            logger.info(f"⚡️ Dual-Track Mode: Using Service Account for Cloud Resources: {self.sa_key_path}")
            self.gcp_creds = service_account.Credentials.from_service_account_file(
                self.sa_key_path, 
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            # Try to extract project ID from key file if possible, else default
            try:
                import json
                with open(self.sa_key_path) as f:
                    key_data = json.load(f)
                    self.gcp_project = key_data.get('project_id')
            except:
                self.gcp_project = self.workspace_project
        else:
            logger.info("👤 Single-Track Mode: Using User Credentials for Cloud Resources")
            self.gcp_creds = self.workspace_creds
            self.gcp_project = self.workspace_project

    def get_slides_service(self):
        return build('slides', 'v1', credentials=self.workspace_creds)

    def get_drive_service(self):
        return build('drive', 'v3', credentials=self.workspace_creds)

    def get_vertex_client(self, location="global"):
        # Explicitly pass project to ensure we use the SA's project quota
        return genai.Client(vertexai=True, credentials=self.gcp_creds, project=self.gcp_project, location=location)
    
    def get_gcs_client(self):
        from google.cloud import storage
        return storage.Client(credentials=self.gcp_creds, project=self.gcp_project)

    def get_run_client(self):
        """Returns a Cloud Run ServicesClient authenticated with the Resource credentials."""
        try:
            from google.cloud import run_v2
            # Explicitly use the project from credentials for the client
            # The client will use these credentials for API calls
            return run_v2.ServicesClient(credentials=self.gcp_creds)
        except ImportError:
            logger.error("google-cloud-run not installed. Please run: pip install google-cloud-run")
            return None
