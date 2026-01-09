"""
Web Scraper for Demographic Data
Scrapes demographic and market data from public sources to fill gaps
"""

import requests
from typing import Dict, Any, Optional, List
import json
import re
from bs4 import BeautifulSoup
try:
    from .nuisance_checker import NuisanceChecker
    from .climate_risk_checker import ClimateRiskChecker
    from .employer_stability_checker import EmployerStabilityChecker
except ImportError:
    from nuisance_checker import NuisanceChecker
    from climate_risk_checker import ClimateRiskChecker
    from employer_stability_checker import EmployerStabilityChecker


class DemographicScraper:
    """Scrape demographic data from web sources."""

    def __init__(self, address: str, city: str, state: str, zip_code: str, lat: float = None, lon: float = None, cache_dir: str = None):
        """
        Initialize scraper with property location.

        Args:
            address: Property street address
            city: City name
            state: State abbreviation
            zip_code: ZIP code
            lat: Latitude (optional, for geocoding)
            lon: Longitude (optional, for geocoding)
            cache_dir: Directory to cache API results (optional)
        """
        self.address = address
        self.city = city
        self.state = state
        self.zip_code = zip_code
        self.lat = lat
        self.lon = lon
        self.cache_dir = cache_dir
        self.scraped_data = {}

    def scrape_all(self) -> Dict[str, Any]:
        """
        Scrape data from all available sources.

        Returns:
            Dictionary containing scraped demographic data
        """
        # Get coordinates if not provided
        if not self.lat or not self.lon:
            self._geocode_address()

        # Scrape each data source
        print(f"\n[INFO] Scraping demographic data for {self.city}, {self.state}...")

        county_data = self._get_county()
        school_data = self._get_school_ratings()
        crime_data = self._get_crime_data()
        flood_data = self._get_flood_risk()
        ownership_data = self._get_home_ownership()
        walkability_data = self._get_walkability_score()
        transit_data = self._get_transit_score()
        nuisance_data = self._get_nuisance_check()
        climate_risk_data = self._get_climate_risk_check()
        employer_stability_data = self._get_employer_stability_check()

        # Calculate renter occupied % from home ownership
        renter_occupied_pct = None
        if ownership_data is not None:
            renter_occupied_pct = round(100 - ownership_data, 1)
            print(f"[OK] Renter occupied: {renter_occupied_pct}%")

        # Extract flood zone and risk from flood_data dict
        flood_zone = flood_data.get('flood_zone') if flood_data else None
        flood_risk = flood_data.get('flood_risk') if flood_data else None
        flood_source_url = flood_data.get('source_url') if flood_data else None

        # Build GreatSchools boundary map URL (for manual school lookup)
        greatschools_url = None
        if self.lat and self.lon:
            greatschools_url = f"https://www.greatschools.org/school-district-boundaries-map/?lat={self.lat}&lon={self.lon}"

        self.scraped_data = {
            'county': county_data,
            'school_ratings': school_data,
            'crime_data': crime_data,
            'flood_zone': flood_zone,
            'flood_risk': flood_risk,
            'flood_source_url': flood_source_url,
            'home_ownership_pct': ownership_data,
            'renter_occupied_pct': renter_occupied_pct,
            'walkability': walkability_data,
            'transit_score': transit_data,
            'nuisance_data': nuisance_data,
            'climate_risk_data': climate_risk_data,
            'employer_stability_data': employer_stability_data,
            'latitude': self.lat,
            'longitude': self.lon,
            'greatschools_url': greatschools_url
        }

        return self.scraped_data

    def _geocode_address(self):
        """Get lat/lon from address using free geocoding services."""
        # Try Census Geocoding API first (free, no key required)
        try:
            url = "https://geocoding.geo.census.gov/geocoder/locations/address"
            params = {
                'street': self.address,
                'city': self.city,
                'state': self.state,
                'zip': self.zip_code,
                'benchmark': 'Public_AR_Current',
                'format': 'json'
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('result', {}).get('addressMatches'):
                    coords = data['result']['addressMatches'][0]['coordinates']
                    self.lat = coords['y']
                    self.lon = coords['x']
                    print(f"[OK] Geocoded via Census: {self.lat}, {self.lon}")
                    return
        except Exception as e:
            print(f"[WARNING] Census geocoding failed: {e}")

        # Fallback to Nominatim (OpenStreetMap) if Census fails
        try:
            from urllib.parse import quote
            full_address = f"{self.address}, {self.city}, {self.state} {self.zip_code}"
            url = f"https://nominatim.openstreetmap.org/search?q={quote(full_address)}&format=json&limit=1"
            headers = {'User-Agent': 'RMP-Screener/1.0'}

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data:
                    self.lat = float(data[0]['lat'])
                    self.lon = float(data[0]['lon'])
                    print(f"[OK] Geocoded via Nominatim: {self.lat}, {self.lon}")
                    return

            print(f"[WARNING] Could not geocode address with either service")
        except Exception as e:
            print(f"[ERROR] Geocoding failed: {e}")

    def _get_county(self) -> Optional[str]:
        """
        Get county name from coordinates using Census reverse geocoding.
        Returns county name without 'County' suffix.
        """
        try:
            if not self.lat or not self.lon:
                print(f"[INFO] No coordinates for county lookup")
                return None

            # Use Census Geocoding API for reverse geocoding
            url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
            params = {
                'x': self.lon,
                'y': self.lat,
                'benchmark': 'Public_AR_Current',
                'vintage': 'Current_Current',
                'layers': 'Counties',
                'format': 'json'
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                geographies = data.get('result', {}).get('geographies', {})
                counties = geographies.get('Counties', [])
                if counties:
                    county_name = counties[0].get('BASENAME', '')
                    if county_name:
                        print(f"[OK] County: {county_name}")
                        return county_name

            print(f"[INFO] Could not determine county from coordinates")
            return None

        except Exception as e:
            print(f"[WARNING] County lookup failed: {e}")
            return None

    def _get_school_ratings(self) -> Optional[Dict[str, Any]]:
        """
        Get school ratings using SchoolDigger API.

        Search priority:
        1. Check cache (if cache_dir provided and cache is fresh)
        2. Assigned schools - boundaryAddress on /schools endpoint (DEV/Enterprise tier)
           Returns actual schools serving the address with individual ratings
        3. District average - finds district and averages all schools by level
           Falls back to ZIP search if boundaryAddress not available

        Returns school_method field: 'Assigned' or 'District Avg' to indicate data type
        """
        import os
        from datetime import datetime

        # Check for cached data first
        cache_file = None
        if self.cache_dir:
            cache_file = os.path.join(self.cache_dir, 'school_cache.json')
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        cached = json.load(f)

                    cache_date = datetime.fromisoformat(cached.get('cached_date', '2000-01-01'))
                    days_old = (datetime.now() - cache_date).days
                    cached_data = cached.get('data', {})

                    # If previous lookup failed (Manual), retry after 1 day
                    # If successful data, keep for 30 days
                    is_failed_cache = cached_data.get('school_method') == 'Manual'
                    max_age = 1 if is_failed_cache else 30

                    if days_old < max_age:
                        if is_failed_cache:
                            print(f"[CACHE] Using cached school data (API failed {days_old} day(s) ago, retry tomorrow)")
                        else:
                            print(f"[CACHE] Using cached school data ({days_old} days old)")
                        return cached_data
                    else:
                        print(f"[CACHE] School cache expired ({days_old} days old), refreshing...")
                except Exception as e:
                    print(f"[CACHE] Could not read cache: {e}")

        # SchoolDigger API credentials
        APP_ID = '6ef87f1b'
        APP_KEY = 'a595e0cbac9b11eefc6db179081500eb'
        full_address = f"{self.address}, {self.city}, {self.state} {self.zip_code}"

        # Step 1: Try to get ASSIGNED SCHOOLS using boundaryAddress on schools endpoint (DEV/Enterprise)
        assigned_result = self._try_assigned_schools(APP_ID, APP_KEY, full_address, cache_file)
        if assigned_result:
            return assigned_result

        # Step 2: Fall back to DISTRICT AVERAGE method
        return self._get_district_average_schools(APP_ID, APP_KEY, full_address, cache_file)

    def _try_assigned_schools(self, app_id: str, app_key: str, full_address: str, cache_file: str) -> Optional[Dict[str, Any]]:
        """
        Try to get actual assigned schools using boundaryAddress on /schools endpoint.
        This requires DEV/Enterprise tier.

        Returns dict with school_method='Assigned' if successful, None otherwise.
        """
        from datetime import datetime

        try:
            url = 'https://api.schooldigger.com/v2.0/schools'
            params = {
                'st': self.state.upper(),
                'boundaryAddress': full_address,
                'appID': app_id,
                'appKey': app_key,
                'perPage': 10  # Should only get a few assigned schools
            }

            response = requests.get(url, params=params, timeout=15)

            # Check if boundaryAddress is not available (Basic tier)
            if response.status_code == 400:
                if 'Enterprise' in response.text or 'boundaryAddress' in response.text:
                    print(f"[INFO] Assigned schools requires DEV/Enterprise tier, using district average")
                    return None

            if response.status_code != 200:
                print(f"[INFO] Assigned schools lookup failed ({response.status_code})")
                return None

            data = response.json()
            school_list = data.get('schoolList', [])

            if not school_list:
                print(f"[INFO] No assigned schools found for address")
                return None

            # Filter to public schools only
            public_schools = [s for s in school_list if not s.get('isPrivate')]

            if not public_schools:
                print(f"[INFO] No public assigned schools found")
                return None

            # Organize by school level
            schools_data = {
                'school_method': 'Assigned',
                'district_rating': None,
                'district_name': None,
                'elementary_avg': None,
                'elementary_name': None,
                'middle_avg': None,
                'middle_name': None,
                'high_avg': None,
                'high_name': None,
                'overall_grade': None,
                'source': 'SchoolDigger API',
                'source_url': None,
                'notes': ''
            }

            all_ratings = []
            notes_parts = ['Assigned Schools:']

            for school in public_schools:
                school_name = school.get('schoolName', 'Unknown')
                rank_history = school.get('rankHistory') or []

                if not rank_history:
                    continue

                latest = rank_history[0]
                percentile = latest.get('rankStatewidePercentage')
                rank_level = latest.get('rankLevel', school.get('schoolLevel', ''))

                if percentile is None:
                    continue

                rating = round(percentile / 10, 1)
                all_ratings.append(rating)

                # Get district info from first school
                if not schools_data['district_name']:
                    district_info = school.get('district', {})
                    schools_data['district_name'] = district_info.get('districtName')
                    schools_data['source_url'] = school.get('url') or f"https://www.schooldigger.com/go/{self.state.upper()}/schools/{school.get('schoolid')}/search.aspx"

                # Assign to appropriate level (first one found for each level)
                if rank_level == 'Elementary' and schools_data['elementary_avg'] is None:
                    schools_data['elementary_avg'] = rating
                    schools_data['elementary_name'] = school_name
                    notes_parts.append(f"Elem: {school_name} ({rating}/10)")
                elif rank_level == 'Middle' and schools_data['middle_avg'] is None:
                    schools_data['middle_avg'] = rating
                    schools_data['middle_name'] = school_name
                    notes_parts.append(f"Mid: {school_name} ({rating}/10)")
                elif rank_level == 'High' and schools_data['high_avg'] is None:
                    schools_data['high_avg'] = rating
                    schools_data['high_name'] = school_name
                    notes_parts.append(f"High: {school_name} ({rating}/10)")

            if all_ratings:
                schools_data['district_rating'] = round(sum(all_ratings) / len(all_ratings), 1)
                schools_data['overall_grade'] = self._number_to_grade(schools_data['district_rating'])
                schools_data['notes'] = ' | '.join(notes_parts)

                print(f"[OK] Found ASSIGNED schools for address:")
                if schools_data['elementary_name']:
                    print(f"     Elementary: {schools_data['elementary_name']} - {schools_data['elementary_avg']}/10")
                if schools_data['middle_name']:
                    print(f"     Middle: {schools_data['middle_name']} - {schools_data['middle_avg']}/10")
                if schools_data['high_name']:
                    print(f"     High: {schools_data['high_name']} - {schools_data['high_avg']}/10")

                # Save to cache
                self._save_school_cache(cache_file, schools_data)
                return schools_data

            return None

        except Exception as e:
            print(f"[INFO] Assigned schools lookup error: {e}")
            return None

    def _get_district_average_schools(self, app_id: str, app_key: str, full_address: str, cache_file: str) -> Optional[Dict[str, Any]]:
        """
        Get school ratings using district average method.
        Tries boundaryAddress on districts endpoint first, falls back to ZIP.

        Returns dict with school_method='District Avg'
        """
        from datetime import datetime

        try:
            schools_data = {
                'school_method': 'District Avg',
                'district_rating': None,
                'district_name': None,
                'elementary_avg': None,
                'elementary_name': None,
                'middle_avg': None,
                'middle_name': None,
                'high_avg': None,
                'high_name': None,
                'overall_grade': None,
                'source': None,
                'source_url': None,
                'notes': ''
            }

            # Step 1: Try to find exact district using boundaryAddress (Enterprise/DEV tier)
            district_id = None
            district_name = None
            search_method = None

            try:
                districts_url = 'https://api.schooldigger.com/v2.0/districts'
                boundary_params = {
                    'st': self.state.upper(),
                    'boundaryAddress': full_address,
                    'appID': app_id,
                    'appKey': app_key,
                    'perPage': 1
                }
                boundary_response = requests.get(districts_url, params=boundary_params, timeout=15)

                if boundary_response.status_code == 200:
                    boundary_data = boundary_response.json()
                    district_list = boundary_data.get('districtList', [])
                    if district_list:
                        district_id = district_list[0].get('districtID')
                        district_name = district_list[0].get('districtName')
                        search_method = 'boundaryAddress (exact district)'
                        print(f"[OK] Found district by address: {district_name}")
                elif boundary_response.status_code == 400 and 'Enterprise' in boundary_response.text:
                    print(f"[INFO] boundaryAddress requires Enterprise tier, falling back to ZIP")
                else:
                    print(f"[INFO] boundaryAddress failed ({boundary_response.status_code}), falling back to ZIP")
            except Exception as e:
                print(f"[INFO] boundaryAddress lookup failed: {e}, falling back to ZIP")

            # Step 2: Query schools - either by district ID or ZIP code
            url = 'https://api.schooldigger.com/v2.0/schools'

            if district_id:
                # We have exact district - query schools in that district
                params = {
                    'st': self.state.upper(),
                    'districtID': district_id,
                    'appID': app_id,
                    'appKey': app_key,
                    'perPage': 50
                }
                response = requests.get(url, params=params, timeout=15)
            else:
                # Fall back to ZIP code search
                params = {
                    'st': self.state.upper(),
                    'zip': self.zip_code,
                    'appID': app_id,
                    'appKey': app_key,
                    'perPage': 50
                }
                response = requests.get(url, params=params, timeout=15)
                search_method = 'ZIP code'

            print(f"[INFO] SchoolDigger search method: {search_method}")

            if response.status_code == 200:
                data = response.json()

                # Check if we got rate-limited (bogus data)
                if data.get('_comment') and 'limit' in data.get('_comment', '').lower():
                    print(f"[WARN] SchoolDigger API rate limit reached")
                    raise Exception("API rate limit reached")

                school_list = data.get('schoolList', [])
                if not school_list:
                    raise Exception("No schools found")

                # If we already have district from boundaryAddress, use all schools from response
                # Otherwise, group by district and pick the largest one in ZIP
                if district_id and district_name:
                    # We have exact district - use all public schools from response
                    primary_district = {
                        'name': district_name,
                        'url': f"https://www.schooldigger.com/go/{self.state.upper()}/district/{district_id}/search.aspx",
                        'schools': [s for s in school_list if not s.get('isPrivate')]
                    }
                else:
                    # ZIP search - group schools by district to find the primary district
                    districts = {}
                    for school in school_list:
                        if school.get('isPrivate'):
                            continue

                        district_info = school.get('district', {})
                        d_id = district_info.get('districtID')
                        if d_id:
                            if d_id not in districts:
                                districts[d_id] = {
                                    'name': district_info.get('districtName', 'Unknown District'),
                                    'url': district_info.get('url'),
                                    'schools': []
                                }
                            districts[d_id]['schools'].append(school)

                    if not districts:
                        raise Exception("No public school districts found")

                    # Use the district with the most schools in this ZIP (likely the primary district)
                    primary_district_id = max(districts, key=lambda d: len(districts[d]['schools']))
                    primary_district = districts[primary_district_id]
                    district_name = primary_district['name']

                schools_data['district_name'] = primary_district['name']
                schools_data['source_url'] = primary_district.get('url') or f"https://www.schooldigger.com/go/{self.state.upper()}/zip/{self.zip_code}/search.aspx"

                # Collect percentile ratings by school level
                elementary_pcts = []
                middle_pcts = []
                high_pcts = []

                for school in primary_district['schools']:
                    rank_history = school.get('rankHistory') or []
                    if not rank_history:
                        continue

                    # Get the most recent ranking
                    latest = rank_history[0]
                    percentile = latest.get('rankStatewidePercentage')
                    rank_level = latest.get('rankLevel', school.get('schoolLevel', ''))

                    if percentile is not None:
                        # Categorize by rankLevel (more accurate than parsing grades)
                        if rank_level == 'Elementary':
                            elementary_pcts.append(percentile)
                        elif rank_level == 'Middle':
                            middle_pcts.append(percentile)
                        elif rank_level == 'High':
                            high_pcts.append(percentile)

                # Convert percentiles to 1-10 scale (percentile / 10)
                if elementary_pcts:
                    avg_pct = sum(elementary_pcts) / len(elementary_pcts)
                    schools_data['elementary_avg'] = round(avg_pct / 10, 1)
                if middle_pcts:
                    avg_pct = sum(middle_pcts) / len(middle_pcts)
                    schools_data['middle_avg'] = round(avg_pct / 10, 1)
                if high_pcts:
                    avg_pct = sum(high_pcts) / len(high_pcts)
                    schools_data['high_avg'] = round(avg_pct / 10, 1)

                # Calculate overall district rating
                all_pcts = elementary_pcts + middle_pcts + high_pcts
                if all_pcts:
                    overall_pct = sum(all_pcts) / len(all_pcts)
                    schools_data['district_rating'] = round(overall_pct / 10, 1)
                    schools_data['overall_grade'] = self._number_to_grade(schools_data['district_rating'])
                    schools_data['source'] = 'SchoolDigger API'

                    # Build notes - indicate if exact district or ZIP average
                    if 'boundaryAddress' in (search_method or ''):
                        notes_parts = [f"District (exact): {primary_district['name']}"]
                    else:
                        notes_parts = [f"District (ZIP avg): {primary_district['name']}"]

                    if elementary_pcts:
                        notes_parts.append(f"Elem: top {round(100 - sum(elementary_pcts)/len(elementary_pcts))}% ({len(elementary_pcts)} schools)")
                    if middle_pcts:
                        notes_parts.append(f"Mid: top {round(100 - sum(middle_pcts)/len(middle_pcts))}% ({len(middle_pcts)} schools)")
                    if high_pcts:
                        notes_parts.append(f"High: top {round(100 - sum(high_pcts)/len(high_pcts))}% ({len(high_pcts)} schools)")
                    schools_data['notes'] = ' | '.join(notes_parts)

                    print(f"[OK] SchoolDigger - {primary_district['name']}")
                    print(f"     Elem: {schools_data['elementary_avg']}/10, Mid: {schools_data['middle_avg']}/10, High: {schools_data['high_avg']}/10")

                    # Save to cache
                    self._save_school_cache(cache_file, schools_data)
                    return schools_data
                else:
                    raise Exception("No school rankings found in API response")

            else:
                raise Exception(f"API returned status {response.status_code}")

        except Exception as e:
            print(f"[INFO] SchoolDigger API failed: {e}")

            # Fallback: Return manual entry link to SchoolDigger (same data source)
            schooldigger_url = f"https://www.schooldigger.com/go/{self.state.upper()}/zip/{self.zip_code}/search.aspx"

            fallback_data = {
                'school_method': 'Manual',
                'district_rating': None,
                'district_name': None,
                'elementary_avg': None,
                'elementary_name': None,
                'middle_avg': None,
                'middle_name': None,
                'high_avg': None,
                'high_name': None,
                'overall_grade': None,
                'source': 'Manual Entry - Click Link',
                'source_url': schooldigger_url,
                'notes': f'API failed: {str(e)[:50]}. Look up at SchoolDigger.'
            }

            # Cache the failure too (for 1 day) so we don't keep hitting API
            if cache_file:
                self._save_school_cache(cache_file, fallback_data)
                print(f"[CACHE] Cached API failure - will retry tomorrow")

            return fallback_data

    def _save_school_cache(self, cache_file: str, schools_data: Dict[str, Any]) -> None:
        """Save school data to cache file."""
        import os
        from datetime import datetime

        if not cache_file:
            return

        try:
            cache_data = {
                'cached_date': datetime.now().isoformat(),
                'address': self.address,
                'data': schools_data
            }
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"[CACHE] Saved school data to cache")
        except Exception as e:
            print(f"[CACHE] Could not save cache: {e}")

    def _number_to_grade(self, rating: float) -> str:
        """Convert numeric rating to letter grade."""
        if rating >= 9.5: return 'A+'
        elif rating >= 9.0: return 'A'
        elif rating >= 8.5: return 'A-'
        elif rating >= 8.0: return 'B+'
        elif rating >= 7.5: return 'B'
        elif rating >= 7.0: return 'B-'
        elif rating >= 6.5: return 'C+'
        elif rating >= 6.0: return 'C'
        elif rating >= 5.5: return 'C-'
        else: return 'D'

    def _get_crime_data(self) -> Optional[Dict[str, Any]]:
        """
        Get crime data from BestPlaces.net at ZIP-code level.

        Tries ZIP-level first (more accurate), falls back to city-level.

        Returns:
            - crime_index: BestPlaces raw index (100 = US avg, lower = safer)
            - bestplaces_score_10: Converted to 1-10 (higher = more dangerous)
            - crime_score_avg: Same as bestplaces_score_10 (for compatibility)
        """
        try:
            crime_data = {
                'crime_index': None,
                'crime_grade': None,
                'violent_crime': None,
                'property_crime': None,
                'bestplaces_score_10': None,
                'neighborhoodscout_score': None,
                'neighborhoodscout_score_10': None,
                'crime_score_avg': None,
                'source': None,
                'source_url': None,
                'notes': ''
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # State abbreviation to full name mapping
            state_names = {
                'AL': 'alabama', 'AK': 'alaska', 'AZ': 'arizona', 'AR': 'arkansas',
                'CA': 'california', 'CO': 'colorado', 'CT': 'connecticut', 'DE': 'delaware',
                'FL': 'florida', 'GA': 'georgia', 'HI': 'hawaii', 'ID': 'idaho',
                'IL': 'illinois', 'IN': 'indiana', 'IA': 'iowa', 'KS': 'kansas',
                'KY': 'kentucky', 'LA': 'louisiana', 'ME': 'maine', 'MD': 'maryland',
                'MA': 'massachusetts', 'MI': 'michigan', 'MN': 'minnesota', 'MS': 'mississippi',
                'MO': 'missouri', 'MT': 'montana', 'NE': 'nebraska', 'NV': 'nevada',
                'NH': 'new-hampshire', 'NJ': 'new-jersey', 'NM': 'new-mexico', 'NY': 'new-york',
                'NC': 'north-carolina', 'ND': 'north-dakota', 'OH': 'ohio', 'OK': 'oklahoma',
                'OR': 'oregon', 'PA': 'pennsylvania', 'RI': 'rhode-island', 'SC': 'south-carolina',
                'SD': 'south-dakota', 'TN': 'tennessee', 'TX': 'texas', 'UT': 'utah',
                'VT': 'vermont', 'VA': 'virginia', 'WA': 'washington', 'WV': 'west-virginia',
                'WI': 'wisconsin', 'WY': 'wyoming', 'DC': 'district-of-columbia'
            }

            state_full = state_names.get(self.state.upper(), self.state.lower())
            city_slug = self.city.lower().replace(' ', '-').replace('.', '')
            data_level = None

            # Try ZIP-level first (more accurate)
            try:
                zip_url = f"https://www.bestplaces.net/crime/zip-code/{state_full}/{city_slug}/{self.zip_code}"
                response = requests.get(zip_url, headers=headers, timeout=15)

                if response.status_code == 200:
                    crime_data = self._parse_bestplaces_crime(response.text, crime_data)
                    if crime_data['crime_index']:
                        data_level = 'ZIP'
                        crime_data['source_url'] = zip_url
                        print(f"[OK] BestPlaces ZIP-level ({self.zip_code}): index {crime_data['crime_index']:.1f}")
            except Exception as e:
                print(f"[INFO] ZIP-level crime lookup failed: {e}")

            # Fall back to city-level if ZIP failed
            if not crime_data['crime_index']:
                try:
                    city_slug_alt = self.city.lower().replace(' ', '_')
                    if city_slug_alt.startswith('st_'):
                        city_slug_alt = 'st._' + city_slug_alt[3:]
                    city_url = f"https://www.bestplaces.net/crime/city/{self.state.lower()}/{city_slug_alt}"
                    response = requests.get(city_url, headers=headers, timeout=15)

                    if response.status_code == 200:
                        crime_data = self._parse_bestplaces_crime(response.text, crime_data)
                        if crime_data['crime_index']:
                            data_level = 'City'
                            crime_data['source_url'] = city_url
                            print(f"[OK] BestPlaces City-level ({self.city}): index {crime_data['crime_index']:.1f}")
                except Exception as e:
                    print(f"[WARNING] City-level crime lookup failed: {e}")

            # Finalize results
            if crime_data['bestplaces_score_10'] is not None:
                crime_data['crime_score_avg'] = crime_data['bestplaces_score_10']
                crime_data['source'] = data_level  # Just "ZIP" or "City"
                crime_data['notes'] = f"{data_level}-level crime score: {crime_data['crime_score_avg']}/10 (100=US avg)"
            else:
                print(f"[INFO] Could not retrieve crime data for {self.city}, {self.state}")
                crime_data['notes'] = 'Crime data not available'

            return crime_data

        except Exception as e:
            print(f"[ERROR] Crime data failed: {e}")
            return None

    def _parse_bestplaces_crime(self, text: str, crime_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse BestPlaces crime page and extract crime indices."""
        violent_patterns = [
            r'violent crime rate in this area is (\d+\.?\d*)',  # ZIP-level format
            r'violent crime in \w+ is (\d+\.?\d*)',
            r'violent crime rate of (\d+\.?\d*)',
            r'\w+ violent crime is (\d+\.?\d*)',
        ]
        property_patterns = [
            r'property crime rate in this area is (\d+\.?\d*)',  # ZIP-level format
            r'property crime.*?rate of (\d+\.?\d*)',  # ZIP alt format: "with a rate of X"
            r'property crime in \w+ is (\d+\.?\d*)',
            r'property crime rate of (\d+\.?\d*)',
            r'\w+ property crime is (\d+\.?\d*)',
        ]

        # Patterns to extract national averages from page
        national_violent_patterns = [
            r'national average of (\d+\.?\d*).*?violent',  # "national average of 22.7" near violent
            r'violent.*?national average of (\d+\.?\d*)',  # violent ... national average of X
            r'national average.*?(\d+\.?\d*).*?violent',
        ]
        national_property_patterns = [
            r'national average of (\d+\.?\d*).*?property',
            r'property.*?national average of (\d+\.?\d*)',
            r'national average.*?(\d+\.?\d*).*?property',
        ]

        for pattern in violent_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                crime_data['violent_crime'] = float(match.group(1))
                break

        for pattern in property_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                crime_data['property_crime'] = float(match.group(1))
                break

        # Try to extract national averages from page (fallback to known values)
        us_avg_violent = 22.7  # Default fallback
        us_avg_property = 35.4  # Default fallback

        # Look for national averages in the text
        # BestPlaces uses various formats:
        # - "national average of 22.7"
        # - "US average of 35.4"
        # - "compared to 35.4"
        # - "The US average is 22.7"
        # More specific patterns first to avoid crossing sentence boundaries
        # Use [^.]{0,100} instead of .*? to limit match to within ~100 chars
        violent_avg_patterns = [
            r'violent crime[^.]{0,100}national average of (\d+\.?\d*)',
            r'violent[^.]{0,50}US average (?:of |is )(\d+\.?\d*)',
            r'violent crime is (\d+\.?\d*)[^.]*\(The US average is (\d+\.?\d*)\)',
        ]
        property_avg_patterns = [
            r'property crime[^.]{0,100}compared to (\d+\.?\d*)',  # Most specific first
            r'property crime[^.]{0,100}national average of (\d+\.?\d*)',
            r'property[^.]{0,50}US average (?:of |is )(\d+\.?\d*)',
            r'property crime is (\d+\.?\d*)[^.]*\(The US average is (\d+\.?\d*)\)',
        ]

        for pattern in violent_avg_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                # Handle patterns with multiple groups (summary format)
                us_avg_violent = float(match.group(2) if match.lastindex >= 2 else match.group(1))
                break

        for pattern in property_avg_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                us_avg_property = float(match.group(2) if match.lastindex >= 2 else match.group(1))
                break

        if crime_data['violent_crime'] and crime_data['property_crime']:
            bestplaces_index = (
                crime_data['violent_crime'] * 0.6 +
                crime_data['property_crime'] * 0.4
            )
            crime_data['crime_index'] = bestplaces_index

            # Store national averages for reference
            crime_data['us_avg_violent'] = us_avg_violent
            crime_data['us_avg_property'] = us_avg_property

            # Calculate national average index using same weighting
            us_avg_index = (us_avg_violent * 0.6) + (us_avg_property * 0.4)
            crime_data['us_avg_index'] = round(us_avg_index, 1)

            # === VALIDATION: Detect if regex extracted unreasonable values ===
            validation_warnings = []

            # Check if local values are in expected range (0-200 for BestPlaces scale)
            if crime_data['violent_crime'] > 200:
                validation_warnings.append(f"Violent crime {crime_data['violent_crime']} seems too high")
            if crime_data['property_crime'] > 200:
                validation_warnings.append(f"Property crime {crime_data['property_crime']} seems too high")

            # Check if national averages are reasonable (should be ~20-40)
            if us_avg_violent < 15 or us_avg_violent > 50:
                validation_warnings.append(f"US avg violent {us_avg_violent} outside expected range 15-50")
            if us_avg_property < 25 or us_avg_property > 60:
                validation_warnings.append(f"US avg property {us_avg_property} outside expected range 25-60")

            if validation_warnings:
                crime_data['validation_warning'] = "; ".join(validation_warnings)
                print(f"[WARNING] Crime data validation: {crime_data['validation_warning']}")

            # Scale: 5 = national average
            # Formula: (index / us_avg_index) * 5 gives us 1-10 scale where 5 = US average
            score = (bestplaces_index / us_avg_index) * 5
            crime_data['bestplaces_score_10'] = min(10, round(score, 1))

        return crime_data

    def _crime_index_to_grade(self, index: float) -> str:
        """
        Convert crime index to letter grade.
        100 = national average
        Lower is better
        """
        if index < 20: return 'A+'
        elif index < 40: return 'A'
        elif index < 60: return 'B+'
        elif index < 80: return 'B'
        elif index < 100: return 'B-'
        elif index < 120: return 'C+'
        elif index < 140: return 'C'
        elif index < 160: return 'C-'
        elif index < 180: return 'D'
        else: return 'F'

    def _get_flood_risk(self) -> Optional[Dict[str, Any]]:
        """
        Get FEMA flood zone designation.

        Using FEMA REST API
        Returns dict with:
            - flood_zone: The actual FEMA zone code (AE, X, etc.)
            - flood_risk: "Yes" or "No" for screener
            - source_url: Link to FEMA Flood Map for this address
        """
        try:
            if not self.lat or not self.lon:
                print(f"[INFO] No coordinates for flood risk lookup")
                return None

            # Build FEMA Map URL using coordinates (more accurate than address search)
            fema_map_url = f"https://hazards-fema.maps.arcgis.com/apps/webappviewer/index.html?id=8b0adb51996444d4879338b5529aa9cd&center={self.lon},{self.lat}&level=17"

            # Try FEMA Flood Hazard API
            # Endpoint: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query
            url = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
            params = {
                'geometry': f'{{"x":{self.lon},"y":{self.lat},"spatialReference":{{"wkid":4326}}}}',
                'geometryType': 'esriGeometryPoint',
                'inSR': '4326',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': 'FLD_ZONE,ZONE_SUBTY',
                'returnGeometry': 'false',
                'f': 'json'
            }

            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()

                # Check if we got flood zone data
                if data.get('features') and len(data['features']) > 0:
                    flood_zone = data['features'][0]['attributes'].get('FLD_ZONE', 'X')

                    # Determine if high risk
                    # Zones A, AE, AH, AO, AR, A99, V, VE indicate high risk
                    high_risk_zones = ['A', 'AE', 'AH', 'AO', 'AR', 'A99', 'V', 'VE']

                    if any(flood_zone.startswith(zone) for zone in high_risk_zones):
                        print(f"[OK] FEMA Flood Zone {flood_zone}: HIGH RISK")
                        return {'flood_zone': flood_zone, 'flood_risk': 'Yes', 'source_url': fema_map_url}
                    else:
                        print(f"[OK] FEMA Flood Zone {flood_zone}: LOW RISK")
                        return {'flood_zone': flood_zone, 'flood_risk': 'No', 'source_url': fema_map_url}
                else:
                    # No flood zone data = Zone X (minimal risk)
                    print(f"[INFO] No FEMA flood zone found (default: Zone X)")
                    return {'flood_zone': 'X', 'flood_risk': 'No', 'source_url': fema_map_url}
            else:
                print(f"[WARNING] FEMA API status {response.status_code}")
                return None

        except Exception as e:
            print(f"[WARNING] Flood risk lookup error: {e}")
            return None

    def _get_home_ownership(self) -> Optional[float]:
        """
        Get home ownership percentage from Census API.

        Using Census American Community Survey (ACS) 5-Year Estimates
        No API key required for basic queries
        """
        try:
            # Census API - no key required for basic queries
            url = "https://api.census.gov/data/2021/acs/acs5"
            params = {
                'get': 'B25003_002E,B25003_001E',  # Owner-occupied / Total occupied
                'for': f'zip code tabulation area:{self.zip_code}'
            }

            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()

                # Data format: [[headers], [values]]
                if len(data) >= 2:
                    owner_occupied = float(data[1][0])
                    total_occupied = float(data[1][1])

                    if total_occupied > 0:
                        ownership_pct = (owner_occupied / total_occupied) * 100
                        print(f"[OK] Home ownership: {ownership_pct:.1f}%")
                        return ownership_pct

            print(f"[INFO] Home ownership data not available for ZIP {self.zip_code}")
            return None

        except Exception as e:
            print(f"[WARNING] Home ownership lookup failed: {e}")
            return None

    def _get_walkability_score(self) -> Optional[Dict[str, Any]]:
        """
        Get walkability score from Walk Score API or scrape from public sites.

        Walk Score ranges from 0-100:
        90-100: Walker's Paradise
        70-89: Very Walkable
        50-69: Somewhat Walkable
        25-49: Car-Dependent
        0-24: Car-Dependent (Very)
        """
        try:
            if not self.lat or not self.lon:
                print(f"[INFO] No coordinates for walkability lookup")
                return None

            walkability_data = {
                'walk_score': None,
                'walk_description': None,
                'bike_score': None,
                'source': None
            }

            # Try Walk Score website scraping
            try:
                # Format address for Walk Score URL
                address_str = f"{self.address}, {self.city}, {self.state} {self.zip_code}"
                url = f"https://www.walkscore.com/score/{address_str.replace(' ', '-').replace(',', '')}"

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                response = requests.get(url, headers=headers, timeout=15)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')

                    # Look for walk score number
                    score_elem = soup.find('img', {'class': re.compile('walk.*score')})
                    if score_elem and 'alt' in score_elem.attrs:
                        alt_text = score_elem['alt']
                        score_match = re.search(r'(\d+)', alt_text)
                        if score_match:
                            walk_score = int(score_match.group(1))
                            walkability_data['walk_score'] = walk_score
                            walkability_data['walk_description'] = self._walk_score_description(walk_score)
                            walkability_data['source'] = 'Walk Score'
                            print(f"[OK] Walk Score: {walk_score} - {walkability_data['walk_description']}")

                    # Also try to get bike score
                    bike_elem = soup.find('img', {'class': re.compile('bike.*score')})
                    if bike_elem and 'alt' in bike_elem.attrs:
                        bike_match = re.search(r'(\d+)', bike_elem['alt'])
                        if bike_match:
                            walkability_data['bike_score'] = int(bike_match.group(1))

            except Exception as e:
                print(f"[WARNING] Walk Score scraping failed: {e}")

            # No fallbacks - if we can't get real Walk Score, return None
            if not walkability_data['walk_score']:
                print(f"[INFO] No walkability data found for {self.address}")
                return None

            return walkability_data

        except Exception as e:
            print(f"[ERROR] Walkability lookup failed: {e}")
            return None

    def _walk_score_description(self, score: int) -> str:
        """Convert walk score to description."""
        if score >= 90: return "Walker's Paradise"
        elif score >= 70: return "Very Walkable"
        elif score >= 50: return "Somewhat Walkable"
        elif score >= 25: return "Car-Dependent"
        else: return "Very Car-Dependent"

    def _get_transit_score(self) -> Optional[Dict[str, Any]]:
        """
        Get public transit score/accessibility.
        Estimates based on city size and known transit systems.

        Transit Score ranges from 0-100 similar to Walk Score
        """
        try:
            transit_data = {
                'transit_score': None,
                'transit_description': None,
                'source': None
            }

            # Known cities with good transit systems
            high_transit_cities = {
                'new york': 90, 'manhattan': 95, 'brooklyn': 85, 'chicago': 75,
                'san francisco': 80, 'boston': 75, 'washington': 70, 'philadelphia': 65,
                'seattle': 60, 'portland': 55, 'denver': 50, 'los angeles': 45,
                'atlanta': 45, 'miami': 45, 'minneapolis': 50, 'baltimore': 50,
                'pittsburgh': 45, 'cleveland': 40, 'st louis': 40, 'dallas': 35,
                'houston': 30, 'phoenix': 25, 'san diego': 35, 'detroit': 30,
            }

            # Check if city has known transit data
            city_lower = self.city.lower()
            for known_city, score in high_transit_cities.items():
                if known_city in city_lower or city_lower in known_city:
                    transit_data['transit_score'] = score
                    transit_data['transit_description'] = self._transit_score_description(score)
                    transit_data['source'] = 'City transit database'
                    print(f"[OK] Transit score for {self.city}: {score}")
                    return transit_data

            # No transit data for this city
            print(f"[INFO] No transit data found for {self.city}, {self.state}")
            return None

        except Exception as e:
            print(f"[ERROR] Transit lookup failed: {e}")
            return None

    def _transit_score_description(self, score: int) -> str:
        """Convert transit score to description."""
        if score >= 90: return "Excellent Transit"
        elif score >= 70: return "Good Transit"
        elif score >= 50: return "Some Transit"
        elif score >= 25: return "Minimal Transit"
        else: return "No Transit"

    def _get_nuisance_check(self) -> Optional[Dict[str, Any]]:
        """
        Check for nearby nuisance properties using OpenStreetMap/Overpass API.

        Searches for:
        - Severe: prisons, landfills, waste facilities
        - Industrial: factories, industrial areas
        - Moderate: motels, self-storage, liquor stores, pawn shops, nightclubs
        - Minor: gas stations

        Returns dict with score (1-10) and list of found nuisances.
        Includes retry logic for API timeouts.
        """
        import time

        if not self.lat or not self.lon:
            print(f"[INFO] No coordinates for nuisance check")
            return None

        checker = NuisanceChecker()
        max_retries = 3

        for attempt in range(max_retries):
            try:
                result = checker.check_nuisances(self.lat, self.lon)

                if result.get('error'):
                    if attempt < max_retries - 1:
                        print(f"[WARN] Nuisance check error (attempt {attempt+1}): {result['error']} - retrying...")
                        time.sleep(2)
                        continue
                    else:
                        print(f"[WARN] Nuisance check failed after {max_retries} attempts: {result['error']}")
                        return result

                score = result.get('final_score', 10)
                print(f"[OK] Nuisance check: {score}/10 - {result.get('notes', 'No issues')}")
                return result

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[WARN] Nuisance check exception (attempt {attempt+1}): {e} - retrying...")
                    time.sleep(2)
                    continue
                else:
                    print(f"[WARN] Nuisance check failed after {max_retries} attempts: {e}")
                    return {'error': str(e), 'notes': f'Nuisance check failed: {str(e)[:50]}'}

        return {'error': 'Max retries exceeded', 'notes': 'Nuisance API unavailable'}

    def _get_climate_risk_check(self) -> Optional[Dict[str, Any]]:
        """
        Check climate risks using FEMA flood zone and USDA wildfire data.

        Uses free government APIs:
        - FEMA NFHL for flood zones
        - USDA Forest Service for wildfire burn probability

        Returns dict with flood zone, fire risk, and combined score.
        """
        import time

        if not self.lat or not self.lon:
            print(f"[INFO] No coordinates for climate risk check")
            return None

        checker = ClimateRiskChecker()
        max_retries = 2

        for attempt in range(max_retries):
            try:
                result = checker.check_climate_risk(self.lat, self.lon)

                if result.get('error'):
                    if attempt < max_retries - 1:
                        print(f"[WARN] Climate risk error (attempt {attempt+1}): {result['error']} - retrying...")
                        time.sleep(2)
                        continue
                    else:
                        print(f"[WARN] Climate risk check incomplete: {result['error']}")
                        # Return partial result even with errors
                        return result

                score = result.get('final_score')
                flood_zone = result.get('flood_zone', 'Unknown')
                print(f"[OK] Climate risk: {score}/10 - Flood Zone {flood_zone}")
                return result

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[WARN] Climate risk exception (attempt {attempt+1}): {e} - retrying...")
                    time.sleep(2)
                    continue
                else:
                    print(f"[WARN] Climate risk check failed: {e}")
                    return {'error': str(e), 'notes': f'Climate check failed: {str(e)[:50]}'}

        return {'error': 'Max retries exceeded', 'notes': 'Climate API unavailable'}

    def _get_employer_stability_check(self) -> Optional[Dict[str, Any]]:
        """
        Check employer stability / recession resistance using BLS QCEW data.

        Uses free BLS Quarterly Census of Employment and Wages API.
        Analyzes county employment mix to determine recession resistance.

        Returns dict with employment breakdown and stability score.
        """
        import time

        if not self.lat or not self.lon:
            print(f"[INFO] No coordinates for employer stability check")
            return None

        checker = EmployerStabilityChecker()
        max_retries = 2

        for attempt in range(max_retries):
            try:
                result = checker.check_employer_stability(self.lat, self.lon)

                if result.get('error'):
                    if attempt < max_retries - 1:
                        print(f"[WARN] Employer stability error (attempt {attempt+1}): {result['error']} - retrying...")
                        time.sleep(2)
                        continue
                    else:
                        print(f"[WARN] Employer stability check incomplete: {result['error']}")
                        return result

                score = result.get('final_score')
                county = result.get('county_name', 'Unknown')
                rri = result.get('rri', 0)
                print(f"[OK] Employer stability: {score}/10 - {county} (RRI: {rri})")
                return result

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[WARN] Employer stability exception (attempt {attempt+1}): {e} - retrying...")
                    time.sleep(2)
                    continue
                else:
                    print(f"[WARN] Employer stability check failed: {e}")
                    return {'error': str(e), 'notes': f'Employer stability check failed: {str(e)[:50]}'}

        return {'error': 'Max retries exceeded', 'notes': 'BLS API unavailable'}

    def get_summary(self) -> str:
        """Get summary of scraped data."""
        summary = ["=== WEB SCRAPED DATA ===\n"]

        for key, value in self.scraped_data.items():
            summary.append(f"{key}: {value}")

        return "\n".join(summary)


if __name__ == "__main__":
    # Test scraper
    demo_scraper = DemographicScraper(
        address="15528 W 133rd St",
        city="Olathe",
        state="KS",
        zip_code="66062"
    )

    print("Testing web scrapers...")
    print("="*80)

    data = demo_scraper.scrape_all()
    print("\n" + demo_scraper.get_summary())
