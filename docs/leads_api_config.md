# Leads/Customer API Configuration

## Environment Variables

Add these to your `.env` file to enable the leads management API:

```bash
# Leads/Customer Database API
LEADS_API_BASE_URL=https://api.example.com
LEADS_API_KEY=your_api_key_here  # Optional, if authentication required
```

## API Endpoints

The leads API uses the following structure:

- **GET** `/api/v1/leads` - List leads with filters
- **POST** `/api/v1/leads` - Create new lead
- **PUT** `/api/v1/leads/{id}` - Update lead
- **DELETE** `/api/v1/leads/{id}` - Delete lead

## Available Tools

### 1. `registrar_lead`

Registers a new customer/lead in the CRM system.

**Parameters:**
- `phone` (required): Customer phone number
- `name`: Full name
- `email`: Email address
- `property_interest`: Specific property ID they're interested in
- `message`: Initial customer message
- `budget_min`: Minimum budget
- `budget_max`: Maximum budget
- `transaction_type`: "sale" or "rent"
- `property_type`: "apartment", "house", etc.
- `preferred_zones`: List of preferred areas
- `action_requested`: "schedule_visit", "request_info", etc.
- `agent_notes`: Notes from the agent about the customer

**Example Usage:**
```python
from src.support.agent.nodes.conversation.tools import registrar_lead

result = registrar_lead(
    phone="+34600123456",
    name="Juan Pérez",
    email="juan@email.com",
    transaction_type="sale",
    property_type="apartment",
    budget_max=300000,
    preferred_zones=["Madrid", "Pozuelo"],
    action_requested="schedule_visit",
    agent_notes="Cliente tiene crédito pre-aprobado"
)
```

### 2. `consultar_lead`

Retrieves lead information by phone number.

**Parameters:**
- `phone` (required): Phone number to search

**Example:**
```python
from src.support.agent.nodes.conversation.tools import consultar_lead

lead_info = consultar_lead(phone="+34600123456")
```

### 3. `actualizar_calificacion_lead`

Updates lead qualification by adding points.

**Parameters:**
- `phone` (required): Lead phone number
- `points_to_add` (required): Points to add
- `reason` (required): Reason for point addition

**Qualification Levels:**
- **A**: 12+ points (high quality lead)
- **B**: 6-11 points (medium quality)
- **C**: 0-5 points (low quality)

**Example:**
```python
from src.support.agent.nodes.conversation.tools import actualizar_calificacion_lead

result = actualizar_calificacion_lead(
    phone="+34600123456",
    points_to_add=4,
    reason="Cliente confirmó financiamiento"
)
```

## Data Structure

The API expects leads in this format (based on `lead_data_retr_structure.json`):

```json
{
  "lead": {
    "fullName": "Juan Perez",
    "phone": "+573001234567",
    "email": "juan.perez@email.com",
    "source": "AI_Agent_Whatsapp",
    "message": "Hola, estoy interesado...",
    "interest": {
      "propertyId": "REF-1024",
      "transactionType": "sale",
      "propertyType": "apartment",
      "budgetMin": 200000,
      "budgetMax": 300000,
      "preferredZones": ["Poblado", "Envigado"]
    },
    "metadata": {
      "actionRequested": "schedule_visit",
      "capturedAt": "2024-02-21T09:00:00Z",
      "agentNotes": "El cliente tiene crédito pre-aprobado.",
      "last_contact": "2024-02-21T10:00:00Z"
    }
  }
}
```

## Database Schema

The leads table structure:

```sql
CREATE TABLE leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT NOT NULL,
  name TEXT,
  email TEXT,
  city TEXT,
  property_interest TEXT,
  property_type TEXT,
  budget_min NUMERIC,
  budget_max NUMERIC,
  has_money BOOLEAN,
  wants_visit BOOLEAN,
  qualification_level TEXT, -- A/B/C
  summary TEXT,
  points INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  last_contact TIMESTAMP
);
```

## Integration with Agent

The agent automatically uses these tools when:

1. **Customer shows interest** → `registrar_lead` is called
2. **Returning customer** → `consultar_lead` retrieves their info
3. **Customer engagement increases** → `actualizar_calificacion_lead` updates their score

The tools only work when `LEADS_API_BASE_URL` is configured. Otherwise, they return a message indicating the system is not configured.

## Testing

Run the example script to test the leads API:

```bash
python examples/leads_api_example.py
```

Make sure to configure `LEADS_API_BASE_URL` first in your `.env` file.
