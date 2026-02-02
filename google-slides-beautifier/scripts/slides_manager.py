import os.path
import pickle
import time
from typing import List, Optional

from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scopes required for the application
# modifying these scopes deletes the token.json file
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/documents.readonly'
]

class GoogleWorkspaceManager:
    def __init__(self, credentials_path='credentials.json', token_path='token.json', auth_manager=None):
        if auth_manager:
            self.drive_service = auth_manager.get_drive_service()
            self.slides_service = auth_manager.get_slides_service()
            # Docs service not yet in AuthManager, but we can access creds if needed or add it
            # For now, duplicate logic or add to AuthManager
            self.creds = auth_manager.workspace_creds
            self.docs_service = build('docs', 'v1', credentials=self.creds)
        else:
            self.creds = self._authenticate(credentials_path, token_path)
            self.drive_service = build('drive', 'v3', credentials=self.creds)
            self.slides_service = build('slides', 'v1', credentials=self.creds)
            self.docs_service = build('docs', 'v1', credentials=self.creds)

    def _authenticate(self, credentials_path, token_path):
        """Authenticates using Application Default Credentials (ADC)."""
        creds, _ = default(scopes=SCOPES)
        # Explicitly set quota project to bypass ADC config issues with Drive API
        # Using 'cloud-llm-preview1' as requested by user
        creds = creds.with_quota_project('cloud-llm-preview1')
        return creds

    def get_presentation(self, presentation_id):
        """Retrieves a presentation object."""
        try:
            return self.slides_service.presentations().get(
                presentationId=presentation_id).execute()
        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def duplicate_presentation(self, presentation_id, new_title):
        """Copies a presentation to a new file."""
        try:
            body = {'name': new_title}
            return self.drive_service.files().copy(
                fileId=presentation_id, body=body).execute()
        except HttpError as error:
            print(f'An error occurred duplicating file: {error}')
            return None

    def delete_file(self, file_id):
        """Deletes a file from Google Drive."""
        try:
            self.drive_service.files().delete(fileId=file_id).execute()
            print(f"Deleted file: {file_id}")
            return True
        except HttpError as error:
            print(f'An error occurred deleting file: {error}')
            return False

    def list_files(self, mime_type: str, limit=10):
        """Lists files of a specific MIME type from Google Drive."""
        try:
            results = self.drive_service.files().list(
                q=f"mimeType='{mime_type}' and trashed=false",
                pageSize=limit,
                fields="nextPageToken, files(id, name)"
            ).execute()
            items = results.get('files', [])
            return items
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []

    def list_presentations(self, limit=10):
        return self.list_files('application/vnd.google-apps.presentation', limit)

    def list_documents(self, limit=10):
        return self.list_files('application/vnd.google-apps.document', limit)

    def search_presentations(self, query):
        """Searches for presentations containing the query in the name."""
        try:
            results = self.drive_service.files().list(
                q=f"mimeType='application/vnd.google-apps.presentation' and name contains '{query}' and trashed=false",
                fields="files(id, name)"
            ).execute()
            return results.get('files', [])
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []

    def read_slides_text(self, presentation_id):
        """Extracts text from a Google Slides presentation."""
        try:
            presentation = self.slides_service.presentations().get(
                presentationId=presentation_id).execute()
            slides = presentation.get('slides', [])
            
            text_content = []
            
            for i, slide in enumerate(slides):
                slide_text = []
                for element in slide.get('pageElements', []):
                    shape = element.get('shape')
                    if shape and shape.get('text'):
                        for text_run in shape.get('text').get('textElements', []):
                            if 'textRun' in text_run:
                                slide_text.append(text_run['textRun']['content'])
                
                if slide_text:
                    text_content.append(f"Slide {i+1}:\n" + "".join(slide_text))
            
            return "\n".join(text_content)
        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def replace_text_in_slides(self, presentation_id, old_text, new_text, match_case=True):
        """Replaces all instances of old_text with new_text in a presentation."""
        requests = [
            {
                'replaceAllText': {
                    'containsText': {
                        'text': old_text,
                        'matchCase': match_case
                    },
                    'replaceText': new_text
                }
            }
        ]

        body = {'requests': requests}
        try:
            response = self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body=body).execute()
            replies = response.get('replies', [])
            # Calculate total replacements
            count = 0
            for reply in replies:
                if 'replaceAllText' in reply:
                    count += reply['replaceAllText'].get('occurrencesChanged', 0)
            return count
        except HttpError as error:
            print(f'An error occurred: {error}')
            return -1

    def read_doc_text(self, document_id):
        """Extracts text from a Google Doc."""
        try:
            doc = self.docs_service.documents().get(documentId=document_id).execute()
            content = doc.get('body').get('content')
            return self._read_structural_elements(content)
        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def _read_structural_elements(self, elements):
        text = ''
        for value in elements:
            if 'paragraph' in value:
                for elem in value['paragraph']['elements']:
                    if 'textRun' in elem:
                        text += elem['textRun']['content']
            elif 'table' in value:
                for row in value['table']['tableRows']:
                    for cell in row['tableCells']:
                        text += self._read_structural_elements(cell['content'])
            elif 'tableOfContents' in value:
                text += self._read_structural_elements(value['tableOfContents']['content'])
    def _get_user_domain(self):
        """Fetches the authenticated user's domain."""
        try:
            about = self.drive_service.about().get(fields='user').execute()
            user = about.get('user', {})
            email = user.get('emailAddress', '')
            if '@' in email:
                return email.split('@')[1]
            return None
        except Exception as e:
            print(f"Warning: Could not fetch user info: {e}")
            return None

    def upload_file_to_drive(self, file_path, folder_id=None):
        """Uploads a file to Google Drive and returns the file ID and webContentLink."""
        from googleapiclient.http import MediaFileUpload
        
        try:
            file_name = os.path.basename(file_path)
            file_metadata = {'name': file_name}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            media = MediaFileUpload(file_path, mimetype='image/png', resumable=False)
            
            # Create file
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webContentLink, webViewLink, thumbnailLink'
            ).execute()
            
            print(f"DEBUG: Uploaded File Metadata: {file}")
            
            # Make it publicly readable so Slides API can access it?
            # Or ensure the service account has access?
            # Usually specific permission is needed for Slides API to fetch via URL unless signed URL.
            # "webContentLink" is often not directly usable by Slides API unless public.
            # Best practice: Make it "anyone with link" reader for the moment.
            
            permission = {
                'type': 'anyone',
                'role': 'reader',
            }
            try:
                self.drive_service.permissions().create(
                    fileId=file.get('id'),
                    body=permission,
                ).execute()
            except Exception as perm_error:
                print(f"Warning: Could not set public permission ({perm_error}). Trying domain...", flush=True)
                try:
                     domain_permission = {
                        'type': 'domain',
                        'role': 'reader',
                     }
                     user_domain = self._get_user_domain()
                     if user_domain:
                         domain_permission['domain'] = user_domain
                         self.drive_service.permissions().create(
                            fileId=file.get('id'),
                            body=domain_permission,
                        ).execute()
                         print(f"Set domain permission successfully for domain: {user_domain}", flush=True)
                     else:
                         print("Could not determine user domain, skipping domain permission.", flush=True)

                except Exception as domain_error:
                     print(f"Warning: Could not set domain permission either: {domain_error}", flush=True)
                     # Proceed anyway
            
            # Refetch to be sure we get the correct link (webContentLink should work now) and check for thumbnailLink
            try:
                time.sleep(2) # Brief wait for propagation
                file = self.drive_service.files().get(
                    fileId=file.get('id'),
                    fields='id, webContentLink, webViewLink, thumbnailLink'
                ).execute()
                print(f"DEBUG: Refetched Metadata: {file}")
            except Exception as e:
                print(f"Warning: Could not refetch file metadata: {e}")

            return file
            
        except Exception as error:
            with open("upload_error.log", "w") as f:
                f.write(f"Error: {error}\n")
                import traceback
                traceback.print_exc(file=f)
            print(f"Error uploading: {error}") 
            return None

