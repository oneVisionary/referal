from flask import Flask, request, jsonify
import os
import speech_recognition as sr
from pydub import AudioSegment
from io import BytesIO
from flask_cors import CORS
import google.generativeai as genai
import json
from datetime import datetime, timezone
from dateutil import parser
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
genai.configure(api_key="AIzaSyALGaEEA_oOcYyLDrQF6uezxodwi2eDzZI")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
CORS(app)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'syncwaveiot@gmail.com'  
app.config['MAIL_PASSWORD'] = 'qosj npwz qaos dwek'     
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
from flask_mail import Mail, Message
mail = Mail(app)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

file_name = 'recording.wav'

def sendEmail(receivers, message_body):
    for receiver in receivers:
        msg = Message(
            subject='Synwave App',  
            sender='syncwaveiot@gmail.com',  
            recipients=[receiver]  # list expected here
        )
        msg.body = message_body
        mail.send(msg)
    return "Emails Sent!"

def calender_integration(mail_data):
    import re

    event_title = mail_data.get('title', 'Untitled Event')
    description = mail_data.get('description', '')
    event_date_str = mail_data.get('date', '')  # ISO string expected

    # ✅ If event_date is missing or invalid, exit early
    if not event_date_str:
        print("❌ Event date is missing.")
        return

    try:
        # Handle both full datetime and date-only (e.g. '2025-04-20')
        if re.match(r'^\d{4}-\d{2}-\d{2}T', event_date_str):
            start_time = datetime.datetime.fromisoformat(event_date_str)
        else:
            # Date only, add default time (10 AM)
            start_time = datetime.datetime.fromisoformat(event_date_str + "T10:00:00+00:00")
    except Exception as e:
        print("❌ Error parsing event date:", e)
        return

    end_time = start_time + datetime.timedelta(hours=1)

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("SECRET.json", SCOPES)
            creds = flow.run_local_server(port=8080)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        gmailsInfo = allgmailData()
        attendees = [{"email": email} for email in gmailsInfo]
        event = {
            "summary": event_title,
            "description": f"MOM:\n{description}",
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
            "attendees": attendees,
        }

        created_event = service.events().insert(calendarId="primary", body=event).execute()
        print(f"\n✅ Event created: {created_event.get('htmlLink')}")

    except HttpError as error:
        print(f"❌ Google Calendar error: {error}")



def convert_to_isoformat(date_str):
    try:
        dt = parser.parse(date_str, fuzzy=True)
        return dt.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat()
    except Exception as e:
        print("❌ Date parsing error:", e)
        return ""

def allgmailData():
        # Fetch emails from 'gmail' collection
    emails = []
    docs = db.collection('gmail').stream()

    for doc in docs:
        data = doc.to_dict()
        if 'email' in data:
            emails.append(data['email'])

    #print("📧 Emails:", emails)
    return emails

