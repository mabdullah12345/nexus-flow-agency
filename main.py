import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv()

app = FastAPI(
    title=os.getenv("PROJECT_NAME", "Nexus Flow Automation"),
    version="1.0.0"
)

# Clients Initialization
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY and "your-supabase" not in SUPABASE_URL:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and "sk-your" not in OPENAI_API_KEY else None

class LeadInput(BaseModel):
    client_name: str
    email: str
    phone: str
    budget: float
    property_type: str
    location: str

@app.get("/")
def root():
    return {
        "status": "online",
        "system": os.getenv("PROJECT_NAME", "Nexus Flow Automation"),
        "ai_enabled": openai_client is not None
    }

@app.post("/api/v1/qualify-lead")
def qualify_lead(lead: LeadInput):
    is_qualified = lead.budget >= 100000.0
    status = "HIGH PRIORITY - QUALIFIED" if is_qualified else "STANDARD NURTURE"
    action = "Instant Calendar Invite Sent" if is_qualified else "Added to Email Sequence"
    
    # Generate AI Personalized Message if OpenAI is connected
    ai_response_message = "Thank you for your inquiry. Our agent will contact you shortly."
    if openai_client:
        try:
            prompt = f"Write a short, professional real estate outreach SMS for {lead.client_name} who is looking for a {lead.property_type} in {lead.location} with a budget of ${lead.budget:,.2f}. Status: {status}."
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
        "budget": lead.budget,
        "property_type": lead.property_type,
        "location": lead.location,
        "status": status,
        "next_step": action,
        "ai_message": ai_response_message
    }
    
    if supabase:
        try:
            supabase.table("leads").insert(lead_data).execute()
        except Exception as e:
            print(f"DB Error: {e}")

    return {
        "success": True,
        "lead_summary": lead_data
    }

# Vercel entry handler
handler = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)