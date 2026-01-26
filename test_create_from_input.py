"""
Manual test script for create-from-input endpoint

Run with: python test_create_from_input.py
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
# BASE_URL = "http://127.0.0.1:8000"

# You'll need to replace these with actual values
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE"
PROPERTY_LIST_UUID = "YOUR_PROPERTY_LIST_UUID_HERE"

# Test URLs
RIGHTMOVE_URLS = [
    "https://www.rightmove.co.uk/properties/123456789",
    # Add more test URLs here
]


def test_create_from_input(url, token):
    """Test the create-from-input endpoint"""
    endpoint = f"{BASE_URL}/api/property/properties/create-from-input/"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_data": url,
        "input_type": "url"
    }

    print(f"\n{'='*60}")
    print(f"Testing URL: {url}")
    print(f"{'='*60}")

    try:
        response = requests.post(endpoint, json=payload, headers=headers)

        print(f"Status Code: {response.status_code}")
        print(f"\nResponse:")
        print(json.dumps(response.json(), indent=2))

        if response.status_code == 200:
            print("\n✓ SUCCESS: Property data extracted")
            return response.json()
        else:
            print("\n✗ FAILED: Error extracting property data")
            return None

    except requests.exceptions.RequestException as e:
        print(f"\n✗ REQUEST FAILED: {e}")
        return None
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return None


def test_create_property(property_data, property_list_uuid, token):
    """Test creating a property with extracted data"""
    endpoint = f"{BASE_URL}/api/property/properties/"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Add property_list to the data
    payload = property_data.copy()
    payload['property_list'] = property_list_uuid

    print(f"\n{'='*60}")
    print(f"Creating property in list: {property_list_uuid}")
    print(f"{'='*60}")

    try:
        response = requests.post(endpoint, json=payload, headers=headers)

        print(f"Status Code: {response.status_code}")
        print(f"\nResponse:")
        print(json.dumps(response.json(), indent=2))

        if response.status_code in [200, 201]:
            print("\n✓ SUCCESS: Property created")
            return response.json()
        else:
            print("\n✗ FAILED: Error creating property")
            return None

    except requests.exceptions.RequestException as e:
        print(f"\n✗ REQUEST FAILED: {e}")
        return None
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return None


def main():
    """Main test function"""
    print("="*60)
    print("Testing create-from-input endpoint")
    print("="*60)

    if ACCESS_TOKEN == "YOUR_ACCESS_TOKEN_HERE":
        print("\n⚠ WARNING: Please set ACCESS_TOKEN in the script")
        print("You can get a token by logging in via the API")
        return

    # Test extraction
    for url in RIGHTMOVE_URLS:
        result = test_create_from_input(url, ACCESS_TOKEN)

        if result and result.get('success'):
            property_data = result.get('property_data', {})

            # Optionally test full flow
            if PROPERTY_LIST_UUID != "YOUR_PROPERTY_LIST_UUID_HERE":
                print("\n" + "="*60)
                print("Testing full flow: extract → create")
                print("="*60)
                test_create_property(property_data, PROPERTY_LIST_UUID, ACCESS_TOKEN)

    print("\n" + "="*60)
    print("Testing complete")
    print("="*60)


if __name__ == "__main__":
    main()
