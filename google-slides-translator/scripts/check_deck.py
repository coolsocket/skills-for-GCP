from slides_manager import GoogleWorkspaceManager
import json
import sys

def check_deck(presentation_id):
    manager = GoogleWorkspaceManager()
    print(f"Reading deck: {presentation_id}")
    
    try:
        presentation = manager.get_presentation(presentation_id)
        if not presentation:
            print("Failed to get presentation")
            return

        slides = presentation.get('slides', [])
        
        print(f"Total Slides: {len(slides)}")
        
        for i, slide in enumerate(slides):
            if i < 7 or i == 16: # Check 1-7 (index 0-6) and 17 (index 16)
                print(f"\n--- Slide {i+1} ({slide['objectId']}) ---")
                for element in slide.get('pageElements', []):
                    shape = element.get('shape')
                    if shape and shape.get('text'):
                        txt_content = ""
                        styles = []
                        for text_run in shape.get('text').get('textElements', []):
                            if 'textRun' in text_run:
                                content = text_run['textRun']['content']
                                txt_content += content
                                style = text_run['textRun']['style']
                                styles.append(f"[{content.strip()}]: Bold={style.get('bold')}, Italic={style.get('italic')}, Font={style.get('weightedFontFamily', {}).get('fontFamily')}")
                        
                        print(f"ID: {element['objectId']}")
                        print(f"Text: {txt_content.strip()}")
                        print(f"Repr: {repr(txt_content.strip())}")
                        # Check Paragraph Style specifically for indentation
                        if 'paragraphStyle' in text_run:
                            print(f"ParaStyle: {text_run['paragraphStyle']}")
                        print(f"Styles: {styles}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    cid = "1Ul2FmfggbCXchWSnFrCohHLWxYDGC4zkP5p0ljbklNc" 
    if len(sys.argv) > 1:
        cid = sys.argv[1]
    check_deck(cid)
