"""
Council Tax Band service using GOV.UK web scraping
"""
import requests
import logging
from typing import Dict, Any
from bs4 import BeautifulSoup
from .interface import IContextService

logger = logging.getLogger(__name__)


class CouncilTaxService(IContextService):
    """
    Retrieves council tax band from GOV.UK checker.

    Source: https://www.tax.service.gov.uk/check-council-tax-band
    Method: Web scraping (no official API available)
    Cost: FREE
    Cache: 365 days (council tax bands rarely change)
    """

    BASE_URL = "https://www.tax.service.gov.uk/check-council-tax-band/search"
    CACHE_TTL = 86400 * 365  # 365 days (1 year)

    # Band valuation ranges for England (as of 1991 values)
    BAND_RANGES_ENGLAND = {
        'A': '£0 to £40,000',
        'B': '£40,001 to £52,000',
        'C': '£52,001 to £68,000',
        'D': '£68,001 to £88,000',
        'E': '£88,001 to £120,000',
        'F': '£120,001 to £160,000',
        'G': '£160,001 to £320,000',
        'H': '£320,001 and above',
    }

    # Wales uses different ranges (2003 values)
    BAND_RANGES_WALES = {
        'A': '£0 to £44,000',
        'B': '£44,001 to £65,000',
        'C': '£65,001 to £91,000',
        'D': '£91,001 to £123,000',
        'E': '£123,001 to £162,000',
        'F': '£162,001 to £223,000',
        'G': '£223,001 to £324,000',
        'H': '£324,001 to £463,000',
        'I': '£463,001 and above',
    }

    def get_service_name(self) -> str:
        return 'council_tax'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has required fields"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for council tax data")

        if not property_obj.title:
            raise ValueError("Property must have title/address for council tax data")

        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode + normalized address for property-specific data"""
        # Normalize address for consistent caching
        address_key = property_obj.title.lower().replace(' ', '_')[:50]
        postcode_key = property_obj.postcode.replace(' ', '').upper()
        return f"council_tax:{postcode_key}:{address_key}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        """
        Fetch council tax band from GOV.UK.

        Uses web scraping as no official API exists.
        Searches by postcode first, then attempts to match property address.

        Returns:
            Dict with council tax band and related information
        """
        self.validate_property_data(property_obj)

        try:
            # Step 1: Search by postcode
            search_results = self._search_by_postcode(property_obj.postcode)

            if not search_results:
                logger.warning(f"No council tax results for postcode {property_obj.postcode}")
                return {
                    'band': None,
                    'band_range': None,
                    'local_authority': None,
                    'error': 'No results found for this postcode',
                    'retrieved_at': None
                }

            # Step 2: Try to find matching property in results
            matched_property = self._match_property(search_results, property_obj.title)

            if not matched_property:
                # If exact match fails, return first result with warning
                logger.warning(f"No exact address match for {property_obj.title}, using first result")
                matched_property = search_results[0]
                matched_property['is_exact_match'] = False
            else:
                matched_property['is_exact_match'] = True

            # Step 3: Extract band and enrich with additional data
            band = matched_property.get('band')
            band_range = self._get_band_range(band, matched_property.get('country', 'England'))

            return {
                'band': band,
                'band_range': band_range,
                'local_authority': matched_property.get('local_authority'),
                'address': matched_property.get('address'),
                'is_exact_match': matched_property.get('is_exact_match', True),
                'country': matched_property.get('country', 'England'),
                'retrieved_at': self._get_current_timestamp()
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch council tax data: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing council tax data: {e}")
            raise ValueError(f"Failed to parse council tax data: {str(e)}")

    def _search_by_postcode(self, postcode: str) -> list:
        """
        Search GOV.UK for properties in postcode.

        Args:
            postcode: UK postcode

        Returns:
            List of property dictionaries with band information
        """
        try:
            # Format postcode (remove extra spaces)
            formatted_postcode = postcode.strip().upper()

            # Make request to GOV.UK
            response = requests.get(
                self.BASE_URL,
                params={'postcode': formatted_postcode},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                timeout=15
            )
            response.raise_for_status()

            # Parse HTML response
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract results from table
            results = self._parse_results_table(soup)

            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error fetching council tax data: {e}")
            raise

    def _parse_results_table(self, soup: BeautifulSoup) -> list:
        """
        Parse results table from GOV.UK response.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of property records
        """
        results = []

        # Find results table (structure may vary, adapt as needed)
        table = soup.find('table')
        if not table:
            # Try alternative parsing if table not found
            return self._parse_results_alternative(soup)

        rows = table.find_all('tr')[1:]  # Skip header row

        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:  # Expect at least address, band, authority
                property_data = {
                    'address': cells[0].get_text(strip=True),
                    'band': cells[1].get_text(strip=True),
                    'local_authority': cells[2].get_text(strip=True) if len(cells) > 2 else None
                }
                results.append(property_data)

        return results

    def _parse_results_alternative(self, soup: BeautifulSoup) -> list:
        """
        Alternative parsing method if table structure differs.

        This is a fallback for different HTML structures.
        """
        results = []

        # Look for result divs or list items
        result_divs = soup.find_all('div', class_='result') or soup.find_all('li', class_='result')

        for div in result_divs:
            address_elem = div.find(class_='address') or div.find('h2') or div.find('strong')
            band_elem = div.find(class_='band') or div.find(string=lambda text: text and 'Band' in text)

            if address_elem and band_elem:
                band_text = band_elem.get_text(strip=True)
                # Extract just the letter (e.g., "Band D" -> "D")
                band = band_text.replace('Band', '').strip()

                results.append({
                    'address': address_elem.get_text(strip=True),
                    'band': band,
                    'local_authority': None
                })

        return results

    def _match_property(self, results: list, target_address: str) -> Dict[str, Any]:
        """
        Find matching property in search results.

        Uses fuzzy matching on address string.

        Args:
            results: List of property results
            target_address: Address to match against

        Returns:
            Matching property dict or None
        """
        target_normalized = self._normalize_address(target_address)

        best_match = None
        best_score = 0

        for result in results:
            result_normalized = self._normalize_address(result['address'])

            # Calculate simple similarity score
            score = self._calculate_similarity(target_normalized, result_normalized)

            if score > best_score:
                best_score = score
                best_match = result

        # Return match if score above threshold (70%)
        if best_score > 0.7:
            return best_match

        return None

    def _normalize_address(self, address: str) -> str:
        """Normalize address for comparison"""
        # Remove common noise words and normalize spacing
        normalized = address.lower()
        noise_words = ['flat', 'apartment', 'apt', 'unit', 'floor']

        for word in noise_words:
            normalized = normalized.replace(word, '')

        # Remove extra spaces and punctuation
        normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
        normalized = ' '.join(normalized.split())

        return normalized

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate basic similarity score between two strings.

        Uses simple word overlap method.
        """
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def _get_band_range(self, band: str, country: str = 'England') -> str:
        """Get valuation range for band letter"""
        if not band:
            return None

        band = band.upper().strip()

        if country.lower() == 'wales':
            return self.BAND_RANGES_WALES.get(band)
        else:
            return self.BAND_RANGES_ENGLAND.get(band)

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()
