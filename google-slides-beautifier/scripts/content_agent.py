import argparse
import json
import logging
import os
import time
from typing import List, Optional
from pydantic import BaseModel, Field

from auth_manager import AuthManager
from google import genai
from google.genai import types

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Data Models (The Skeleton Schema) ---

class SlideStructure(BaseModel):
    type: str = Field(description="Type of slide: 'TITLE', 'HOOK', 'CONTENT', 'SECTION', 'CONCLUSION', 'ECHO'")
    title: str = Field(description="Headline of the slide. Punchy and short.")
    body: List[str] = Field(description="Bullet points or main text content.")
    speaker_notes: str = Field(description="Script for the speaker. Includes pauses, questions to audience, and transitions.")
    visual_prompt: str = Field(description="Detailed description for the AI Image Generator (background/visuals). Must match the narrative metaphor.")

class PresentationStructure(BaseModel):
    title: str = Field(description="Title of the presentation")
    subtitle: str = Field(description="Subtitle or tagline")
    narrative_arc: str = Field(description="The chosen narrative framework (e.g., Problem-Agitation-Solution)")
    recurring_metaphor: str = Field(description="The central visual metaphor (e.g., 'Climbing Everest', 'Space Mission')")
    slides: List[SlideStructure] = Field(description="Ordered list of slides")

# --- The Content Agent ---

class ContentAgent:
    def __init__(self, auth_manager: Optional[AuthManager] = None):
        self.auth = auth_manager or AuthManager()
        self.client = self.auth.get_vertex_client(location='global') # Gemini 3 requires global
        self.model_id = "gemini-3-flash-preview" # Fast reasoning

    def generate_structure(self, topic: str, intent: str = "auto", audience: str = "general", pages: str = "5-10") -> Optional[PresentationStructure]:
        """
        Generates the detailed structure of the presentation using Gemini.
        """
        logger.info(f"🧠 Ghostwriter thinking about: '{topic}' (Audience: {audience}, Pages: {pages})")
        
        prompt = self._build_prompt(topic, intent, audience, pages)
        
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PresentationStructure,
                    temperature=0.7
                )
            )
            
            if not response.text:
                logger.error("Empty response from Gemini.")
                return None
                
            # Parse JSON
            structure_data = json.loads(response.text)
            structure = PresentationStructure(**structure_data)
            
            logger.info(f"✅ Narrative Generated: {structure.title} ({len(structure.slides)} slides)")
            logger.info(f"   Arc: {structure.narrative_arc}")
            logger.info(f"   Metaphor: {structure.recurring_metaphor}")
            
            return structure
            
        except Exception as e:
            logger.error(f"Failed to generate structure: {e}")
            return None

    def _build_prompt(self, topic: str, intent: str, audience: str, pages: str) -> str:
        # Define Page Structure Rules based on input
        page_structure_rules = ""
        if pages == "5":
             page_structure_rules = """
             - Slide 1: Cover (Title + Subtitle)
             - Slide 2-4: Core Content (1-2 key points per slide)
             - Slide 5: Summary or Call to Action
             """
        elif pages == "5-10":
             page_structure_rules = """
             - Slide 1: Cover
             - Slide 2: Table of Contents or Intro
             - Slide 3-8: Detailed Content (Chapters)
             - Slide 9-10: Summary + Next Steps
             """
        elif pages == "10-15":
             page_structure_rules = """
             - Slide 1: Cover
             - Slide 2-3: Intro/Background
             - Slide 4-12: Core Content (3-4 Chapters)
             - Slide 13-14: Case Studies / Data
             - Slide 15: Summary
             """
        else: # Default or 20-25
             page_structure_rules = """
             - Slide 1: Cover
             - Slide 2: Agenda
             - Slide 3-5: Introduction
             - Slide 6-20: Detailed Content (Multiple Chapters)
             - Slide 21-23: Case Studies
             - Slide 24: Key Findings
             - Slide 25: Summary
             """

        return f"""
You are an expert Presentation Architect (The Ghostwriter).
Your goal is to turn a Topic into a compelling Narrative Journey, strictly adhering to the page count structure.

**Request**:
- Topic: "{topic}"
- Audience: "{audience}"
- Intent: "{intent}" (If 'auto', choose the best framework)
- Target Length: "{pages}" pages

**Structure Requirement (STRICT)**:
{page_structure_rules}

**Narrative Frameworks (Choose one)**:
1. **The Pitch (Sales)**: Problem (Pain) -> Agitation (Cost) -> Solution (Gain).
2. **The Journey (Vision)**: Old World -> The Shift -> New World.
3. **The Explanation (Educational)**: Concept -> Analogy -> Example (Rule of 3).

**Engagement Rules (Crucial)**:
1. **The Hook (Slide 1-2)**: Start with a shock, a question, or a counter-intuitive fact.
2. **The Thread**: Pick a *Visual Metaphor* (e.g., 'Construction', 'Gardening', 'Sailing') and weave it into the `visual_prompt` of EVERY slide.
3. **Layered Content**: Each slide must have substantive depth. Use hierarchical bullets:
   - Primary point (Substantive phrase)
     - Secondary detail or data point
     - Specific example or implication
   Ensure at least 3 main points per 'CONTENT' slide.
4. **The Echo**: Call back to the Hook in the final slide.

**Output Requirements**:
- `body`: A list of strings. Use 2 spaces for sub-bullets (e.g., "  - Sub-point").
- `visual_prompt`: Be highly descriptive for an AI image generator. Describe style, lighting, color palette, and subjects.
- `speaker_notes`: Write not just facts, but *stage directions*. e.g., "Pause for effect", "Make eye contact".

Generate the full JSON structure now.
"""

# --- CLI Utility ---

def main():
    parser = argparse.ArgumentParser(description="Content Agent: Generate PPT Structure from Topic")
    parser.add_argument("topic", help="The main topic or title of the presentation")
    parser.add_argument("--audience", default="general", help="Target audience (e.g., 'executives', 'students')")
    parser.add_argument("--intent", default="auto", choices=["auto", "pitch", "journey", "education"], help="Narrative intent")
    parser.add_argument("--pages", default="5-10", choices=["5", "5-10", "10-15", "20-25"], help="Target page count")
    parser.add_argument("--out", default="presentation.json", help="Output JSON file")
    
    args = parser.parse_args()
    
    agent = ContentAgent()
    structure = agent.generate_structure(args.topic, args.intent, args.audience, args.pages)
    
    if structure:
        # Save to file
        with open(args.out, "w") as f:
            f.write(structure.model_dump_json(indent=2))
        logger.info(f"💾 Structure saved to {args.out}")

if __name__ == "__main__":
    main()
