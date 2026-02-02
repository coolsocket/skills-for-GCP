---
name: google-slides-beautifier
description: Redesigns Google Slides presentations using Vertex AI (Gemini 3 Pro) and high-fidelity image generation. Use this skill when the user wants to "beautify", "redesign", "modernize", or "fix" the aesthetics of a slide deck. It replaces boring text slides with stunning, theme-consistent visual slides while preserving key information via "Infographic Mode". Supports "Glassmorphism" and "Retro Vector" styles.
---

# Google Slides Beautifier (Nano Banana Standard)

This skill transforms standard text-heavy Google Slides into visually stunning, professionally designed presentations using Generative AI. It follows the "Nano Banana" workflow for high-fidelity, narrative-driven output.

## Core Capabilities

1.  **Smart Narrative Planning**:
    *   Generates separate **Cover**, **Content**, and **Data** slide structures.
    *   Supports **Strict Page Counts** (5, 5-10, 10-15, 20-25) with predefined narrative arcs.
    *   Includes **Hierarchical Bullets** (sub-points) and **Visual Metaphors**.
2.  **High-Fidelity Themes**:
    *   **Glassmorphism (`glass`)**: Unreal Engine 5 style with volumetric lighting and Bento grids.
    *   **Retro Vector (`vector`)**: Flat, monoline, pastel-colored illustrations with "Toy Model" aesthetic.
3.  **GCS Image Buffer**:
    *   Uses **Google Cloud Storage** as a public buffer for ultra-fast, high-res image injection.
    *   Auto-fallback to Drive if GCS is unavailable.
4.  **Blank Slide Cleanup**:
    *   Automatically removes the default blank title slide after generation to keep decks clean.

## Usage Guide

### Step 1: Generate Content Structure

Use the `content_agent.py` to plan your deck. This creates a JSON blueprint.

```bash
# Example: 10-page deck for executives on AI Strategy
python3 scripts/content_agent.py "Enterprise AI Strategy" \
  --audience "Executives" \
  --pages "10-15" \
  --intent "pitch" \
  --out ai_strategy.json
```

**Options**:
-   `--pages`: `5` (Quick), `5-10` (Standard), `10-15` (Deep Dive), `20-25` (Training).
-   `--intent`: `pitch` (Sales), `journey` (Vision), `education` (Explainer).

### Step 2: Build Skeleton Deck

Convert the JSON blueprint into a real Google Slides presentation (text-only skeleton).

```bash
python3 scripts/slides_generator.py ai_strategy.json
# Output: Created Presentation ID: <DECK_ID>
```

### Step 3: Beautify (Apply Theme)

Apply the chosen theme (`glass` or `vector`) to generate high-fidelity images.

```bash
python3 scripts/smart_beautifier.py \
  --presentation-id <DECK_ID> \
  --theme vector \
  --workers 5
```

**Themes**:
-   `glass`: Best for Tech, SaaS, Keynotes.
-   `vector`: Best for Education, Storytelling, Creative.

## Themes Reference

| Theme | Keyword | Style Notes | Best For |
| :--- | :--- | :--- | :--- |
| **Glassmorphism** | `glass` | Dark mode, Neon accents, Frosted glass transparency, Bento Grid | Tech demos, AI startups, High-Impact Keynotes |
| **Retro Vector** | `vector` | Flat design, Pastel colors, Monoline illustrations, Paper texture | Education, Storytelling, Creative Agencies |

## Troubleshooting

-   **Auth Errors**:
    -   Check `~/.gemini/credentials/cloud-resource-key.json` exists.
    -   Ensure you are logged in locally (`gcloud auth login`) for the Slides API.
-   **Quota Issues**:
    -   If Vertex AI quota is hit, the skill will attempt to retry with exponential backoff.
-   **Text Rendering**:
    -   If text looks "garbled", try simplifying the slide content before beautification.
