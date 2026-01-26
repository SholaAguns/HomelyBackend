# Quick Test - create-from-input Endpoint

## Setup

```bash
# 1. Install dependency
pip install beautifulsoup4

# 2. Run server
python manage.py runserver

# 3. Get your access token (replace below)
```

## Test Endpoint

**Windows PowerShell:**
```powershell
$TOKEN = "YOUR_ACCESS_TOKEN"
$URL = "https://www.rightmove.co.uk/properties/123456789"

curl -X POST http://localhost:8000/api/property/properties/create-from-input/ `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d "{`"input_data`": `"$URL`", `"input_type`": `"url`"}"
```

**Git Bash / Linux / Mac:**
```bash
TOKEN="YOUR_ACCESS_TOKEN"
URL="https://www.rightmove.co.uk/properties/123456789"

curl -X POST http://localhost:8000/api/property/properties/create-from-input/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"input_data\": \"$URL\", \"input_type\": \"url\"}"
```

## Or Use Browser

Navigate to: `http://localhost:8000/api/property/properties/create-from-input/`
- Login (top right)
- Fill form and click POST

## Expected Response

```json
{
  "success": true,
  "property_data": {
    "title": "...",
    "price": "...",
    "address_line_1": "...",
    "postcode": "...",
    ...
  },
  "source": "RightmoveService"
}
```

---

**Full testing guide**: `documentation/claude_responses/manual_testing_guide.md`
**Test script**: `test_create_from_input.py`
