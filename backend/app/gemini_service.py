import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# Try to import the modern official google-genai SDK
try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from .settings import settings

logger = logging.getLogger("reelvault.gemini")

class GeminiServiceError(Exception):
    pass

def parse_ai_json(text: str) -> Dict[str, Any]:
    """
    Parses json from Gemini response, stripping markdown backticks if present.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening ```json or ```
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini output as JSON: {text}. Error: {e}")
        # Build graceful fallback dictionary
        return {
            "summary": text,
            "suggested_post": "Failed to parse AI JSON caption. See summary.",
            "hashtags": [],
            "category": "Uncategorized",
            "platform_suggestion": "Instagram",
            "quality_notes": "AI generated a non-structured response."
        }

def analyze_video_with_gemini(video_path: str) -> Dict[str, Any]:
    """
    Uploads a local video file to Gemini Files API, waits for processing,
    then requests an analysis utilizing the specified model and settings.
    """
    if not settings.is_gemini_enabled:
        raise GeminiServiceError("Gemini API key is not configured. Please add it to your .env file.")

    if not GENAI_AVAILABLE:
        raise GeminiServiceError("The 'google-genai' package is not installed. Please run 'pip install google-genai'.")
        
    v_path = Path(video_path)
    if not v_path.exists():
        raise GeminiServiceError(f"Video file does not exist locally: {video_path}")
        
    logger.info(f"Initializing Gemini client for {v_path.name}...")
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
    uploaded_file = None
    try:
        logger.info(f"Uploading {v_path.name} to Gemini Files API...")
        # Upload using the modern client.files.upload
        uploaded_file = client.files.upload(file=v_path)
        logger.info(f"File uploaded. Name: {uploaded_file.name}. State: {uploaded_file.state}")
        
        # Poll for processing complete
        # Video files need processing before they can be sent to generate_content
        start_time = time.time()
        while uploaded_file.state.name == "PROCESSING":
            if time.time() - start_time > 300:  # 5 minutes timeout
                raise GeminiServiceError("Gemini video processing timed out.")
            logger.info("Waiting for video processing to complete...")
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise GeminiServiceError(f"Gemini video processing failed: {uploaded_file.error.message}")
            
        logger.info("Video is active and ready for analysis. Constructing prompt...")
        
        prompt = """
        You are an expert social media manager and content strategist. Analyze the attached video reel.
        
        Perform the following tasks:
        1. Summarize what happens in the reel in a clear, plain-English summary.
        2. Identify the likely business/marketing angle of this video.
        3. Write a high-converting social media caption suitable for this reel.
           - Use a confident, modern, slightly witty, professional tone.
           - Avoid cringe corporate speak or typical cheesy influencer garbage (e.g. "Calling all...", "Look no further!", "Are you ready?").
           - Keep it practical, structured, and ready to post.
           - Frame the copywriting style to suit a roofing/construction/home-services company, unless the video focuses heavily on a different, obvious topic.
        4. Generate a separate array of highly relevant, trending hashtags (e.g. ["#roofing", "#homerenovation"]).
        5. Categorize the content (e.g., Showcase, Behind-the-Scenes, Customer Testimonial, Educational, Interactive).
        6. Suggest the best platform fit (Instagram, TikTok, YouTube Shorts, LinkedIn, Facebook).
        7. Evaluate visual quality/suitability and provide brief quality/human-review notes.
        
        You MUST respond ONLY with a valid, clean JSON object matching the following structure. Do not wrap in markdown or add explanations.
        {
          "summary": "Plain English summary of video events and marketing angle...",
          "suggested_post": "Post caption here...",
          "hashtags": ["hashtag1", "hashtag2"],
          "category": "Educational / Showcase / Behind the Scenes...",
          "platform_suggestion": "Instagram / TikTok / LinkedIn...",
          "quality_notes": "e.g., Quality looks great, audio is clear. / Needs human review because caption is cut off at end."
        }
        """
        
        logger.info(f"Generating content using model: {settings.GEMINI_MODEL}...")
        # Call generate_content with video file and text prompt
        # We enforce JSON response format in config
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        logger.info("Received analysis from Gemini. Parsing...")
        result = parse_ai_json(response.text)
        return result
        
    except APIError as e:
        logger.error(f"Gemini API Error: {e}")
        raise GeminiServiceError(f"Gemini API error occurred: {e.message}")
    except Exception as e:
        logger.error(f"Unexpected error in Gemini service: {e}")
        raise GeminiServiceError(f"AI analysis failed: {str(e)}")
        
    finally:
        # Always clean up the uploaded file from Gemini's server
        if uploaded_file:
            try:
                logger.info(f"Cleaning up file {uploaded_file.name} from Gemini Files API...")
                client.files.delete(name=uploaded_file.name)
                logger.info("Cleanup completed successfully.")
            except Exception as e:
                logger.warning(f"Failed to delete temporary video file {uploaded_file.name}: {e}")
