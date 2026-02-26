"""
Example script demonstrating how to use the Leads API Client directly.

This script shows how to interact with the leads/customers API using GET, POST, PUT, and DELETE operations.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.support.agent.nodes.conversation.leads_api_client import LeadsAPIClient


def example_get_leads():
    """Example: Get leads with various filters"""
    print("\n=== Example: GET Leads ===\n")
    
    client = LeadsAPIClient()
    
    try:
        # Example 1: Get all leads
        print("1. Getting all leads...")
        results = client.get_leads(limit=5)
        print(f"   Found {len(results.get('leads', []))} leads")
        
        # Example 2: Get qualified leads (A level)
        print("\n2. Getting A-level qualified leads...")
        results = client.get_leads(
            qualification_level="A",
            limit=5
        )
        print(f"   Found {len(results.get('leads', []))} A-level leads")
        
        # Example 3: Search by city
        print("\n3. Getting leads from Madrid...")
        results = client.get_leads(
            city="Madrid",
            limit=5
        )
        print(f"   Found {len(results.get('leads', []))} leads from Madrid")
        
        # Example 4: Search by budget range
        print("\n4. Getting leads with budget 200k-400k...")
        results = client.get_leads(
            budget_min=200000,
            budget_max=400000,
            limit=5
        )
        print(f"   Found {len(results.get('leads', []))} leads in that budget range")
        
        # Display first lead if available
        if results.get('leads'):
            lead = results['leads'][0]
            print(f"\n   First lead:")
            print(f"   - ID: {lead.get('id')}")
            print(f"   - Name: {lead.get('name')}")
            print(f"   - Phone: {lead.get('phone')}")
            print(f"   - Qualification: {lead.get('qualification_level')} ({lead.get('points', 0)} points)")
            if lead.get('budget_min') or lead.get('budget_max'):
                print(f"   - Budget: {lead.get('budget_min', 0):,.0f} - {lead.get('budget_max', 0):,.0f}")
        
    except Exception as e:
        print(f"   Error: {e}")
        print(f"   Make sure LEADS_API_BASE_URL is configured in .env file")


def example_create_lead():
    """Example: Create a new lead"""
    print("\n=== Example: POST (Create Lead) ===\n")
    
    client = LeadsAPIClient()
    
    # Lead data matching lead_data_retr_structure.json
    new_lead = {
        "lead": {
            "fullName": "María García",
            "phone": "+34600123456",
            "email": "maria.garcia@email.com",
            "source": "AI_Agent_Whatsapp",
            "message": "Estoy interesada en comprar un apartamento",
            "interest": {
                "transactionType": "sale",
                "propertyType": "apartment",
                "budgetMin": 200000,
                "budgetMax": 300000,
                "preferredZones": ["Madrid", "Pozuelo"]
            },
            "metadata": {
                "actionRequested": "request_info",
                "agentNotes": "Cliente interesado, tiene financiamiento preaprobado"
            }
        }
    }
    
    try:
        print("Creating new lead...")
        result = client.create_lead(new_lead)
        print(f"   Success! Created lead with ID: {result.get('id')}")
        return result.get('id')
    except Exception as e:
        print(f"   Error: {e}")
        return None


def example_update_lead(lead_id: str):
    """Example: Update an existing lead"""
    print(f"\n=== Example: PUT (Update Lead {lead_id}) ===\n")
    
    client = LeadsAPIClient()
    
    # Update data - adding qualification
    update_data = {
        "qualification_level": "A",
        "points": 12,
        "wants_visit": True,
        "has_money": True
    }
    
    try:
        print(f"Updating lead {lead_id}...")
        result = client.update_lead(lead_id, update_data)
        print(f"   Success! Updated lead")
        print(f"   - Qualification: {result.get('qualification_level')}")
        print(f"   - Points: {result.get('points')}")
    except Exception as e:
        print(f"   Error: {e}")


def example_get_lead_by_phone():
    """Example: Get lead by phone number"""
    print(f"\n=== Example: GET Lead by Phone ===\n")
    
    client = LeadsAPIClient()
    phone = "+34600123456"
    
    try:
        print(f"Fetching lead with phone {phone}...")
        lead = client.get_lead_by_phone(phone)
        
        if lead:
            print(f"   Success! Found lead:")
            print(f"   - Name: {lead.get('name')}")
            print(f"   - Email: {lead.get('email')}")
            print(f"   - Qualification: {lead.get('qualification_level')}")
        else:
            print(f"   No lead found with phone {phone}")
    except Exception as e:
        print(f"   Error: {e}")


def example_delete_lead(lead_id: str):
    """Example: Delete a lead"""
    print(f"\n=== Example: DELETE (Remove Lead {lead_id}) ===\n")
    
    client = LeadsAPIClient()
    
    try:
        print(f"Deleting lead {lead_id}...")
        result = client.delete_lead(lead_id)
        print(f"   Success! Lead deleted")
        print(f"   Response: {result}")
    except Exception as e:
        print(f"   Error: {e}")


def main():
    """Run all examples"""
    print("="*60)
    print("Leads API Client Examples")
    print("="*60)
    
    # Check configuration
    api_url = os.getenv("LEADS_API_BASE_URL", "")
    if not api_url:
        print("\n⚠️  WARNING: LEADS_API_BASE_URL not configured!")
        print("   Set this in your .env file to test the API client.")
        print("   Example: LEADS_API_BASE_URL=https://api.example.com")
        print("\n   These examples will fail without a valid API URL.\n")
    else:
        print(f"\n✓ API URL configured: {api_url}\n")
    
    # Run examples
    example_get_leads()
    example_get_lead_by_phone()
    
    # Uncomment to test create/update/delete:
    # lead_id = example_create_lead()
    # if lead_id:
    #     example_update_lead(lead_id)
    #     example_delete_lead(lead_id)
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
