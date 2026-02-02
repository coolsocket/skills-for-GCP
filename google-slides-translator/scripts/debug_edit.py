from slides_manager import GoogleWorkspaceManager
import sys

def debug_edit(presentation_id):
    manager = GoogleWorkspaceManager()
    
    # Target: Slide 4, Body Text
    obj_id = "g3b50c7ed3ce_0_400" 
    # Current text length approx 145 chars (from check_deck output)
    # "Internal, AI-native development platform built by Google DeepMind\nOriginally from the Windsurf team\nStandalone application, primarily available on macOS\n"
    
    # Let's get exact current text first
    print("Fetching current text...")
    presentation = manager.get_presentation(presentation_id)
    slides = presentation.get('slides', [])
    target_element = None
    for slide in slides:
        for el in slide.get('pageElements', []):
            if el['objectId'] == obj_id:
                target_element = el
                break
        if target_element: break
    
    if not target_element:
        print("Target element not found!")
        return

    # Reconstruct text content to get length
    txt_content = ""
    if 'shape' in target_element and 'text' in target_element['shape']:
        for text_run in target_element['shape']['text'].get('textElements', []):
             if 'textRun' in text_run:
                 txt_content += text_run['textRun']['content']
    
    print(f"Current Text Length: {len(txt_content)}")
    print(f"Current Text: {repr(txt_content)}")
    
    # Attempt Safe Delete [0, len-1)
    end_index = len(txt_content) - 1
    requests = []
    
    print(f"Proposed Delete Range: 0 to {end_index} (Exclusive)")
    
    requests.append({
        'deleteText': {
            'objectId': obj_id,
            'textRange': {
                'type': 'FIXED_RANGE',
                'startIndex': 0,
                'endIndex': end_index
            }
        }
    })
    
    requests.append({
         'insertText': {
             'objectId': obj_id,
             'text': "DEBUG_TRANSLATION_TEST",
             'insertionIndex': 0
         }
    })
    
    body = {'requests': requests}
    print("Executing batch update...")
    try:
        response = manager.slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body).execute()
        print("Success!")
        print(response)
    except Exception as e:
        print(f"Failed: {e}")
        if hasattr(e, 'content'):
            print(e.content)

if __name__ == "__main__":
    cid = "1I5ECs4MJEOIPWegS2eTkDTolXaQFtXPX1Tw47cLkStM"
    if len(sys.argv) > 1:
        cid = sys.argv[1]
    debug_edit(cid)
