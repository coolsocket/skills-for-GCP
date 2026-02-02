---
name: google-slides-translator
description: Automated, AI-powered translation for Google Slides presentations. It recursively scans slides, uses Vertex AI (Gemini) to translate content while preserving technical terms (via glossary) and formatting, and applies changes safely. Use this when a user wants to translate a slide deck.
---

# Google Slides Translator

This skill provides a complete workflow for translating Google Slides presentations using Google Vertex AI.

## Capabilities

1.  **Context-Aware Translation**: Translates text within the context of the user's presentation, understanding headers vs body text.
2.  **Glossary Support**: Protects technical terms (e.g., "Vertex AI", "Cloud Run") from being translated.
3.  **Safe Editing**: Uses element-level updates to preserve formatting (bold, colors, fonts).
4.  **Scalable**: Handles large decks by processing in batches (configurable).

## Prerequisites

1.  **Google Cloud Project**: A GCP project with **Vertex AI API** and **Google Slides API** enabled.
2.  **Authentication**: Local Application Default Credentials (ADC) must be set up with Drive permissions if you generally use duplication/creation features:
    ```bash
    gcloud auth application-default login --scopes=https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/presentations,https://www.googleapis.com/auth/documents.readonly,https://www.googleapis.com/auth/cloud-platform
    ```
3.  **Permissions**: The account must have `aiplatform.endpoints.predict` permission on the project.

## Usage

### 1. Basic Translation

Run the unified translation script:

Run the main wrapper script:

```bash
python3 scripts/translate_slides.py \
  --presentation-id <YOUR_DECK_ID> \
  --source-language "English" \
  --target-language "Simplified Chinese" \
  --project <GCP_PROJECT> \
  --location global \
  --create-copy
```

### 2. Interactive Selection

If you don't know the ID, run without arguments to list recent presentations:

```bash
python3 scripts/translate_slides.py --list
```

### 3. Custom Configuration

You can override the default project and model:

```bash
python3 scripts/translate_slides.py \
  --presentation-id <ID> \
  --project "cloud-llm-preview1" \
  --model "gemini-3-flash-preview" \
  --location "global" \
  --create-copy
```

## Features

### 1. Smart Optimization
- **Caching**: The tool checks `translated_content.json` before calling the API.
- **Parallel Translation**: Uses multi-threading to translate multiple batches simultaneously.
- **Language Support**: Translate between ANY languages using `--source-language` and `--target-language`.

### 2. Fidelity & Robustness
-   **Robustness**: Uses smart caching, parallel execution, and **infinite retry** with backoff for API rate limits.
-   **Structure Preservation**: Ensures formatting (bold, italics, lists) and fonts are preserved or adapted (e.g., forcing Roboto for Chinese).
-   **Verification**: Automatically verifies the output deck.
- **Infinite Retry**: Automatically handles 429 Rate Limit errors with exponential backoff. It will retry indefinitely until success, logging a warning if it struggles (3+ retries).
- **Line-by-Line Replacement**: Preserves nested lists and complex formatting.
- **Font Correction**: Automatically applies `Roboto` to translated text.

### 3. Translation Summary
- The tool tracks items that failed translation or are marked as `[UNCERTAIN]`.
- Check the logs for a final summary of any problematic slides.

## Duplication & Safety

Use `--create-copy` to automatically duplicate the presentation before translating. This ensures your original deck remains untouched. The script will output the new Presentation ID and perform all operations on the copy.

## Workflows

### Phase 0: Duplicate (Optional but Recommended)
Use `--create-copy` to duplicate the presentation. This creates a safe backup (`[Title] (Translated)`) so the original deck is never modified.

### Phase 1: Scan
The `SlidesScanner/scripts/slides_scanner.py` extracts text structure into `source_content.json`.

### Phase 2: Translate
The `SlidesTranslator/scripts/slides_translator.py` sends batches to Vertex AI and produces `translated_content.json`.

### Phase 3: Apply
The `SlidesEditor/scripts/slides_editor.py` reads the translations and updates the slide deck.

## Customization

-   **Glossary**: Edit `scripts/glossary.json` to add or remove terms that should remain in English.
-   **Skipped Slides**: By default, hidden slides are translated. Modify `slides_scanner.py` to filter them if desired.
