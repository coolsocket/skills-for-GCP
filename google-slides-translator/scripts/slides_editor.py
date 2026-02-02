import json
import time
from slides_manager import GoogleWorkspaceManager

class SlidesEditor:
    def __init__(self, translated_file="translated_content.json", presentation_id=None):
        self.manager = GoogleWorkspaceManager()
        self.translated_file = translated_file
        # Presentation ID can be passed or loaded from a config
        self.presentation_id = presentation_id or '13SnRUO47s8o22aRxdsGYsiUSH4Kuw5hzmkkCOinZD1I'
        self.requests = []
        self.request_metadata = [] # Track context for fallback
        self.object_length_map = {}
        if self.presentation_id:
            self._load_live_lengths()

    # ... (skipping _load_live_lengths logic which is fine) ...

    def apply_translations(self):
        data = self.load_translations()
        print(f"Applying translations to presentation: {self.presentation_id}")
        
        slide_count = 0
        element_count = 0
        
        for slide in data:
            slide_count += 1
            replacements = []
            for element in slide.get("elements", []):
                obj_id = element.get("object_id")
                # Use 'translated_text' if available, else fallback to 'translation' or 'text'
                # The Translator module sets 'translated_text'
                new_text = element.get("translated_text")
                original_text = element.get("text")
                location = element.get("location")
                
                if new_text and new_text != original_text:
                    # Collect replacement for slide-level batching. Keep obj_id!
                    replacements.append((obj_id, original_text, new_text))
                    
                    # Fix Font: Enforce Roboto
                    font_req = {
                        'updateTextStyle': {
                            'objectId': obj_id,
                            'style': {
                                'weightedFontFamily': {
                                    'fontFamily': 'Roboto'
                                }
                            },
                            'textRange': {
                                'type': 'ALL'
                            },
                            'fields': 'weightedFontFamily'
                        }
                    }
                    if location:
                        font_req['updateTextStyle']['cellLocation'] = {
                            'rowIndex': location['row'],
                            'columnIndex': location['col']
                        }
                    
                    self.requests.append(font_req)
                    self.request_metadata.append({'type': 'font', 'obj_id': obj_id})
                    
                    element_count += 1
            
            # Generate smart line-by-line replacements
            self._generate_slide_requests(slide.get("slide_id"), replacements)
            
            if len(self.requests) > 20:
                self._execute_batch()
                
        if self.requests:
            self._execute_batch()
            
        print(f"Finished. Updated {element_count} elements across {slide_count} slides.")

    def _generate_slide_requests(self, slide_id, replacements):
        line_replacements = []
        
        for obj_id, orig, new in replacements:
            orig_lines = orig.split('\n')
            new_lines = new.split('\n')
            
            if len(orig_lines) == len(new_lines):
                for o, n in zip(orig_lines, new_lines):
                    if o.strip(): 
                        line_replacements.append((obj_id, o, n))
            else:
                o_valid = [l for l in orig_lines if l.strip()]
                n_valid = [l for l in new_lines if l.strip()]
                
                if len(o_valid) == len(n_valid):
                    for o, n in zip(o_valid, n_valid):
                       line_replacements.append((obj_id, o, n))
                else:
                    line_replacements.append((obj_id, orig, new))

        # Sort by Length Descending (Longest first)
        line_replacements.sort(key=lambda x: len(x[1]), reverse=True)
        
        for obj_id, orig, new in line_replacements:
            self._create_replacement_request(orig, new, slide_id, obj_id)

    def _create_replacement_request(self, original_text, new_text, slide_id=None, obj_id=None):
        if not original_text or not new_text: return
        
        search_text = original_text.strip()
        replace_text = new_text.strip()
        if not search_text: return
        
        req = {
            'replaceAllText': {
                'containsText': {
                    'text': search_text,
                    'matchCase': True
                },
                'replaceText': replace_text
            }
        }
        if slide_id:
            req['replaceAllText']['pageObjectIds'] = [slide_id]
        
        self.requests.append(req)
        self.request_metadata.append({
            'type': 'replace', 
            'obj_id': obj_id, 
            'orig': search_text, 
            'new': replace_text
        })

    def _execute_batch(self):
        if not self.requests: return
        
        # 1. Attempt Batch Execution with limited retry
        batch_success = False
        retries = 0
        backoff = 1.0
        
        while retries < 3:
            try:
                body = {'requests': self.requests}
                self.manager.slides_service.presentations().batchUpdate(
                    presentationId=self.presentation_id, body=body).execute()
                print(f"  Executed batch of {len(self.requests)//2} updates...")
                batch_success = True
                break
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "rate limit" in err_str:
                    retries += 1
                    print(f"  Batch Rate Limit (Retry {retries}). Sleeping {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    # Non-retriable batch error (e.g. invalid request in batch)
                    print(f"  Batch failed with non-retriable error: {e}")
                    break
        
        if batch_success:
            self.requests = []
            self.request_metadata = []
            time.sleep(1.0) # Throttle between successful batches
            return

        # 2. Fallback to Individual Execution (Infinite Retry for 429)
        print("  Retrying requests individually to isolate failure...")
        
        for i, req in enumerate(self.requests):
            retry_count = 0
            single_backoff = 1.2
            
            while True:
                try:
                    body = {'requests': [req]}
                    self.manager.slides_service.presentations().batchUpdate(
                        presentationId=self.presentation_id, body=body).execute()
                    time.sleep(single_backoff) # Throttle
                    break # Success
                except Exception as inner_e:
                    err_str = str(inner_e).lower()
                    if "429" in err_str or "quota" in err_str or "rate limit" in err_str:
                        retry_count += 1
                        if retry_count == 3:
                            print(f"    Warning: Item {i} hit Rate Limit 3 times. Retrying indefinitely...")
                        
                        print(f"    Item Rate Limit (Retry {retry_count}). Sleeping {single_backoff}s...")
                        time.sleep(single_backoff)
                        single_backoff = min(single_backoff * 1.5, 30) # Cap wait
                    else:
                        print(f"    Failed single request: {inner_e}")
                        
                        # FALLBACK LOGIC (Spacer/Nesting)
                        meta = self.request_metadata[i] if i < len(self.request_metadata) else {}
                        
                        if "spacer" in err_str and meta.get('obj_id'):
                            obj_id = meta['obj_id']
                            orig_len = len(meta.get('orig', ''))
                            obj_actual_len = self.object_length_map.get(obj_id, 999999)
                            
                            if abs(obj_actual_len - orig_len) < 5 or orig_len > (obj_actual_len * 0.8):
                                print(f"    -> Attempting Destructive Fallback for {obj_id} (Wipe & Replace)")
                                try:
                                    fallback_reqs = [
                                        {'deleteText': {'objectId': obj_id, 'textRange': {'type': 'ALL'}}},
                                        {'insertText': {'objectId': obj_id, 'text': meta['new']}}
                                    ]
                                    self.manager.slides_service.presentations().batchUpdate(
                                        presentationId=self.presentation_id, body={'requests': fallback_reqs}).execute()
                                    print("    -> Fallback Success!")
                                except Exception as fb_e:
                                    print(f"    -> Fallback Failed: {fb_e}")
                        break # Move to next item

        self.requests = []
        self.request_metadata = []

    def _load_live_lengths(self):
        print("Fetching live presentation to sync text lengths...")
        try:
            presentation = self.manager.get_presentation(self.presentation_id)
            slides = presentation.get('slides', [])
            for slide in slides:
                for el in slide.get('pageElements', []):
                    # Shapes
                    if 'shape' in el and 'text' in el['shape']:
                        oid = el['objectId']
                        txt = ""
                        for tr in el['shape']['text'].get('textElements', []):
                             if 'textRun' in tr:
                                 txt += tr['textRun']['content']
                        self.object_length_map[oid] = len(txt)
                    # Tables
                    if 'table' in el:
                        oid = el['objectId']
                        rows = el['table'].get('tableRows', [])
                        cell_map = {}
                        for r, row in enumerate(rows):
                            for c, cell in enumerate(row.get('tableCells', [])):
                                txt = ""
                                if 'text' in cell:
                                    for tr in cell['text'].get('textElements', []):
                                         if 'textRun' in tr:
                                             txt += tr['textRun']['content']
                                cell_map[(r,c)] = len(txt)
                        self.object_length_map[oid] = cell_map
                        
        except Exception as e:
            print(f"Warning: Failed to fetch live lengths: {e}")

    def load_translations(self):
        with open(self.translated_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def apply_translations(self):
        data = self.load_translations()
        print(f"Applying translations to presentation: {self.presentation_id}")
        
        slide_count = 0
        element_count = 0
        
        for slide in data:
            slide_count += 1
            replacements = []
            for element in slide.get("elements", []):
                obj_id = element.get("object_id")
                # Use 'translated_text' if available, else fallback to 'translation' or 'text'
                # The Translator module sets 'translated_text'
                new_text = element.get("translated_text")
                original_text = element.get("text")
                location = element.get("location")
                
                if new_text and new_text != original_text:
                    # Collect replacement for slide-level batching
                    replacements.append((original_text, new_text))
                    
                    # Fix Font: Enforce Roboto (or standard Sans) to avoid fallback serif issues
                    # We apply this to the ENTIRE Element.
                    font_req = {
                        'updateTextStyle': {
                            'objectId': obj_id,
                            'style': {
                                'weightedFontFamily': {
                                    'fontFamily': 'Roboto'
                                }
                            },
                            'textRange': {
                                'type': 'ALL'
                            },
                            'fields': 'weightedFontFamily'
                        }
                    }
                    if location:
                        font_req['updateTextStyle']['cellLocation'] = {
                            'rowIndex': location['row'],
                            'columnIndex': location['col']
                        }
                    self.requests.append(font_req)
                    
                    element_count += 1
            
            # Generate smart line-by-line replacements for the accumulated text
            self._generate_slide_requests(slide.get("slide_id"), replacements)
            
            # Execute batch per slide (or every N items) to keep requests manageable
            if len(self.requests) > 20:
                self._execute_batch()
                
        # Final flush
        if self.requests:
            self._execute_batch()
            
        print(f"Finished. Updated {element_count} elements across {slide_count} slides.")

    def _generate_slide_requests(self, slide_id, replacements):
        # 1. Decompose into Line-by-Line replacements
        # This preserves paragraph formatting (bullets, indentation) if we match line-by-line.
        line_replacements = []
        
        for orig, new in replacements:
            orig_lines = orig.split('\n')
            new_lines = new.split('\n')
            
            # Smart Matching: 
            # If line counts match, pair them 1:1.
            if len(orig_lines) == len(new_lines):
                for o, n in zip(orig_lines, new_lines):
                    if o.strip(): # Only replace non-empty lines
                        line_replacements.append((o, n))
            else:
                # Count mismatch. fallback to block replacement but warn?
                # Block replacement DESTROYS structure if multiple paragraphs are in one block.
                # Attempt to align by filtering empty?
                o_valid = [l for l in orig_lines if l.strip()]
                n_valid = [l for l in new_lines if l.strip()]
                
                if len(o_valid) == len(n_valid):
                    for o, n in zip(o_valid, n_valid):
                       line_replacements.append((o, n))
                else:
                    # True mismatch. Fallback to whole block (risk alignment loss, but translation applies).
                    # print(f"Warning: Line count mismatch for slide {slide_id}. Fallback to block.")
                    line_replacements.append((orig, new))

        # 2. Sort by Length Descending (Longest first)
        # To avoid partial substring replacements (e.g. replacing 'Rules' inside 'Global Rules').
        line_replacements.sort(key=lambda x: len(x[0]), reverse=True)
        
        # 3. Generate Requests
        for orig, new in line_replacements:
            self._create_replacement_request(orig, new, slide_id)

    def _create_replacement_request(self, original_text, new_text, slide_id=None):
        if not original_text or not new_text: return
        
        search_text = original_text.strip()
        replace_text = new_text.strip()
        if not search_text: return
        
        req = {
            'replaceAllText': {
                'containsText': {
                    'text': search_text,
                    'matchCase': True
                },
                'replaceText': replace_text
            }
        }
        if slide_id:
            req['replaceAllText']['pageObjectIds'] = [slide_id]
        self.requests.append(req)

    def _execute_batch(self):
        if not self.requests: return
        try:
            body = {'requests': self.requests}
            self.manager.slides_service.presentations().batchUpdate(
                presentationId=self.presentation_id, body=body).execute()
            print(f"  Executed batch of {len(self.requests)//2} updates...")
            self.requests = []
            time.sleep(1.0) # Throttle batches slightly
        except Exception as e:
            print(f"  Error executing batch: {e}")
            if hasattr(e, 'content'):
                print(f"  Error content: {e.content}")
            
            print("  Retrying requests individually to isolate failure...")
            # Throttle retry loop significantly to avoid 429 (Write Quota: 60/min)
            for req in self.requests:
                try:
                    body = {'requests': [req]}
                    self.manager.slides_service.presentations().batchUpdate(
                        presentationId=self.presentation_id, body=body).execute()
                    time.sleep(1.2) # Max 50 requests/min
                except Exception as inner_e:
                    print(f"    Failed single request: {inner_e}")
            
            self.requests = []

if __name__ == "__main__":
    editor = SlidesEditor()
    editor.apply_translations()
