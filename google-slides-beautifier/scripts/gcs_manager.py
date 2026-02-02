import os
import datetime
from google.cloud import storage
from google.oauth2 import service_account
import logging

logger = logging.getLogger(__name__)

class GCSImageManager:
    def __init__(self, sa_key_path, project_id=None):
        self.sa_key_path = sa_key_path
        self.creds = service_account.Credentials.from_service_account_file(sa_key_path)
        self.project_id = project_id or self.creds.project_id
        self.client = storage.Client(credentials=self.creds, project=self.project_id)
        self.bucket_name = f"jetski-secure-buffer-{self.project_id}"
        self.bucket = self._get_or_create_bucket()
        
    def _get_or_create_bucket(self):
        try:
            bucket = self.client.get_bucket(self.bucket_name)
        except Exception:
            try:
                logger.info(f"Creating bucket {self.bucket_name}...")
                bucket = self.client.create_bucket(self.bucket_name, location="US")
            except Exception as e:
                logger.error(f"Failed to create bucket: {e}")
                raise e
        
        # Try to disable Uniform Bucket Level Access to allow ACLs
        try:
            iam_config = bucket.iam_configuration
            if iam_config.uniform_bucket_level_access_enabled:
                logger.info("Disabling Uniform Bucket Level Access to allow ACLs...")
                iam_config.uniform_bucket_level_access_enabled = False
                bucket.patch()
        except Exception as e:
            logger.warning(f"Could not disable UBLA (ACLs might fail): {e}")
            
        return bucket

    def upload_image(self, file_path, folder="slides_assets"):
        """
        Uploads an image to GCS and returns the Public URL.
        Note: The bucket must be publicly accessible (via enable_public_access).
        """
        try:
            file_name = os.path.basename(file_path)
            blob_name = f"{folder}/{int(datetime.datetime.now().timestamp())}_{file_name}"
            blob = self.bucket.blob(blob_name)
            
            logger.info(f"Uploading to GCS: {blob_name}")
            blob.upload_from_filename(file_path, content_type="image/png")
            
            return blob.public_url, blob_name
            
        except Exception as e:
            logger.error(f"GCS Upload Failed: {e}")
            return None, None

    def enable_public_access(self):
        """Grants allUsers objectViewer access to the bucket via IAM."""
        try:
            logger.info(f"Enabling Public Access on bucket {self.bucket_name}...")
            policy = self.bucket.get_iam_policy(requested_policy_version=3)
            # Check if already exists
            for binding in policy.bindings:
                if binding['role'] == 'roles/storage.objectViewer' and 'allUsers' in binding['members']:
                    logger.info("Bucket is already public.")
                    return

            policy.bindings.append({
                "role": "roles/storage.objectViewer",
                "members": {"allUsers"}
            })
            self.bucket.set_iam_policy(policy)
            logger.info("Bucket is now Public.")
        except Exception as e:
            logger.error(f"Failed to enable public access: {e}")

    def disable_public_access(self):
        """Revokes allUsers objectViewer access."""
        try:
            logger.info(f"Disabling Public Access on bucket {self.bucket_name}...")
            policy = self.bucket.get_iam_policy(requested_policy_version=3)
            new_bindings = []
            modified = False
            for binding in policy.bindings:
                if binding['role'] == 'roles/storage.objectViewer' and 'allUsers' in binding['members']:
                    binding['members'].discard('allUsers')
                    modified = True
                    if binding['members']:
                        new_bindings.append(binding)
                else:
                    new_bindings.append(binding)
            
            if modified:
                policy.bindings = new_bindings
                self.bucket.set_iam_policy(policy)
                logger.info("Bucket is now Private (Public Access Revoked).")
        except Exception as e:
            logger.error(f"Failed to disable public access: {e}")

    def cleanup_blob(self, blob_name):
        """Deletes the blob to maintain privacy/cleanliness."""
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()
            logger.info(f"Deleted GCS blob: {blob_name}")
        except Exception as e:
            logger.warning(f"Failed to clean up blob {blob_name}: {e}")
