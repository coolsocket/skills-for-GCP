import json
import os
import time
from vertexai.preview.generative_models import GenerativeModel, SafetySetting

class SlidesTranslator:
    def __init__(self, source_file="source_content.json", glossary_file="glossary.json", 
                 project=None, location=None, model_name=None, 
                 source_lang="English", target_lang="Simplified Chinese"):
        import vertexai
        
        self.project = project or "cloud-llm-preview1"
        self.location = location or "global"
        self.model_name = model_name or "gemini-3-flash-preview"
        self.source_lang = source_lang
        self.target_lang = target_lang
        
        # Initialize Vertex AI with provided or default params
        try:
            vertexai.init(project=self.project, location=self.location)
        except Exception as e:
            print(f"Warning during Vertex AI init: {e}")
        
        self.source_file = source_file
        self.glossary_file = glossary_file
        self.translated_file = "translated_content.json"
        
        # Load glossary if exists
        self.glossary = {}
        if os.path.exists(glossary_file):
            with open(glossary_file, 'r', encoding='utf-8') as f:
                self.glossary = json.load(f)

    def load_source(self):
        with open(self.source_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def translate(self):
        data = self.load_source()
        translated_data = []
        existing_map = {}
        
        # Load existing translations
        if os.path.exists(self.translated_file):
            try:
                with open(self.translated_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    for slide in existing:
                        for el in slide.get("elements", []):
                            if el.get("translated_text"):
                                key = el["object_id"]
                                if "location" in el:
                                    key = f"{key}_{el['location']['row']}_{el['location']['col']}"
                                existing_map[key] = el["translated_text"]
            except Exception as e:
                print(f"Warning: Failed to load existing translations: {e}")

        # Batch processing with ThreadPool
        BATCH_SIZE = 5
        batches = [data[i:i+BATCH_SIZE] for i in range(0, len(data), BATCH_SIZE)]
        
        # Limit max workers to avoid hitting Rate Limits (Vertex AI default is high, but let's be safe)
        MAX_WORKERS = 5 
        
        print(f"Starting translation of {len(batches)} batches with {MAX_WORKERS} workers...")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_batch = {executor.submit(self._translate_batch, batch, existing_map): i for i, batch in enumerate(batches)}
            
            results = [None] * len(batches) # Keep order
            
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    translated_batch = future.result()
                    results[batch_idx] = translated_batch
                    print(f"Batch {batch_idx + 1}/{len(batches)} completed.")
                except Exception as e:
                    print(f"Error in batch {batch_idx}: {e}")
                    results[batch_idx] = batches[batch_idx] # Fallback to original
        
        # Flatten results
        for res in results:
            if res:
                translated_data.extend(res)

        self.save_results(translated_data)

    def _translate_batch(self, batch, existing_map={}):
        model = GenerativeModel(self.model_name)
        
        text_map = {}
        # We must track which key corresponds to which element to map back correctly.
        # Table cells share the same object_id, so we need a unique key.
        
        filtered_batch = False # Track if we need to call API

        for slide in batch:
            for el in slide["elements"]:
                txt = el["text"].strip()
                if txt and not txt.isdigit(): 
                     if txt:
                        # Construct unique key
                        key = el["object_id"]
                        if "location" in el:
                            key = f"{key}_{el['location']['row']}_{el['location']['col']}"
                        
                        # SKIP if already translated
                        if key in existing_map:
                            el["translated_text"] = existing_map[key]
                        else:
                            text_map[key] = el["text"]
                            filtered_batch = True
            
        if not text_map:
            # All done or filtered
            return batch
            
        glossary_text = json.dumps(self.glossary, ensure_ascii=False)
        input_json = json.dumps(text_map, ensure_ascii=False, indent=2)
        
        prompt = f"""
        You are a professional translator for technical cloud presentations (Google Cloud, Vertex AI).
        Translate the values of the following JSON dictionary from {self.source_lang} to {self.target_lang}.
        
        INPUT VALUES:
        {input_json}
        
        RULES:
        1. Return ONLY a JSON dictionary with the EXACT SAME KEYS.
        2. Translate the values to {self.target_lang}.
        3. Use the GLOSSARY below significantly. Do not translate these terms (keep in English/Original).
        4. If a value is a number (e.g. "01") or short code, keep it as is.
        5. Keep newline characters \\n exactly where they are.
        6. If you are UNCERTAIN about a translation (e.g. ambiguous acronym), strictly mark it by appending " [UNCERTAIN]" to the value.
        
        GLOSSARY:
        {glossary_text}
        
        OUTPUT JSON:
        """
        
        retries = 0
        backoff = 2
        while True:
            try:
                response = model.generate_content(prompt)
                break # Success
            except Exception as e:
                # Check for 429 or Quota Exceeded
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "rate limit" in err_str:
                    retries += 1
                    if retries == 3:
                        print(f"Warning: Hit Rate Limit 3 times on this batch. Retrying indefinitely...")
                    print(f"    Rate limit hit (Retry {retries}). Sleeping {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60) # Cap at 60s
                else:
                    # Non-retriable error (e.g. 400 Bad Request)
                    print(f"Failed to call LLM: {e}")
                    raise e
        
        try:
            # Clean response
            text = response.text.strip()
            # ... (rest of parsing logic) ...
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
                
            translated_map = json.loads(text)
            
            # Map back
            for slide in batch:
                for el in slide["elements"]:
                    # Reconstruct key
                    key = el["object_id"]
                    if "location" in el:
                        key = f"{key}_{el['location']['row']}_{el['location']['col']}"
                        
                    if key in translated_map:
                        val = translated_map[key]
                        if val:
                            el["translated_text"] = val
                            # Check for uncertainty flag
                            if " [UNCERTAIN]" in val:
                                el["uncertain"] = True
                    else:
                        if key in text_map: # Only if we asked for it
                            el["translated_text"] = el["text"] 
            
            return batch
            
        except Exception as e:
            print(f"Failed to parse LLM response: {e}")
            raise e

    def save_results(self, data):
        with open(self.translated_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved translations to {self.translated_file}")

if __name__ == "__main__":
    translator = SlidesTranslator()
    translator.translate()
