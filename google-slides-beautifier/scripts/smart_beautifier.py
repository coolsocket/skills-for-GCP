import argparse
import os
import time
import concurrent.futures
import base64
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from google import genai
from google.genai import types
from google.auth import default
from googleapiclient.errors import HttpError

from slides_manager import GoogleWorkspaceManager
from themes import Themes
from gcs_manager import GCSImageManager
from auth_manager import AuthManager

# Setup logging manually or rely on print
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SmartBeautifier:
    def __init__(self, presentation_id, project=None, location_flash="global", location_image="global", sa_key_path=None):
        self.auth_manager = AuthManager(sa_key_path)
        self.manager = GoogleWorkspaceManager(auth_manager=self.auth_manager)
        self.presentation_id = presentation_id
        self.location_flash = location_flash
        self.location_image = location_image # Gemini 3 Image is Global
        
        # Resolve SA Key from AuthManager if not provided
        self.sa_key_path = sa_key_path or self.auth_manager.sa_key_path
        self.gcs_manager = GCSImageManager(self.sa_key_path) if self.sa_key_path else None # Manager still takes path internally or env, but we should align eventually
        
        # Init Clients via AuthManager
        try:
             # Flash Client (Vertex)
             self.client_flash = self.auth_manager.get_vertex_client(location=self.location_flash)
        except Exception as e:
            logger.error(f"Failed to init Flash client: {e}")
            self.client_flash = None
            
        try:
            # Image Client (Vertex - likely same creds but explicit)
            self.client_image = self.auth_manager.get_vertex_client(location=self.location_image)
        except Exception as e:
            logger.error(f"Failed to init Image client: {e}")
            self.client_image = None

    def _extract_slide_text(self, slide):
        text_parts = []
        for element in slide.get('pageElements', []):
            if 'shape' in element and 'text' in element['shape']:
                for te in element['shape']['text'].get('textElements', []):
                    if 'textRun' in te:
                         text_parts.append(te['textRun']['content'].strip())
        return "\\n".join([t for t in text_parts if t])

    def _identify_slide_type(self, index, total_slides, slide_content):
        """Simple heuristic to map index/content to Nano Banana types."""
        # Index 1 is always cover
        if index == 1:
            return "cover"
        # Last slide or heavily data-focused?
        if index == total_slides or "Conclusion" in slide_content or "Data" in slide_content or "Statistics" in slide_content:
            return "data"
        return "default" # Content

    def analyze_presentation(self):
        """
        Step 1: Identify ALL slides for processing (except maybe first if we want, but Nano workflow says process all).
        Actually Nano workflow says process Cover, Content, Data. So we process ALL.
        """
        presentation = self.manager.get_presentation(self.presentation_id)
        slides = presentation.get('slides', [])
        return list(range(1, len(slides) + 1))

    # @retry removed to prevent infinite loops
    def process_slide(self, index, slide_obj, theme_name, total_slides):
        """
        Process a single slide:
        1. Identify Type (Cover/Content/Data)
        2. Fill Template
        3. Generate Image
        """
        logger.info(f"Processing Slide {index}...")
        blob_name = None
        
        try:
            content = self._extract_slide_text(slide_obj)
            slide_type = self._identify_slide_type(index, total_slides, content)
            
            # Step 1: Template Selection
            theme = Themes.get_theme(theme_name)
            if not theme:
                logger.error(f"Theme {theme_name} not found.")
                return

            templates = theme.get("prompt_template", {})
            # Handle both old string templates and new dict templates
            if isinstance(templates, str):
                template = templates # Fallback for backward compat if any
            else:
                template = templates.get(slide_type, templates.get("default"))
            
            # Extract Visual Prompt from Notes if available
            # We injected "[VISUAL_PROMPT]: ..." in speaker notes
            notes_page = slide_obj.get("slideProperties", {}).get("notesPage", {})
            notes_text = self._extract_slide_text(notes_page)
            visual_prompt_override = ""
            if "[VISUAL_PROMPT]:" in notes_text:
                try:
                    visual_prompt_override = notes_text.split("[VISUAL_PROMPT]:")[1].split("[NOTES]:")[0].strip()
                except:
                    pass
            
            # Combine Content + Visual Prompt
            full_context = f"Slide Content:\n{content}\n\nVisual Direction:\n{visual_prompt_override}"
            
            image_prompt = template.replace("{content}", full_context)
            logger.info(f"Slide {index} ({slide_type}) Prompt Length: {len(image_prompt)}")

            # Step 2: Image Generation
            logger.info(f"Slide {index} Generating Image...")
            
            gen_config = types.GenerateContentConfig(
                temperature=1,
                top_p=0.95,
                max_output_tokens=32768,
                response_modalities=["IMAGE"], # Request ONLY Image
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
                ],
                image_config=types.ImageConfig(
                    aspect_ratio="16:9",
                    output_mime_type="image/png",
                ),
            )
            
            start_t = time.time()
            try:
                # Use Unary call for robustness (Stream was hanging)
                response = self.client_image.models.generate_content(
                    model="gemini-3-pro-image-preview",
                    contents=[types.Content(role="user", parts=[types.Part.from_text(text=image_prompt)])],
                    config=gen_config, 
                )
                
                img_data = None
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            # SDK returns raw bytes for inline_data.data, NO DECODE NEEDED.
                            img_data = part.inline_data.data
                            logger.info(f"Slide {index} Image Data Length: {len(img_data)}")
                            break # Usually only one image part in unary response
            except Exception as e:
                 logger.error(f"Slide {index} Image Gen Failed: {e}")
                 return

            if not img_data:
                logger.error(f"Slide {index} No image returned.")
                return
                
            logger.info(f"Slide {index} Image Generated in {time.time()-start_t:.1f}s")
            
            # Save locally
            output_filename = f"slide_{index}_generated.png"
            with open(output_filename, "wb") as f:
                f.write(img_data)
            logger.info(f"Saved local image: {output_filename}")
                
            # Step 3: Upload
            image_url = None
            
            # 3a. Try GCS if available (Public Buffer)
            if self.gcs_manager:
                try:
                    folder_name = f"slides_{self.presentation_id}"
                    gcs_url, uploaded_blob_name = self.gcs_manager.upload_image(output_filename, folder=folder_name)
                    if gcs_url:
                        image_url = gcs_url
                        blob_name = uploaded_blob_name # Track for cleanup
                        logger.info(f"Uploaded to GCS: {image_url[:60]}...")
                except Exception as gcs_e:
                    logger.error(f"GCS Upload Failed: {gcs_e}")
            
            # 3b. Fallback to Drive ONLY if GCS failed/unavailable
            if not image_url:
                logger.warning(f"Slide {index} GCS unavailable, falling back to Drive...")
                try:
                    drive_file = self.manager.upload_file_to_drive(output_filename)
                    if drive_file:
                        time.sleep(5) # Propagation
                        if 'thumbnailLink' in drive_file:
                            base_thumb = drive_file['thumbnailLink']
                            image_url = base_thumb.split('=s')[0] + '=s2000' if '=s' in base_thumb else base_thumb + '=s2000'
                        else:
                            image_url = f"https://drive.google.com/thumbnail?id={drive_file['id']}&sz=w2000"
                        logger.info(f"Using Drive Link: {image_url}")
                except Exception as e:
                    logger.error(f"Slide {index} Drive Upload Failed: {e}")
                    return # Stop here if mostly failed

            if not image_url:
                logger.error(f"Slide {index} Failed to get any image URL.")
                return
            
            # Step 4: Update Slide
            requests = [
                {
                    'updatePageProperties': {
                        'objectId': slide_obj['objectId'],
                        'pageProperties': {
                            'pageBackgroundFill': {
                                'stretchedPictureFill': {
                                    'contentUrl': image_url
                                }
                            }
                        },
                        'fields': 'pageBackgroundFill'
                    }
                }
            ]
            
            # Hide text/elements
            for element in slide_obj.get('pageElements', []):
                 requests.append({
                    'deleteObject': {
                        'objectId': element['objectId']
                    }
                })
                
            try:
                self._update_slide_with_retry(requests)
                logger.info(f"Slide {index} Updated Successfully.")
            except Exception as slide_error:
                # Soft fail
                logger.error(f"Slide {index} Update Failed (likely permission). Image is saved at {output_filename}. Error: {slide_error}")
                
        except Exception as e:
            logger.error(f"Slide {index} Unexpected Error: {e}")
        
        finally:
             # Cleanup GCS blob to keep bucket clean
             if self.gcs_manager and blob_name:
                 self.gcs_manager.cleanup_blob(blob_name)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception))
    def _update_slide_with_retry(self, requests):
        self.manager.slides_service.presentations().batchUpdate(
            presentationId=self.presentation_id,
            body={'requests': requests}
        ).execute()

    def run(self, theme_name="glass", max_workers=5, limit=None):
        # 1. Enable Public Buffer (if GCS)
        if self.gcs_manager:
            self.gcs_manager.enable_public_access()
            
        try:
            # 2. Analyze
            logger.info("Analyzing presentation...")
            target_indices = self.analyze_presentation()
            logger.info(f"Target Slides: {target_indices}")
            
            if not target_indices:
                logger.warning("No slides selected.")
                return
    
            # Fetch full slide objects for processing
            presentation = self.manager.get_presentation(self.presentation_id)
            slides = presentation.get('slides', [])
            
            targets = []
            for i, slide in enumerate(slides):
                if (i+1) in target_indices:
                    targets.append((i+1, slide))
            
            if limit and limit > 0:
                logger.info(f"Limiting to first {limit} slides.")
                targets = targets[:limit]
            
            # 3. Parallel Processing
            total_slides = len(slides)
            
            # 3. Parallel Processing
            logger.info(f"Starting parallel processing with {max_workers} workers...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self.process_slide, idx, slide, theme_name, total_slides): idx 
                    for idx, slide in targets
                }
                
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        logger.error(f"Slide {idx} generated an exception: {exc}")
                        
        finally:
            # 4. Disable Public Buffer / Cleanup
            if self.gcs_manager:
                self.gcs_manager.disable_public_access()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentation-id", required=True)
    parser.add_argument("--theme", default="glass")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--create-copy", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of slides to process (0 for all)")
    parser.add_argument("--sa-key-file", help="Path to Service Account JSON key for GCS upload")
    
    args = parser.parse_args()
    
    pid = args.presentation_id
    if args.create_copy:
        # Temp auth for simple duplication
        temp_auth = AuthManager(args.sa_key_file)
        manager = GoogleWorkspaceManager(auth_manager=temp_auth)
        pid_obj = manager.duplicate_presentation(pid, f"Beautified Deck {int(time.time())}")
        pid = pid_obj['id']
        print(f"Created copy: {pid}")
    
    beautifier = SmartBeautifier(pid, sa_key_path=args.sa_key_file)
    beautifier.run(theme_name=args.theme, max_workers=args.workers, limit=args.limit)
