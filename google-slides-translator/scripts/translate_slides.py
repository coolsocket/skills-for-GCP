import argparse
import os
import sys
from slides_manager import GoogleWorkspaceManager
from slides_scanner import SlidesScanner
from slides_translator import SlidesTranslator
from slides_editor import SlidesEditor

def verify_files_exist():
    # Ensure source content json logic matches across modules
    pass

def main():
    parser = argparse.ArgumentParser(description="Translate Google Slides using Vertex AI.")
    parser.add_argument("--presentation-id", required=False, help="ID of the Google Slide presentation")
    parser.add_argument("--list", action='store_true', help="List recent presentations")
    parser.add_argument("--confirm-skip", action='store_true', help="Ask whether to skip hidden slides (default: True)")
    parser.add_argument("--translate-notes", action='store_true', help="Translate speaker notes (NOT IMPLEMENTED YET)")
    parser.add_argument("--project", default="cloud-llm-preview1", help="GCP Project ID for Vertex AI")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Vertex AI Model Name")
    parser.add_argument("--location", default="global", help="GCP Region for Vertex AI")
    parser.add_argument("--create-copy", action='store_true', help="Duplicate the presentation before translating")
    parser.add_argument("--source-language", default="English", help="Source language (default: English)")
    parser.add_argument("--target-language", default="Simplified Chinese", help="Target language (default: Simplified Chinese)")

    args = parser.parse_args()

    manager = GoogleWorkspaceManager()

    if args.list:
        manager.list_presentations()
        return

    pid = args.presentation_id
    if not pid:
        print("Please provide a presentation ID using --presentation-id or select one from --list.")
        manager.list_presentations()
        pid = input("\nEnter Presentation ID to translate: ").strip()
        if not pid:
            print("No ID provided. Exiting.")
            return

    if args.create_copy:
        print(f"\nDuplicating presentation {pid}...")
        try:
            # Get original name to append suffix
            original_meta = manager.get_presentation(pid)
            new_title = f"{original_meta.get('title', 'Presentation')} (Translated)"
            
            dup_result = manager.duplicate_presentation(pid, new_title)
            if dup_result:
                pid = dup_result['id']
                print(f"Created copy: {new_title}")
                print(f"New Presentation ID: {pid}")
            else:
                print("Duplication failed. Aborting to be safe.")
                return
        except Exception as e:
            print(f"Error during duplication: {e}")
            return

    # Determine script directory to find glossary and save outputs
    script_dir = os.path.dirname(os.path.abspath(__file__))
    source_file = os.path.join(script_dir, "source_content.json")
    translated_file = os.path.join(script_dir, "translated_content.json")
    glossary_file = os.path.join(script_dir, "glossary.json")

    print(f"\nTarget Presentation ID: {pid}")
    
    # 1. Scan
    print("\n--- Phase 1: Scanning ---")
    
    include_hidden = False
    if args.confirm_skip:
         ans = input("Include hidden slides? [y/N]: ").strip().lower()
         if ans == 'y':
             include_hidden = True
    
    scanner = SlidesScanner(pid, include_skipped=include_hidden)
    scanner.scan()
    scanner.save_json(source_file)

    # 2. Translate
    print("\n--- Phase 2: Translating ---")
    
    # Update internal config based on args
    translator = SlidesTranslator(source_file=source_file, glossary_file=glossary_file,
                                  project=args.project, location=args.location, model_name=args.model,
                                  source_lang=args.source_language, target_lang=args.target_language)
    translator.translated_file = translated_file # Ensure translator saves to correct path
    
    translator.translate()
    
    # 3. Edit
    print("\n--- Phase 3: Applying Changes ---")
    confirm = input("Scan and Translation complete. Apply changes to deck? [y/N]: ")
    if confirm.lower() != 'y':
        print("Aborted.")
        return

    editor = SlidesEditor(translated_file=translated_file, presentation_id=pid)
    editor.apply_translations()
    
    print("\nDone! Please check your Google Slide.")

if __name__ == "__main__":
    # Ensure we are in the right directory or handle paths
    # Because we imported from local files, we assume running from the directory containing scripts
    main()
