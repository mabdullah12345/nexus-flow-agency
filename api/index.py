import os
import json
import urllib.request
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
import resend

load_dotenv()

app = FastAPI(
    title=os.getenv("PROJECT_NAME", "Nexus Flow Automation"),
    version="1.0.0"
)

# Clients Initialization
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY and "your-supabase" not in SUPABASE_URL:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Supabase init error: {e}")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and "sk-your" not in OPENAI_API_KEY else None

class LeadInput(BaseModel):
    client_name: str
    email: str
    phone: str
    company_name: str | None = None
    budget: float
    property_type: str
    location: str
    message: str | None = None


def send_email_notification(lead_data: dict, status: str):
    """Send an automated confirmation email to the lead."""
    if not RESEND_API_KEY:
        print("RESEND_API_KEY missing. Skipping email dispatch.")
        return

    is_qualified = lead_data.get("budget", 0) >= 5000.0
    
    if is_qualified:
        subject = f"Priority Consultation Confirmed - {lead_data['company_name']}"
        body_html = f"""
        <h3>Hi {lead_data['client_name']},</h3>
        <p>Thank you for reaching out to <strong>Nexus Flow Automation</strong>.</p>
        <p>Your requirements for <strong>{lead_data['property_type']}</strong> match our High-Priority AI acceleration tier.</p>
        <p><strong>Next Step:</strong> Please schedule a 15-minute discovery call using our priority link below:</p>
        <p><a href="https://cal.com/nexus-flow/15min" style="background:#0284c7;color:#fff;padding:10px 18px;border-radius:4px;text-decoration:none;font-weight:bold;">Book Priority Call</a></p>
        <br>
        <p>Best regards,<br><strong>Nexus Flow Engineering Team</strong></p>
        """
    else:
        subject = f"We Received Your Inquiry - Nexus Flow Automation"
        body_html = f"""
        <h3>Hi {lead_data['client_name']},</h3>
        <p>Thank you for contacting <strong>Nexus Flow Automation</strong>.</p>
        <p>We have received your details regarding <strong>{lead_data['property_type']}</strong> and added you to our nurture sequence. Our team will review your requirements and follow up via email shortly.</p>
        <br>
        <p>Best regards,<br><strong>Nexus Flow Team</strong></p>
        """

    try:
        resend.Emails.send({
            "from": "Nexus Flow <onboarding@resend.dev>",
            "to": [lead_data["email"]],
            "subject": subject,
            "html": body_html
        })
        print(f"Email sent successfully to {lead_data['email']}")
    except Exception as e:
        print(f"Email Dispatch Error: {e}")


def send_slack_notification(lead_data: dict, status: str, next_step: str):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    is_hot = lead_data.get("budget", 0) >= 5000
    header_text = "🔴 HOT LEAD ALERT ($5K+ Budget)" if is_hot else "⚡ New Lead Inbound"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Client:* {lead_data.get('client_name', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Company:* {lead_data.get('company_name', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Email:* {lead_data.get('email', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Phone:* {lead_data.get('phone', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Budget:* ${lead_data.get('budget', 0):,.2f}"},
                {"type": "mrkdwn", "text": f"*Location:* {lead_data.get('location', 'N/A')}"},
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Status:* `{status}`\n*Next Step:* {next_step}\n*AI Response:* {lead_data.get('ai_message', 'N/A')}"
            }
        },
        {"type": "divider"}
    ]

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"blocks": blocks}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Slack Notification Error: {e}")


@app.get("/")
def root():
    return {
        "status": "online",
        "system": os.getenv("PROJECT_NAME", "Nexus Flow Automation"),
        "ai_enabled": openai_client is not None
    }

@app.get("/api/v1/leads")
def get_leads():
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        response = supabase.table("leads").select("*").execute()
        return {"success": True, "leads": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/qualify-lead")
def qualify_lead(lead: LeadInput):
    is_qualified = lead.budget >= 5000.0
    status = "HIGH PRIORITY - QUALIFIED" if is_qualified else "STANDARD NURTURE"
    action = "Instant Calendar Invite Sent" if is_qualified else "Added to Email Sequence"
    
    # Generate AI Personalized Message if OpenAI is connected
    ai_response_message = "Thank you for your inquiry. Our agent will contact you shortly."
    if openai_client:
        try:
            prompt = f"Write a short, professional outreach SMS for {lead.client_name} who is looking for {lead.property_type} in {lead.location} with a budget of ${lead.budget:,.2f}. Status: {status}."
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )
            ai_response_message = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI Error: {e}")

    lead_data = {
        "client_name": lead.client_name,
        "email": lead.email,
        "phone": lead.phone,
        "company_name": lead.company_name or "N/A",
        "budget": lead.budget,
        "property_type": lead.property_type,
        "location": lead.location,
        "message": lead.message or "",
        "status": status,
        "next_step": action,
        "ai_message": ai_response_message
    }
    
    # Insert to Supabase Database
    if supabase:
        try:
            supabase.table("leads").insert(lead_data).execute()
        except Exception as e:
            print(f"DB Error: {e}")

    # Trigger Slack Rich Alert
    send_slack_notification(lead_data, status, action)

    # Trigger Automated Email Dispatch
    send_email_notification(lead_data, status)

    return {
        "success": True,
        "lead_summary": lead_data
    }

# Vercel entry handler
handler = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)