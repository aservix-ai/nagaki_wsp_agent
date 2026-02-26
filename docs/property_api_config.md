# Property API Configuration Example

# Remote Property Database API
# Uncomment and configure these variables to use the HTTP API client
# If PROPERTY_API_BASE_URL is not set, the system will use the legacy Supabase/mock database

# Base URL of the remote property API (without trailing slash)
# Example: https://api.example.com or http://localhost:8000
# PROPERTY_API_BASE_URL=

# Optional API key for authentication
# If your API requires authentication, uncomment and set this value
# PROPERTY_API_KEY=

## Usage Instructions

### Using HTTP API Mode
1. Set `PROPERTY_API_BASE_URL` to your API endpoint
2. (Optional) Set `PROPERTY_API_KEY` if authentication is required
3. Restart the application

### Using Legacy Mode (Supabase/Mock)
1. Leave `PROPERTY_API_BASE_URL` empty or commented out
2. Ensure `SUPABASE_PROJECT_URL` and `SUPABASE_API_KEY` are set (if using Supabase)
3. Or leave both empty to use the mock SQLite database

### Image Handling
- **HTTP API Mode**: Images are returned as URLs from the API (Twilio-compatible)
  - URLs are sent directly in WhatsApp messages
  - Format: `media.photos` array containing public URLs
  
- **Legacy Mode**: Images are stored as base64 in the database
  - Not ideal for Twilio WhatsApp
  - Consider migrating to URL-based storage

### Example Configuration for HTTP API

```bash
# .env file
PROPERTY_API_BASE_URL=https://api.inmobiliaria.com
PROPERTY_API_KEY=your_api_key_here_if_needed
```

### Testing

To test if the API is configured correctly, you can:

1. Check the logs when starting the application
2. Ask the agent: "¿Qué propiedades tienen en Madrid?"
3. If successful, you should see results from the remote API
4. If URL is not configured, it will fall back to legacy mode
