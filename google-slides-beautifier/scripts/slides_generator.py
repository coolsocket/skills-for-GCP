import argparse
import json
import logging
import os
from typing import List, Dict, Any

from auth_manager import AuthManager
from googleapiclient.discovery import build

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SlidesGenerator:
    def __init__(self, auth_manager=None):
        self.auth = auth_manager or AuthManager()
        # Use Workspace Identity for Slides (via AuthManager's handled property or direct creds)
        self.creds = self.auth.workspace_creds 
        self.service = build('slides', 'v1', credentials=self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)

    def create_presentation(self, title: str) -> str:
        """Creates a new presentation and returns its ID."""
        body = {'title': title}
        presentation = self.service.presentations().create(body=body).execute()
        pid = presentation.get('presentationId')
        logger.info(f"📄 Created Presentation: {title} (ID: {pid})")
        return pid

    def build_deck(self, structure_file: str) -> str:
        """Reads JSON structure and builds the deck."""
        with open(structure_file, 'r') as f:
            data = json.load(f)
        
        title = data.get("title", "Untitled Generator Deck")
        slides_data = data.get("slides", [])
        
        # 1. Create Deck
        deck_id = self.create_presentation(title)
        
        # 2. Create Slides (Batch 1)
        create_requests = []
        for i, slide in enumerate(slides_data):
            page_id = f"slide_{i}_generated" 
            layout_id = self._map_layout(slide.get("type", "CONTENT"))
            
            create_requests.append({
                'createSlide': {
                    'objectId': page_id,
                    'insertionIndex': i + 1, 
                    'slideLayoutReference': {'predefinedLayout': layout_id}
                }
            })
            
        if create_requests:
            self.service.presentations().batchUpdate(
                presentationId=deck_id, body={'requests': create_requests}
            ).execute()
        
        # 3. Delete Default Slide 1 (The initial empty Title slide)
        # Fetch deck to get the objectId of the first slide
        temp_deck = self.service.presentations().get(
            presentationId=deck_id, fields="slides(objectId)"
        ).execute()
        if temp_deck.get('slides'):
            default_slide_id = temp_deck['slides'][0]['objectId']
            # We only delete it if we created NEW slides (to avoid empty deck errors if something failed)
            if len(temp_deck['slides']) > 1:
                self.service.presentations().batchUpdate(
                    presentationId=deck_id,
                    body={'requests': [{'deleteObject': {'objectId': default_slide_id}}]}
                ).execute()
                logger.info("🗑️ Deleted initial blank slide.")
        
        # 3. Fetch Deck to find Placeholders (Robustness Refactor)
        deck = self.service.presentations().get(
            presentationId=deck_id,
            fields="slides(objectId,pageElements(objectId,shape(placeholder(type))))"
        ).execute()
        
        # Map our generated slides to their placeholders
        # We deleted slide 0, so ours are now at index 0 to N-1
        deck_slides = deck.get('slides', [])
        
        insert_requests = []
        
        for i, slide_data in enumerate(slides_data):
            # deck_slides[0] is our first generated slide now
            deck_index = i
            if deck_index >= len(deck_slides):
                logger.warning(f"Slide {i} missing in deck?")
                continue
                
            slide_obj = deck_slides[deck_index]
            elements = slide_obj.get('pageElements', [])
            
            # Find Title and Body IDs
            title_id = None
            body_id = None
            
            for el in elements:
                ph = el.get('shape', {}).get('placeholder', {})
                ph_type = ph.get('type')
                
                if ph_type == 'TITLE' or ph_type == 'CENTERED_TITLE':
                    title_id = el['objectId']
                elif ph_type == 'BODY' or ph_type == 'SUBTITLE':
                    # If we have multiple, this might grab the first. Usually fine.
                    # For SECTION_HEADER, subtitle is the body.
                    if not body_id: # Grab first body/subtitle
                        body_id = el['objectId']
            
            # Fill Title
            if title_id and slide_data.get("title"):
                insert_requests.append({
                    'insertText': {
                        'objectId': title_id,
                        'text': slide_data.get("title")
                    }
                })
                
            # Fill Body with Hierarchy Support
            if body_id and slide_data.get("body"):
                body_lines = []
                for line in slide_data.get("body"):
                    # Basic sub-bullet detection (starting with spaces or specific symbols)
                    if line.strip().startswith("-") or line.strip().startswith("•") or line.startswith("  "):
                        # If it doesn't already have indentation, but is a sub-bullet, add it?
                        # Actually, ContentAgent already provides "  - Sub-point"
                        body_lines.append(line)
                    else:
                        # Top level point
                        body_lines.append(f"• {line}")
                
                body_text = "\n".join(body_lines)
                insert_requests.append({
                    'insertText': {
                        'objectId': body_id,
                        'text': body_text
                    }
                })


        # 4. Execute Content Insertion (Batch 2)
        if insert_requests:
            logger.info(f"📝 Inserting text into {len(insert_requests)} fields...")
            self.service.presentations().batchUpdate(
                presentationId=deck_id, body={'requests': insert_requests}
            ).execute()
            
        # 5. Inject Visual Prompts (Speaker Notes)
        self._inject_visual_prompts(deck_id, slides_data, None)

        return deck_id

    def _map_layout(self, slide_type: str) -> str:
        """Maps narrative types to Google Slides Layouts."""
        # SIMPLIFIED ROBUST MAPPING
        # TITLE -> TITLE layout (has TITLE + SUBTITLE)
        # SECTION -> SECTION_HEADER layout (has TITLE + SUBTITLE)
        # ALL OTHERS -> TITLE_AND_BODY (has TITLE + BODY)
        
        st = slide_type.upper()
        if st == "TITLE":
            return "TITLE"
        elif st == "SECTION":
            return "SECTION_HEADER"
        else:
            return "TITLE_AND_BODY"
            
            
            # Placeholder Logic in build_deck handled this:
            # TITLE/SECTION_HEADER -> Body maps to SUBTITLE
            # OTHERS -> Body maps to BODY

    def _inject_visual_prompts(self, deck_id: str, slides_data: List[Dict], batch_response: Any):
        """Fetches the deck to find Notes Pages, then inserts Visual Prompts."""
        logger.info("🎨 Injecting Visual Prompts into Speaker Notes...")
        
        # 1. Fetch Deck (fields: slides.objectId, slides.slideProperties.notesPage.objectId)
        deck = self.service.presentations().get(
            presentationId=deck_id,
            fields="slides(objectId,slideProperties(notesPage(objectId)))"
        ).execute()
        
        slides = deck.get("slides", [])
        # Mapping: We deleted slide 0, so ours ARE the slides
        generated_slides = slides 
        
        if len(generated_slides) != len(slides_data):
            logger.warning(f"Slide count mismatch! Deck has {len(generated_slides)} new slides, Data has {len(slides_data)}.")
        
        notes_requests = []
        for i, slide_obj in enumerate(generated_slides):
            if i >= len(slides_data): break
            
            data = slides_data[i]
            notes_page_id = slide_obj.get("slideProperties", {}).get("notesPage", {}).get("objectId")
            
            if not notes_page_id:
                continue
                
            # Notes page usually has a BODY placeholder (index 0 or shape type)
            # We can use 'createShape' on the notes page? No, standard notes page has a text box.
            # Let's try inserting text into the notes page's BODY placeholder.
            # We don't know the placeholder ID.
            # Easier: Just CREATE a new shape on the notes page? No, might overlap.
            # Better: Get the notes page details to find the placeholder? Too many calls.
            # Hack: Most notes pages have a specific structure.
            # Reliable Way: `batchUpdate` with `insertText` requires an ObjectID.
            # We need to fetch the Notes Page contents to find the text box.
            pass 
        
        # Optimization: Fetch Notes Page contents in one GET call?
        # We can't fetch multiple specific pages easily.
        # Let's just create a new text box on the notes page for the prompt?
        # Or better: Put the Visual Prompt in a hidden shape on the slide itself?
        # The Beautifier looks for "Speaker Notes".
        # Let's fix `_inject_visual_prompts` to be robust. 
        # Actually, for V1, let's just use `insertText` on the *Shape* found in the notes page.
        # We need to query the notes page elements.
        
        # RE-FETCHING with deeper fields
        deck_deep = self.service.presentations().get(
            presentationId=deck_id,
            fields="slides(slideProperties(notesPage(pageElements(objectId,shape(placeholder(type))))))"
        ).execute()
        
        slides_deep = deck_deep.get("slides", []) 
        
        for i, slide_deep in enumerate(slides_deep):
            if i >= len(slides_data): break
            data = slides_data[i]
            prompt = data.get("visual_prompt", "")
            notes = data.get("speaker_notes", "")
            
            full_notes = f"[VISUAL_PROMPT]: {prompt}\n\n[NOTES]: {notes}"
            
            # Find the BODY placeholder on the notes page
            notes_page = slide_deep.get("slideProperties", {}).get("notesPage", {})
            elements = notes_page.get("pageElements", [])
            
            target_id = None
            for el in elements:
                # Look for BODY type placeholder
                if el.get("shape", {}).get("placeholder", {}).get("type") == "BODY":
                    target_id = el["objectId"]
                    break
            
            if target_id:
                notes_requests.append({
                    'insertText': {
                        'objectId': target_id,
                        'text': full_notes
                    }
                })

        if notes_requests:
            self.service.presentations().batchUpdate(
                presentationId=deck_id, body={'requests': notes_requests}
            ).execute()
            logger.info(f"📝 Added notes/prompts to {len(notes_requests)} slides.")

def main():
    parser = argparse.ArgumentParser(description="Slides Generator: JSON -> Deck")
    parser.add_argument("structure_file", help="Path to presentation_structure.json")
    args = parser.parse_args()
    
    gen = SlidesGenerator()
    deck_id = gen.build_deck(args.structure_file)
    print(f"DONE: {deck_id}")

if __name__ == "__main__":
    main()
