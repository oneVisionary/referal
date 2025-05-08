import google.generativeai as genai
import json
from datetime import datetime, timezone
from dateutil import parser

# Gemini API key configuration
genai.configure(api_key="AIzaSyALGaEEA_oOcYyLDrQF6uezxodwi2eDzZI")

def convert_to_isoformat(date_str):
    try:
        dt = parser.parse(date_str, fuzzy=True)
        return dt.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat()
    except Exception as e:
        print("❌ Date parsing error:", e)
        return ""

def generate_mom_from_transcription(transcription):
    prompt = f"""
You are a smart AI assistant. Based on the following meeting transcription, generate concise Minutes of Meeting (MoM). 
Your response MUST be a valid JSON object, without any extra explanation.

Include these fields:
- "title": A short, meaningful title for the meeting.
- "description": A brief summary of the key points discussed.
- "date": Extract any words/phrases related to a date from the transcription (e.g., specific dates, 'tomorrow', 'next week'). If no date is found, leave it as an empty string.

Transcription:
\"\"\"{transcription}\"\"\"

Respond only with valid JSON:
{{
  "title": "...",
  "description": "...",
  "date": "..."
}}
"""

    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=generation_config
    )

    chat_session = model.start_chat()
    response = chat_session.send_message(prompt)
    gemini_response = response.text.strip()

    # Remove Markdown backticks if present
    if gemini_response.startswith("```json"):
        gemini_response = gemini_response[7:]
    if gemini_response.endswith("```"):
        gemini_response = gemini_response[:-3]

    gemini_response = gemini_response.strip()

    try:
        mom_data = json.loads(gemini_response)
    except json.JSONDecodeError:
        print("❌ Still not valid JSON. Raw response:")
        print(gemini_response)
        return {
            "title": "Untitled",
            "description": gemini_response,
            "date": "",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    # Add created_at and convert date if available
    mom_data['created_at'] = datetime.now(timezone.utc).isoformat()
    mom_data['date'] = convert_to_isoformat(mom_data.get('date', ""))

    return mom_data

# Sample transcription for testing
out = generate_mom_from_transcription(
    "it is happening or not but it completely fun for the entire organisation this is called Diwali and I know him very well yesterday he had a meeting with me he said that the robotic on the hand one it is not working properly so I just said to him that we need to close the bottom part one which has to be more accurately from top to bottom then this will be a great one so I think I need to walk on it on upcoming days of 15 April 2025 the time will be about 3 p.m. to 4:00 p.m. I need to analyse it and remind it"
)

print(json.dumps(out, indent=2))
#pip install python-dateutil
