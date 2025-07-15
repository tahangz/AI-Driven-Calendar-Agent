# AI-Driven-Calendar-Agent

SchedulAI parses your natural language event requests (e.g., "Lunch with Sarah tomorrow at noon"), extracts the details via an LLM pipeline, and creates events in your Google Calendar automatically.

### 🚀 Key Features
- **LLM‑driven Extraction**:  
  1. **Event Detection**: Determine whether your text describes a calendar item.  
  2. **Detail Parsing**: Pull out event name, ISO‑8601 datetime, duration, and participants.  
  3. **Confirmation**: Generate a friendly confirmation message.
- **Google Calendar Integration**: OAuth2‑powered flow that writes directly to your primary calendar.  
- **Timezone‑Aware**: Uses IANA timezones (default: Africa/Tunis) to avoid scheduling mishaps.
- **Modular & Extensible**: Swap in other LLM models or downstream services with minimal changes.

### ⚙️ Installation
1. **Clone the repository**
   ```bash
   git clone https://github.com/your‑username/SchedulAI.git
   cd SchedulAI
   ````
2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Set up environment**
  - Copy the `.env` file from above and fill in your credentials.

### ▶️ Usage
Run the main script and follow the prompts:
   ```bash
   python main.py
   ```
- On first run you’ll authenticate Google Calendar via your browser.
- Then simply type something like:
      "I have a meet tomorrow at 10 am for 30min"

SchedulAI will confirm and show you a link to the new calendar event.

### 🔄 Workflow Overview (Prompt Chaining)

1. User Input → LLM pipeline extracts and validates event.
2. Parsed Data → `google-api-python-client` creates a new event.
3. Confirmation → LLM crafts a human‑friendly message including the event URL.

### 📝 Environment Variables

All configured via your `.env` file:

- ``OPENAI_API_KEY``
- ``GOOGLE_CREDENTIALS_PATH``
- ``TIMEZONE``
