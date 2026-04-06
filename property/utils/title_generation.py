"""
Auto-generate unique PropertyList titles from search criteria area.
"""

from property.models import PropertyList


def generate_unique_list_title(area, project):
    """
    Generate unique PropertyList title within a project.

    If "Manchester" exists, generates "Manchester 2", "Manchester 3", etc.

    Args:
        area (str): Search criteria area
        project (Project): Project instance

    Returns:
        str: Unique title

    Examples:
        >>> generate_unique_list_title("London", project)
        "London"

        >>> # If "London" already exists
        >>> generate_unique_list_title("London", project)
        "London 2"
    """
    base_title = area.strip()
    title = base_title
    counter = 2

    while PropertyList.objects.filter(
        project=project,
        title=title
    ).exists():
        title = f"{base_title} {counter}"
        counter += 1

    return title
