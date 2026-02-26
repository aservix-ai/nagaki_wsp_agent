"""
Example script demonstrating how to use the Property API Client directly.

This script shows how to interact with the property API using GET, POST, PUT, and DELETE operations.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.support.agent.nodes.conversation.property_api_client import PropertyAPIClient


def example_get_properties():
    """Example: Get properties with various filters"""
    print("\n=== Example: GET Properties ===\n")
    
    # Initialize client (reads from environment variables)
    client = PropertyAPIClient()
    
    try:
        # Example 1: Get all properties in Madrid
        print("1. Getting properties in Madrid...")
        results = client.get_properties(city="Madrid", limit=5)
        print(f"   Found {len(results.get('properties', []))} properties")
        
        # Example 2: Get apartments for rent with specific criteria
        print("\n2. Getting apartments for rent with elevator...")
        results = client.get_properties(
            operation_type="rent",
            property_type="apartment",
            city="Madrid",
            max_price=1000,
            has_elevator=True,
            min_bedrooms=2,
            limit=5
        )
        print(f"   Found {len(results.get('properties', []))} properties")
        
        # Example 3: Search with keyword
        print("\n3. Searching for 'piscina' (pool)...")
        results = client.get_properties(
            keyword="piscina",
            has_pool=True,
            limit=5
        )
        print(f"   Found {len(results.get('properties', []))} properties")
        
        # Display first property if available
        if results.get('properties'):
            prop = results['properties'][0]
            print(f"\n   First property:")
            print(f"   - ID: {prop.get('id')}")
            print(f"   - Title: {prop.get('title')}")
            print(f"   - Price: {prop.get('price')} {prop.get('currency')}")
            
            # Show photo URLs (Twilio-compatible)
            media = prop.get('media', {})
            photos = media.get('photos', [])
            if photos:
                print(f"   - Photos ({len(photos)} available):")
                for i, photo_url in enumerate(photos[:3], 1):
                    print(f"     {i}. {photo_url}")
        
    except Exception as e:
        print(f"   Error: {e}")
        print(f"   Make sure PROPERTY_API_BASE_URL is configured in .env file")


def example_create_property():
    """Example: Create a new property"""
    print("\n=== Example: POST (Create Property) ===\n")
    
    client = PropertyAPIClient()
    
    # Property data matching product_req_structure.json
    new_property = {
        "title": "Modern apartment in downtown",
        "description": "Beautiful 2-bedroom apartment with city views",
        "price": 250000,
        "currency": "EUR",
        "operationType": "sale",
        "location": {
            "address": "Calle Mayor 123",
            "city": "Madrid",
            "zone": "Centro",
            "zipCode": "28013"
        },
        "specs": {
            "builtArea": 85,
            "bedrooms": 2,
            "bathrooms": 1,
            "floor": 3,
            "constructionYear": 2020
        },
        "features": ["elevator", "air conditioning", "balcony"],
        "status": "active",
        "propertyType": "apartment",
        "media": {
            "photos": [
                "https://example.com/photos/apt1-living.jpg",
                "https://example.com/photos/apt1-bedroom.jpg"
            ]
        }
    }
    
    try:
        print("Creating new property...")
        result = client.create_property(new_property)
        print(f"   Success! Created property with ID: {result.get('id')}")
        return result.get('id')
    except Exception as e:
        print(f"   Error: {e}")
        return None


def example_update_property(property_id: str):
    """Example: Update an existing property"""
    print(f"\n=== Example: PUT (Update Property {property_id}) ===\n")
    
    client = PropertyAPIClient()
    
    # Partial update data
    update_data = {
        "price": 245000,  # Price reduction
        "status": "reserved"  # Mark as reserved
    }
    
    try:
        print(f"Updating property {property_id}...")
        result = client.update_property(property_id, update_data)
        print(f"   Success! Updated property")
        print(f"   - New price: {result.get('price')} {result.get('currency')}")
        print(f"   - New status: {result.get('status')}")
    except Exception as e:
        print(f"   Error: {e}")


def example_delete_property(property_id: str):
    """Example: Delete a property"""
    print(f"\n=== Example: DELETE (Remove Property {property_id}) ===\n")
    
    client = PropertyAPIClient()
    
    try:
        print(f"Deleting property {property_id}...")
        result = client.delete_property(property_id)
        print(f"   Success! Property deleted")
        print(f"   Response: {result}")
    except Exception as e:
        print(f"   Error: {e}")


def main():
    """Run all examples"""
    print("="*60)
    print("Property API Client Examples")
    print("="*60)
    
    # Check configuration
    api_url = os.getenv("PROPERTY_API_BASE_URL", "")
    if not api_url:
        print("\n⚠️  WARNING: PROPERTY_API_BASE_URL not configured!")
        print("   Set this in your .env file to test the API client.")
        print("   Example: PROPERTY_API_BASE_URL=https://api.example.com")
        print("\n   These examples will fail without a valid API URL.\n")
    else:
        print(f"\n✓ API URL configured: {api_url}\n")
    
    # Run examples
    example_get_properties()
    
    # Uncomment to test create/update/delete:
    # property_id = example_create_property()
    # if property_id:
    #     example_update_property(property_id)
    #     example_delete_property(property_id)
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