import argparse

def main():
    parser = argparse.ArgumentParser(description='Google Workspace Manager')
    parser.add_argument('--list', action='store_true', help='List recent presentations and docs')
    parser.add_argument('--search', type=str, help='Search for presentations by name')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no input)')
    args = parser.parse_args()

    print("Initializing Google Workspace Manager...")
    try:
        manager = GoogleWorkspaceManager()
    except Exception as e:
        print(f"Error: {e}")
        return

    if args.search:
        print(f"\n--- Searching for '{args.search}' ---")
        results = manager.search_presentations(args.search)
        if not results:
            print("No matching presentations found.")
            return
        
        print("Found Presentations:")
        for i, ppt in enumerate(results):
            print(f"{i+1}. {ppt['name']} (ID: {ppt['id']})")
        
        # If there's exactly one result or user picks one, we could read it.
        # For now, let's just list them and let the user (me) decide what to do next 
        # via the interactive mode if I want, or just exit if headless.
        return

    print("\n--- Google Slides ---")
    presentations = manager.list_presentations(limit=5)
    if not presentations:
        print("No presentations found.")
    else:
        print("Recent Presentations:")
        for i, ppt in enumerate(presentations):
            print(f"{i+1}. {ppt['name']} (ID: {ppt['id']})")
    
    if args.list:
        return

    print("\n--- Google Docs ---")
    docs = manager.list_documents(limit=5)
    if not docs:
        print("No documents found.")
    else:
        print("Recent Documents:")
        for doc in docs:
            print(f"- {doc['name']} (ID: {doc['id']})")
            
    if args.headless:
        return

    if presentations:
        # Interactive demo
        choice = input("\nEnter number to read/modify (or 'q' to skip): ")
        if choice.isdigit() and 1 <= int(choice) <= len(presentations):
            ppt = presentations[int(choice)-1]
            print(f"\nReading content from '{ppt['name']}'...")
            content = manager.read_slides_text(ppt['id'])
            print("-" * 40)
            print(content[:500] + "..." if len(content) > 500 else content)
            print("-" * 40)
            
            modify = input("Do you want to replace text in this valid PPT? (y/n): ")
            if modify.lower() == 'y':
                old = input("Text to find: ")
                new = input("Text to replace with: ")
                count = manager.replace_text_in_slides(ppt['id'], old, new)
                print(f"Replaced {count} occurrences.")

if __name__ == '__main__':
    main()