def generate_mom_from_transcription(transcription):
    prompt = f"""
You are a smart AI assistant. Based on the following meeting transcription, generate concise Minutes of Meeting (MoM). 
Your response MUST be a valid JSON object, without any extra explanation.

Include these fields:
- "title": A short, meaningful title for the meeting.
- "description": A brief summary of the key points discussed.
- "date": Extract any words/phrases related to a date from the transcription (e.g., specific dates, 'tomorrow', 'next week'). If no date is found, leave it as an empty string.
- "created_at": Current timestamp in ISO 8601 format, e.g., 2025-04-17T15:00:00Z

Transcription:
\"\"\"{transcription}\"\"\"

Respond only with valid JSON:
{{
  "title": "...",
  "description": "...",
  "date": "...",
  "created_at": "..."
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

    # Remove Markdown formatting if present
    if gemini_response.startswith("```json"):
        gemini_response = gemini_response[7:]
    if gemini_response.endswith("```"):
        gemini_response = gemini_response[:-3]

    gemini_response = gemini_response.strip()
    print("----------------------------")
    print("Raw Gemini response:", gemini_response)

    try:
        mom_data = json.loads(gemini_response)
    except json.JSONDecodeError as e:
        print("❌ JSON decoding failed:", e)
        return {
            "title": "Invalid",
            "description": gemini_response,
            "date": "",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    # Safely parse date
    try:
        mom_data['date'] = convert_to_isoformat(mom_data.get('date', ""))
    except Exception as e:
        print("❌ Failed to convert date:", e)
        mom_data['date'] = ""

    print("----------------------------")
    print("Final MoM data:", mom_data)

    
    try:
        db.collection('mail').add(mom_data)
        print("✅ MoM saved to Firestore")
        print("---------*********************-------------------")
        print(mom_data.get('date'))
        pro_date = mom_data.get('date')
        messageInfo =  mom_data.get('description')
        gmailsInfo = allgmailData()
        
        if pro_date!="":
            calender_integration(mom_data)
            
        else:
            print("no date")
            outData = sendEmail(gmailsInfo,messageInfo)
            print(outData)
        print("---------*********************-------------------")
        
    except Exception as e:
        print("❌ Firestore save failed:", e)

    return mom_data

@app.route('/')
def index():
    return "welcome to syncwave"

@app.route('/readMessage', methods=['GET'])
def read_message():
    try:
        doc_ref = db.collection('message').document('deaImXBJi4rVFf9HyU6f')
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            # Extract fields in desired order and format
            response_text = f"{data.get('mode', '')}\n{data.get('name', '')}\n{data.get('status', '')}"
            return response_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return "No NFC data found", 404
    except Exception as e:
        return str(e), 500

@app.route('/getMailById/<doc_id>', methods=['GET'])
def get_mail_by_id(doc_id):
    try:
        
        doc_ref = db.collection('mail').document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            mail_data = doc.to_dict()
            mail_data['id'] = doc.id  

          
            """ print("Mail Data:")
            print("title:", mail_data.get('title', ''))
            print("description:", mail_data.get('description', ''))
            print("date:", mail_data.get('date', ''))
            print("created_at:", mail_data.get('created_at', ''))
            print("id:", mail_data.get('id', '')) """
            calender_integration(mail_data)
            return jsonify(mail_data), 200
        else:
            return jsonify({'error': 'Document not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/uploadAudio', methods=['POST'])
def upload_audio():
    if request.method == 'POST':
        try:
            # Save uploaded audio
            with open(file_name, 'wb') as f:
                f.write(request.data)

            # Convert audio to text
            transcription = speech_to_text(file_name)
            print("Transcription:", transcription)

            if not transcription or "could not" in transcription.lower():
                return jsonify({
                    "status": "error",
                    "message": "Transcription failed",
                    "transcription": transcription
                }), 400

            # Generate MoM
            mom = generate_mom_from_transcription(transcription)
            print("MoM:", mom)

            # Validate generated data
            if not mom.get('title') or not mom.get('description'):
                return jsonify({
                    "status": "error",
                    "message": "Failed to generate MoM from transcription",
                    "transcription": transcription
                }), 500

            # Prepare Firestore document
            mail_data = {
                "title": mom.get('title', ""),
                "description": mom.get('description', ""),
                "date": mom.get('date', ""),
                "created_at": mom.get('created_at', datetime.now(timezone.utc).isoformat())
            }

            db.collection('mail').add(mail_data)
            print("MoM data added to Firestore")

            return jsonify({
                "status": "success",
                "message": "Audio processed and MoM saved",
                "data": mail_data
            }), 200

        except Exception as e:
            return jsonify({
                "status": "error",
                "message": "Exception occurred during processing",
                "error": str(e)
            }), 500
    else:
        return jsonify({
            "status": "error",
            "message": "Method Not Allowed"
        }), 405



@app.route('/testingCalender', methods=['GET'])
def testingCalender():
    try:
        transcription = speech_to_text(file_name)
        print("Transcription:", transcription)

        if not transcription or "could not" in transcription.lower():
            return jsonify({
                "status": "error",
                "message": "Transcription failed",
                "transcription": transcription
            }), 400

        # Generate MoM
        mom = generate_mom_from_transcription(transcription)
        print("MoM:", mom)

        # Validate generated data
        if not mom.get('title') or not mom.get('description'):
            return jsonify({
                "status": "error",
                "message": "Failed to generate MoM from transcription",
                "transcription": transcription
            }), 500

        # Prepare Firestore document
        mail_data = {
            "title": mom.get('title', ""),
            "description": mom.get('description', ""),
            "date": mom.get('date', ""),
            "created_at": mom.get('created_at', datetime.now(timezone.utc).isoformat())
        }

        db.collection('mail').add(mail_data)
        print("MoM data added to Firestore")

        return jsonify({
            "status": "success",
            "message": "Audio processed and MoM saved",
            "data": mail_data
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Exception occurred during processing",
            "error": str(e)
        }), 500





def speech_to_text(file_name):
    # Initialize the recognizer
    recognizer = sr.Recognizer()
    
    # Open the audio file
    with sr.AudioFile(file_name) as source:
        # Listen for the data (load audio to memory)
        audio_data = recognizer.record(source)
        
        # Recognize (convert from speech to text)
        try:
            text = recognizer.recognize_google(audio_data)
            print(f'Transcription: {text}')
            return text
        except sr.UnknownValueError:
            return "Google Speech Recognition could not understand audio"
        except sr.RequestError as e:
            return f"Could not request results from Google Speech Recognition service; {e}"

if __name__ == '__main__':
    port = 8888
    app.run(host='0.0.0.0', port=port)
    print(f'Listening at {port}')