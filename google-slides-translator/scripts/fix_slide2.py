from slides_manager import GoogleWorkspaceManager

def fix_slide_2():
    manager = GoogleWorkspaceManager()
    presentation_id = '1Ul2FmfggbCXchWSnFrCohHLWxYDGC4zkP5p0ljbklNc'
    
    print(f"Fixing Slide 2 on deck: {presentation_id}")
    
    # Target Object ID for "What is JetSki?" on Slide 2
    # From check_deck.py: ID: g3b50c7ed3ce_0_351
    target_id = 'g3b50c7ed3ce_0_351'
    target_text = "What is JetSki?"
    translated_text = "什么是 JetSki？"
    
    requests = [
        {
            'deleteText': {
                'objectId': target_id,
                'textRange': {'type': 'ALL'}
            }
        },
        {
            'insertText': {
                'objectId': target_id,
                'text': translated_text
            }
        },
        {
            'updateTextStyle': {
                'objectId': target_id,
                'style': {
                    'weightedFontFamily': {
                        'fontFamily': 'Roboto'
                    }
                },
                'textRange': {'type': 'ALL'},
                'fields': 'weightedFontFamily'
            }
        }
    ]
    
    try:
        manager.slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body={'requests': requests}).execute()
        print("Success! Fixed Slide 2.")
    except Exception as e:
        print(f"Failed to fix Slide 2: {e}")

if __name__ == "__main__":
    fix_slide_2()
