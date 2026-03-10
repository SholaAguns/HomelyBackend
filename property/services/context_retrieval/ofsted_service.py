"""
Ofsted scraper service for on-demand school ratings retrieval
"""
import requests
import logging
from typing import Dict, Optional, Any
from bs4 import BeautifulSoup
from datetime import datetime
from django.core.cache import cache

logger = logging.getLogger(__name__)


class OfstedService:
    """
    Scrape Ofsted reports for school ratings.

    - URL: https://reports.ofsted.gov.uk/provider/21/{URN}
    - Cache: 30 days per URN
    - Rate limiting: 1 request per second (handled by caller)
    """

    BASE_URL = "https://reports.ofsted.gov.uk/provider/21"
    CACHE_TTL = 86400 * 30  # 30 days

    # Valid Ofsted ratings
    VALID_RATINGS = ['Outstanding', 'Good', 'Requires improvement', 'Inadequate']

    @classmethod
    def get_ofsted_report(cls, urn: str) -> Dict[str, Any]:
        """
        Fetch Ofsted report for a school by URN.

        Args:
            urn: School URN (Unique Reference Number)

        Returns:
            Dict with Ofsted data or error info

        Example:
            >>> data = OfstedService.get_ofsted_report('100000')
            >>> data['overall_rating']
            'Outstanding'
        """
        # Check cache first
        cache_key = f"ofsted:{urn}"
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.info(f"Ofsted data for URN {urn} found in cache")
            cached_data['cached'] = True
            return cached_data

        # Fetch from Ofsted website
        try:
            url = f"{cls.BASE_URL}/{urn}"
            response = requests.get(url, timeout=10)

            if response.status_code == 404:
                error_data = {
                    'error': 'School not found',
                    'urn': urn,
                    'url': url,
                    'cached': False
                }
                # Cache 404s for shorter period (1 day)
                cache.set(cache_key, error_data, timeout=86400)
                return error_data

            if response.status_code != 200:
                logger.error(f"Ofsted fetch failed for URN {urn}: {response.status_code}")
                return {
                    'error': f'HTTP {response.status_code}',
                    'urn': urn,
                    'url': url,
                    'cached': False
                }

            # Parse HTML
            data = cls._parse_ofsted_html(response.text, urn, url)

            # Cache successful result
            if 'error' not in data:
                cache.set(cache_key, data, timeout=cls.CACHE_TTL)
                logger.info(f"Cached Ofsted data for URN {urn}")

            data['cached'] = False
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching Ofsted for URN {urn}: {e}")
            return {
                'error': 'Network error',
                'urn': urn,
                'cached': False
            }
        except Exception as e:
            logger.error(f"Unexpected error fetching Ofsted for URN {urn}: {e}")
            return {
                'error': 'Parse error',
                'urn': urn,
                'cached': False
            }

    @classmethod
    def _parse_ofsted_html(cls, html: str, urn: str, url: str) -> Dict[str, Any]:
        """
        Parse Ofsted HTML to extract ratings and inspection date.

        Args:
            html: HTML content
            urn: School URN
            url: Source URL

        Returns:
            Dict with parsed data
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract school name from title
            title_tag = soup.find('title')
            school_name = None
            if title_tag:
                # Format: "The Aldgate School - Open - Find an Inspection Report - Ofsted"
                parts = title_tag.text.split(' - ')
                if parts:
                    school_name = parts[0].strip()

            # Extract overall rating
            overall_div = soup.find('div', class_='subjudgements__overall')
            overall_rating = None
            inspection_date = None

            if overall_div:
                # Extract date from text like "The overall outcome of the inspection on 12 June 2024 was:"
                date_text = overall_div.find('p')
                if date_text:
                    date_str = date_text.text.strip()
                    # Extract date using simple parsing
                    if 'on ' in date_str and ' was:' in date_str:
                        date_part = date_str.split('on ')[1].split(' was:')[0].strip()
                        if date_part:  # Only try to parse if we have a date string
                            try:
                                # Parse date like "12 June 2024"
                                inspection_date = datetime.strptime(date_part, '%d %B %Y').date().isoformat()
                            except ValueError:
                                logger.warning(f"Could not parse date: {date_part}")

                # Extract rating
                rating_strong = overall_div.find('strong')
                if rating_strong:
                    overall_rating = rating_strong.text.strip()

            # Extract sub-judgements
            sub_judgements = {}
            rates_div = soup.find('div', class_='subjudgements__rates')

            if rates_div:
                items = rates_div.find_all('div', class_='subjudgements__rates__item')

                for item in items:
                    p_tag = item.find('p')
                    strong_tag = item.find('strong')

                    if p_tag and strong_tag:
                        # Clean up label (remove trailing colon)
                        label = p_tag.text.strip().rstrip(':')
                        rating = strong_tag.text.strip()

                        # Convert to snake_case key
                        key = label.lower().replace(' ', '_')
                        sub_judgements[key] = rating

            # Validate we have minimum data
            if not overall_rating:
                return {
                    'error': 'Could not parse Ofsted rating',
                    'urn': urn,
                    'url': url
                }

            return {
                'urn': urn,
                'school_name': school_name,
                'overall_rating': overall_rating,
                'inspection_date': inspection_date,
                'sub_judgements': sub_judgements,
                'report_url': url,
                'fetched_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"HTML parsing error for URN {urn}: {e}")
            return {
                'error': 'Parse error',
                'urn': urn,
                'url': url
            }

    @classmethod
    def clear_cache(cls, urn: str) -> bool:
        """
        Clear cached Ofsted data for a school.

        Args:
            urn: School URN

        Returns:
            True if cache was cleared
        """
        cache_key = f"ofsted:{urn}"
        cache.delete(cache_key)
        logger.info(f"Cleared Ofsted cache for URN {urn}")
        return True
