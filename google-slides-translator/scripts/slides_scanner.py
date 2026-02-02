import json
from slides_manager import GoogleWorkspaceManager

class SlidesScanner:
    def __init__(self, presentation_id):
        self.manager = GoogleWorkspaceManager()
        self.presentation_id = presentation_id
        self.content_map = []

    def __init__(self, presentation_id, include_skipped=False):
        self.manager = GoogleWorkspaceManager()
        self.presentation_id = presentation_id
        self.include_skipped = include_skipped
        self.content_map = []

    def scan(self):
        print(f"Scanning presentation: {self.presentation_id}")
        presentation = self.manager.get_presentation(self.presentation_id)
        slides = presentation.get('slides', [])
        
        for i, slide in enumerate(slides):
            slide_id = slide.get('objectId')
            is_skipped = slide.get('slideProperties', {}).get('isSkipped', False)
            
            if is_skipped and not self.include_skipped:
                print(f"  Skipping hidden Slide {i+1} ({slide_id})...")
                continue
                
            print(f"  Scanning Slide {i+1} ({slide_id})...")
            
            slide_data = {
                "slide_index": i,
                "slide_id": slide_id,
                "elements": []
            }
            
            self._scan_elements(slide.get('pageElements', []), slide_data["elements"])
            
            if slide_data["elements"]:
                self.content_map.append(slide_data)
                
        return self.content_map

    def _scan_elements(self, elements, output_list):
        for element in elements:
            self._process_element_recursive(element, output_list)

    def _process_element_recursive(self, element, output_list):
        object_id = element.get('objectId')
        
        # 1. Groups
        if 'elementGroup' in element:
            children = element.get('elementGroup', {}).get('children', [])
            for child in children:
                self._process_element_recursive(child, output_list)
        
        # 2. Tables
        elif 'table' in element:
            rows = element.get('table', {}).get('tableRows', [])
            for r_idx, row in enumerate(rows):
                cells = row.get('tableCells', [])
                for c_idx, cell in enumerate(cells):
                    if 'text' in cell:
                        # Table cells don't have direct objectIDs easily actionable via API without cell location
                        # But we can store the table ObjectID + rowIndex + colIndex
                        self._extract_text(cell['text'], output_list, parent_id=object_id, location={'row': r_idx, 'col': c_idx})

        # 3. Shapes
        elif 'shape' in element:
            if 'text' in element['shape']:
                self._extract_text(element['shape']['text'], output_list, parent_id=object_id)

    def _extract_text(self, text_obj, output_list, parent_id, location=None):
        if not text_obj: return
        
        text_content = ""
        style_info = {"font_size": 0, "is_bold": False}
        
        text_elements = text_obj.get('textElements', [])
        for te in text_elements:
            if 'textRun' in te:
                content = te['textRun'].get('content', '')
                text_content += content
                
                # Capture style of the first meaningful run for context (simplification)
                # In robust version, we might track style changes
                style = te['textRun'].get('style', {})
                if content.strip() and style_info["font_size"] == 0:
                    # Google Slides font size is in 'magnitude' usually? checking API docs
                    # actually 'fontSize' object: {magnitude, unit}
                    fs = style.get('fontSize', {}).get('magnitude', 0)
                    style_info["font_size"] = fs
                    style_info["is_bold"] = style.get('bold', False)
        
        # Only add if there's meaningful text
        if text_content.strip():
            entry = {
                "object_id": parent_id,
                "text": text_content,
                "style": style_info
            }
            if location:
                entry["location"] = location
                
            output_list.append(entry)

    def save_json(self, filename="source_content.json"):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.content_map, f, indent=2, ensure_ascii=False)
        print(f"Saved scan results to {filename}")

if __name__ == "__main__":
    # Use the known presentation ID
    PID = '13SnRUO47s8o22aRxdsGYsiUSH4Kuw5hzmkkCOinZD1I'
    scanner = SlidesScanner(PID)
    scanner.scan()
    scanner.save_json()
