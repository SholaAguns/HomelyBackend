"""
Property deduplication logic for project-scoped uniqueness.

Deduplication Rules:
- Properties are unique within a Project (not globally)
- If property exists in another list in SAME project: reuse
- If property exists in another list in DIFFERENT project: create duplicate

Priority for matching:
1. UPRN (UK Property Reference Number) - most authoritative
2. external_id (Rightmove listing ID)
3. postcode + normalized_address (fallback)
"""

from django.db.models import Q
from property.models import Property, Project
import re


def normalize_address(address):
    """
    Normalize address for comparison.

    - Lowercase
    - Remove extra spaces
    - Replace common abbreviations
    - Remove punctuation

    Examples:
        "123 Main St." → "123 main street"
        "Flat 4B, Park Lane" → "flat 4b park lane"
    """
    if not address:
        return ""

    normalized = address.lower().strip()

    # Replace abbreviations
    replacements = {
        r'\bst\b\.?': 'street',
        r'\brd\b\.?': 'road',
        r'\bave\b\.?': 'avenue',
        r'\bdr\b\.?': 'drive',
        r'\bln\b\.?': 'lane',
        r'\bapt\b\.?': 'apartment',
        r'\bfl\b\.?': 'floor',
    }

    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)

    # Remove punctuation and extra spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def find_existing_property_in_project(property_data, project):
    """
    Find existing property in project using priority-based matching.

    Args:
        property_data (dict): Property data with potential keys:
            - uprn (optional)
            - external_id (optional)
            - postcode (required)
            - address_line_1 (required)
        project (Project): Project instance

    Returns:
        Property or None: Existing property if found
    """
    # Priority 1: UPRN (most authoritative)
    if property_data.get('uprn'):
        existing = Property.objects.filter(
            property_lists__project=project,
            uprn=property_data['uprn']
        ).first()
        if existing:
            return existing

    # Priority 2: Rightmove external_id
    if property_data.get('external_id'):
        existing = Property.objects.filter(
            property_lists__project=project,
            external_id=property_data['external_id']
        ).first()
        if existing:
            return existing

    # Priority 3: Postcode + normalized address (fallback)
    if property_data.get('postcode') and property_data.get('address_line_1'):
        normalized = normalize_address(property_data['address_line_1'])
        existing = Property.objects.filter(
            property_lists__project=project,
            postcode=property_data['postcode'],
            normalized_address=normalized
        ).first()
        if existing:
            return existing

    return None


def get_or_create_property_in_project(property_data, project):
    """
    Get existing property in project or create new one.

    If property exists in same project:
        - Update its details (price may have changed)
        - Return existing property

    If property exists in different project:
        - Create new duplicate (different project = different context)

    Args:
        property_data (dict): Property data
        project (Project): Project instance

    Returns:
        tuple: (property, created) where created is bool
    """
    existing = find_existing_property_in_project(property_data, project)

    if existing:
        # Update existing property with latest data
        update_fields = []

        # Update fields that might change (price, description, etc.)
        updatable_fields = [
            'title', 'price', 'bedrooms', 'bathrooms', 'square_area',
            'garden', 'parking', 'furnished_status', 'external_url',
            'latitude', 'longitude', 'city', 'address_line_2'
        ]

        for field in updatable_fields:
            if field in property_data and property_data[field] is not None:
                if getattr(existing, field) != property_data[field]:
                    setattr(existing, field, property_data[field])
                    update_fields.append(field)

        if update_fields:
            existing.save(update_fields=update_fields + ['updated_at'])

        return existing, False

    else:
        # Create new property
        # Ensure normalized_address is set
        if 'address_line_1' in property_data:
            property_data['normalized_address'] = normalize_address(
                property_data['address_line_1']
            )

        property = Property.objects.create(**property_data)
        return property, True


def bulk_deduplicate_properties_in_project(properties_data, project):
    """
    Bulk deduplication for scraping results.

    Args:
        properties_data (list[dict]): List of property data dicts
        project (Project): Project instance

    Returns:
        dict: {
            'created': [Property],
            'updated': [Property],
            'total': int
        }
    """
    created = []
    updated = []

    for prop_data in properties_data:
        prop, was_created = get_or_create_property_in_project(prop_data, project)

        if was_created:
            created.append(prop)
        else:
            updated.append(prop)

    return {
        'created': created,
        'updated': updated,
        'total': len(created) + len(updated)
    }
