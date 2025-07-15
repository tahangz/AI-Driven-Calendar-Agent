from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from openai import OpenAI
import os
import logging
import pytz
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Google Calendar API setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_CREDENTIALS_FILE = 'credentials.json'
CALENDAR_TOKEN_FILE = 'token.json'

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
model = "gpt-4o"

# --------------------------------------------------------------
# Google Calendar Functions
# --------------------------------------------------------------

def get_calendar_service():
    """Authenticate and create Google Calendar service"""
    creds = None
    if os.path.exists(CALENDAR_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(CALENDAR_TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CALENDAR_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(CALENDAR_TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    
    return build('calendar', 'v3', credentials=creds)

def create_calendar_event(event_details):
    """Create event in Google Calendar"""
    try:
        service = get_calendar_service()
        
        # Parse and convert to timezone-aware datetime
        start_time = datetime.fromisoformat(event_details.date)
        end_time = start_time + timedelta(minutes=event_details.duration_minutes)
        timezone = str(pytz.timezone(os.getenv("TIMEZONE", "UTC")))
        
        event_body = {
            'summary': event_details.name,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': timezone,
            },
            'attendees': [{'email': f"{name}@example.com"} for name in event_details.participants],
            'reminders': {
                'useDefault': True,
            },
        }
        
        event = service.events().insert(
            calendarId='primary',
            body=event_body,
            sendUpdates='all'  # Send notifications to attendees
        ).execute()
        
        logger.info(f"Calendar event created: {event.get('htmlLink')}")
        return event.get('htmlLink')
    
    except Exception as e:
        logger.error(f"Failed to create calendar event: {str(e)}")
        return None
    
# --------------------------------------------------------------
# Step 1: Define the data models for each stage
# --------------------------------------------------------------


class EventExtraction(BaseModel):
    """First LLM call: Extract basic event information"""

    description: str = Field(description="Raw description of the event")
    is_calendar_event: bool = Field(
        description="Whether this text describes a calendar event"
    )
    confidence_score: float = Field(description="Confidence score between 0 and 1")


class EventDetails(BaseModel):
    """Second LLM call: Parse specific event details"""

    name: str = Field(description="Name of the event")
    date: str = Field(
        description="Date and time of the event. Use ISO 8601 to format this value."
    )
    duration_minutes: int = Field(description="Expected duration in minutes")
    participants: list[str] = Field(description="List of participants")


class EventConfirmation(BaseModel):
    """Third LLM call: Generate confirmation message"""

    confirmation_message: str = Field(
        description="Natural language confirmation message"
    )
    calendar_link: Optional[str] = Field(
        description="Generated calendar link if applicable"
    )


# --------------------------------------------------------------
# Step 2: Define the functions
# --------------------------------------------------------------


def extract_event_info(user_input: str) -> EventExtraction:
    """First LLM call to determine if input is a calendar event"""
    logger.info("Starting event extraction analysis")
    logger.debug(f"Input text: {user_input}")

    today = datetime.now()
    date_context = f"Today is {today.strftime('%A, %B %d, %Y')}."

    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "system",
                "content": f"{date_context} Analyze if the text describes a calendar event.",
            },
            {"role": "user", "content": user_input},
        ],
        response_format=EventExtraction,
    )
    result = completion.choices[0].message.parsed
    logger.info(
        f"Extraction complete - Is calendar event: {result.is_calendar_event}, Confidence: {result.confidence_score:.2f}"
    )
    return result


def parse_event_details(description: str) -> EventDetails:
    """Second LLM call to extract specific event details"""
    logger.info("Starting event details parsing")

    today = datetime.now()
    date_context = f"Today is {today.strftime('%A, %B %d, %Y')}."

    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "system",
                "content": f"{date_context} Extract detailed event information. When dates reference 'next Tuesday' or similar relative dates, use this current date as reference.",
            },
            {"role": "user", "content": description},
        ],
        response_format=EventDetails,
    )
    result = completion.choices[0].message.parsed
    logger.info(
        f"Parsed event details - Name: {result.name}, Date: {result.date}, Duration: {result.duration_minutes}min"
    )
    logger.debug(f"Participants: {', '.join(result.participants)}")
    return result


def generate_confirmation(event_details: EventDetails, calendar_link: str = None) -> EventConfirmation:
    """Generate confirmation message with calendar link"""
    logger.info("Generating confirmation message")

    system_message = "Generate a natural confirmation message for the event. Sign off with your name; Susie."
    if calendar_link:
        system_message += f" Include this calendar link: {calendar_link}"

    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_message
            },
            {"role": "user", "content": str(event_details.model_dump())},
        ],
        response_format=EventConfirmation,
    )
    result = completion.choices[0].message.parsed
    result.calendar_link = calendar_link  # Ensure link is included
    logger.info("Confirmation message generated successfully")
    return result


# --------------------------------------------------------------
# Step 3: Chain the functions together
# --------------------------------------------------------------


def process_calendar_request(user_input: str) -> Optional[EventConfirmation]:
    """Main function implementing the prompt chain with gate check"""
    logger.info("Processing calendar request")
    logger.debug(f"Raw input: {user_input}")

    # First LLM call: Extract basic info
    initial_extraction = extract_event_info(user_input)

    # Gate check: Verify if it's a calendar event with sufficient confidence
    if (
        not initial_extraction.is_calendar_event
        or initial_extraction.confidence_score < 0.7
    ):
        logger.warning(
            f"Gate check failed - is_calendar_event: {initial_extraction.is_calendar_event}, confidence: {initial_extraction.confidence_score:.2f}"
        )
        return None

    logger.info("Gate check passed, proceeding with event processing")
    # Second LLM call: Get detailed event information
    event_details = parse_event_details(initial_extraction.description)
    
    # Create Google Calendar event
    calendar_link = create_calendar_event(event_details)

    # Third LLM call: Generate confirmation
    confirmation = generate_confirmation(event_details, calendar_link)

    logger.info("Calendar request processing completed successfully")
    return confirmation


# --------------------------------------------------------------
# Step 4: Test the chain with a valid input
# --------------------------------------------------------------

user_input = "Let's schedule a 1h team meeting next Tuesday at 2pm with Alice and Bob to discuss the project roadmap."

result = process_calendar_request(user_input)
if result:
    print(f"Confirmation: {result.confirmation_message}")
    if result.calendar_link:
        print(f"Calendar Link: {result.calendar_link}")
else:
    print("This doesn't appear to be a calendar event request.")


# --------------------------------------------------------------
# Step 5: Test the chain with an invalid input
# --------------------------------------------------------------

user_input = "Can you send an email to Alice and Bob to discuss the project roadmap?"

result = process_calendar_request(user_input)
if result:
    print(f"Confirmation: {result.confirmation_message}")
    if result.calendar_link:
        print(f"Calendar Link: {result.calendar_link}")
else:
    print("This doesn't appear to be a calendar event request.")


# --------------------------------------------------------------
# Test The Agent
# --------------------------------------------------------------

if __name__ == "__main__":
    # Set your timezone
    os.environ["TIMEZONE"] = "America/New_York"
    
    user_input = "Meeting with Alex tomorrow at 3pm for 1 hour"
    result = process_calendar_request(user_input)
    
    if result:
        print(f"Confirmation: {result.confirmation_message}")
        if result.calendar_link:
            print(f"Calendar Link: {result.calendar_link}")
    else:
        print("Not a calendar event request")