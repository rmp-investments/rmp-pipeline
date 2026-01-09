"""
Employer Stability / Recession Resistance Checker

Uses BLS Quarterly Census of Employment and Wages (QCEW) data to assess
how recession-resistant a county's employment base is.

Scoring based on:
1. % of employment in recession-resistant industries (healthcare, education, govt)
2. % in essential services (retail, transport)
3. % in cyclical industries (construction, manufacturing, hospitality)
4. Industry diversification (concentration risk)

Free API, no key required.
"""
import requests
import time
from typing import Dict, Any, Optional, Tuple
from io import StringIO
import csv


class EmployerStabilityChecker:
    """Checks employer stability using BLS QCEW employment data."""

    # BLS QCEW Open Data API
    QCEW_URL = 'https://data.bls.gov/cew/data/api/{year}/{qtr}/area/{fips}.csv'

    # FCC API for reverse geocoding (lat/lon to county FIPS)
    FCC_URL = 'https://geo.fcc.gov/api/census/area'

    # Industry classification by recession resistance
    # NAICS 2-digit codes
    RECESSION_PROOF = {
        '62': 'Healthcare & Social Assistance',
        '61': 'Educational Services',
        '22': 'Utilities',
    }

    ESSENTIAL = {
        '44-45': 'Retail Trade',
        '48-49': 'Transportation & Warehousing',
        '42': 'Wholesale Trade',
    }

    MODERATE = {
        '52': 'Finance & Insurance',
        '54': 'Professional & Technical Services',
        '55': 'Management of Companies',
        '51': 'Information',
        '56': 'Administrative & Support Services',
    }

    CYCLICAL = {
        '23': 'Construction',
        '31-33': 'Manufacturing',
        '72': 'Accommodation & Food Services',
        '71': 'Arts, Entertainment & Recreation',
        '21': 'Mining, Oil & Gas',
        '53': 'Real Estate',
    }

    # Scoring thresholds for Recession Resistance Index (RRI)
    # RRI = stable% + 0.6*essential% + 0.3*moderate% - 0.4*cyclical%
    SCORE_THRESHOLDS = [
        (45, 10),  # RRI >= 45
        (40, 9),
        (35, 8),
        (30, 7),
        (25, 6),
        (20, 5),
        (15, 4),
        (10, 3),
        (5, 2),
        (0, 1),
    ]

    def __init__(self):
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self._fips_cache = {}

    def _rate_limit(self):
        """Ensure we don't hit APIs too fast."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _get_county_fips(self, lat: float, lon: float) -> Optional[str]:
        """
        Convert lat/lon to county FIPS code using FCC API.
        Returns 5-digit FIPS (state + county).
        """
        cache_key = f"{lat:.4f},{lon:.4f}"
        if cache_key in self._fips_cache:
            return self._fips_cache[cache_key]

        try:
            self._rate_limit()
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json'
            }
            response = requests.get(self.FCC_URL, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if results:
                    # Get county FIPS from first result
                    fips = results[0].get('county_fips')
                    county_name = results[0].get('county_name', 'Unknown')
                    state = results[0].get('state_code', '')

                    if fips:
                        self._fips_cache[cache_key] = (fips, county_name, state)
                        return fips, county_name, state

            return None, None, None

        except Exception as e:
            print(f"Error getting FIPS: {e}")
            return None, None, None

    def _get_qcew_data(self, fips: str, year: int = 2024, qtr: int = 1) -> Optional[Dict]:
        """
        Fetch QCEW employment data for a county.
        Returns parsed employment by industry.
        """
        try:
            self._rate_limit()
            url = self.QCEW_URL.format(year=year, qtr=qtr, fips=fips)
            response = requests.get(url, timeout=30)

            if response.status_code != 200:
                # Try previous year if current not available
                if year == 2024:
                    return self._get_qcew_data(fips, year=2023, qtr=3)
                return None

            # Parse CSV
            reader = csv.DictReader(StringIO(response.text))
            rows = list(reader)

            return self._parse_employment_data(rows)

        except Exception as e:
            print(f"Error fetching QCEW data: {e}")
            return None

    def _parse_employment_data(self, rows: list) -> Dict:
        """
        Parse QCEW CSV data into employment breakdown.
        """
        result = {
            'total_employment': 0,
            'government': 0,
            'by_industry': {},
            'recession_proof': 0,
            'essential': 0,
            'moderate': 0,
            'cyclical': 0,
            'other': 0,
        }

        for row in rows:
            own_code = row.get('own_code', '')
            industry_code = row.get('industry_code', '')
            agglvl_code = row.get('agglvl_code', '')

            try:
                emp = int(row.get('month3_emplvl', 0) or 0)
            except (ValueError, TypeError):
                emp = 0

            # Total employment (all ownership, all industries)
            if own_code == '0' and industry_code == '10' and agglvl_code == '70':
                result['total_employment'] = emp

            # Government employment (federal + state + local)
            if own_code in ['1', '2', '3'] and industry_code == '10':
                result['government'] += emp

            # Private sector by 2-digit NAICS (agglvl_code 74)
            if own_code == '5' and agglvl_code == '74':
                result['by_industry'][industry_code] = emp

                if industry_code in self.RECESSION_PROOF:
                    result['recession_proof'] += emp
                elif industry_code in self.ESSENTIAL:
                    result['essential'] += emp
                elif industry_code in self.MODERATE:
                    result['moderate'] += emp
                elif industry_code in self.CYCLICAL:
                    result['cyclical'] += emp
                else:
                    result['other'] += emp

        return result

    def _calculate_score(self, emp_data: Dict) -> Tuple[float, float, str]:
        """
        Calculate recession resistance score from employment data.

        Returns (score, rri, explanation)
        """
        total = emp_data['total_employment']
        if total == 0:
            return 5, 0, "No employment data"

        # Calculate percentages
        govt_pct = (emp_data['government'] / total) * 100
        recession_pct = (emp_data['recession_proof'] / total) * 100
        essential_pct = (emp_data['essential'] / total) * 100
        moderate_pct = (emp_data['moderate'] / total) * 100
        cyclical_pct = (emp_data['cyclical'] / total) * 100

        # Stable = government + recession-proof industries
        stable_pct = govt_pct + recession_pct

        # Calculate Recession Resistance Index (RRI)
        # Weights: stable=1.0, essential=0.6, moderate=0.3, cyclical=-0.4
        rri = (
            stable_pct * 1.0 +
            essential_pct * 0.6 +
            moderate_pct * 0.3 -
            cyclical_pct * 0.4
        )

        # Map RRI to 1-10 score
        score = 1
        for threshold, s in self.SCORE_THRESHOLDS:
            if rri >= threshold:
                score = s
                break

        # Build explanation
        explanation = (
            f"Stable: {stable_pct:.1f}% (Govt {govt_pct:.1f}% + Healthcare/Ed {recession_pct:.1f}%), "
            f"Essential: {essential_pct:.1f}%, "
            f"Cyclical: {cyclical_pct:.1f}%"
        )

        return score, round(rri, 1), explanation

    def _calculate_concentration_risk(self, emp_data: Dict) -> Tuple[float, str]:
        """
        Calculate industry concentration using simplified HHI.
        High concentration = risk if that industry crashes.

        Returns (adjustment, explanation)
        """
        total = emp_data['total_employment']
        if total == 0:
            return 0, "No data"

        # Calculate market share for each major industry
        industries = emp_data['by_industry']

        # Find largest industry
        if not industries:
            return 0, "No industry data"

        largest_industry = max(industries.items(), key=lambda x: x[1])
        largest_code, largest_emp = largest_industry
        largest_pct = (largest_emp / total) * 100

        # Get industry name
        all_industries = {**self.RECESSION_PROOF, **self.ESSENTIAL,
                         **self.MODERATE, **self.CYCLICAL}
        largest_name = all_industries.get(largest_code, largest_code)

        # Concentration adjustment
        # >25% in one industry = concerning
        # >35% = significant risk
        if largest_pct >= 35:
            adj = -1.5
            note = f"HIGH concentration: {largest_pct:.0f}% in {largest_name}"
        elif largest_pct >= 25:
            adj = -0.5
            note = f"Moderate concentration: {largest_pct:.0f}% in {largest_name}"
        else:
            adj = 0
            note = f"Diversified (largest: {largest_pct:.0f}% {largest_name})"

        return adj, note

    def check_employer_stability(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Check employer stability / recession resistance for a location.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict with stability analysis and score
        """
        result = {
            'latitude': lat,
            'longitude': lon,
            'county_fips': None,
            'county_name': None,
            'state': None,
            'total_employment': None,
            'government_pct': None,
            'recession_proof_pct': None,
            'essential_pct': None,
            'moderate_pct': None,
            'cyclical_pct': None,
            'rri': None,  # Recession Resistance Index
            'concentration_adj': None,
            'base_score': None,
            'final_score': None,
            'notes': None,
            'error': None,
        }

        if not lat or not lon:
            result['error'] = 'Missing coordinates'
            result['notes'] = 'No coordinates available'
            return result

        # Step 1: Get county FIPS from coordinates
        fips_result = self._get_county_fips(lat, lon)
        if not fips_result[0]:
            result['error'] = 'Could not determine county'
            result['notes'] = 'Failed to geocode to county FIPS'
            return result

        fips, county_name, state = fips_result
        result['county_fips'] = fips
        result['county_name'] = county_name
        result['state'] = state

        # Step 2: Get QCEW employment data
        emp_data = self._get_qcew_data(fips)
        if not emp_data or emp_data['total_employment'] == 0:
            result['error'] = 'No employment data available'
            result['notes'] = f'No BLS data for {county_name}, {state}'
            return result

        total = emp_data['total_employment']
        result['total_employment'] = total

        # Calculate percentages
        result['government_pct'] = round((emp_data['government'] / total) * 100, 1)
        result['recession_proof_pct'] = round((emp_data['recession_proof'] / total) * 100, 1)
        result['essential_pct'] = round((emp_data['essential'] / total) * 100, 1)
        result['moderate_pct'] = round((emp_data['moderate'] / total) * 100, 1)
        result['cyclical_pct'] = round((emp_data['cyclical'] / total) * 100, 1)

        # Step 3: Calculate base score
        base_score, rri, score_explanation = self._calculate_score(emp_data)
        result['rri'] = rri
        result['base_score'] = base_score

        # Step 4: Apply concentration adjustment
        conc_adj, conc_note = self._calculate_concentration_risk(emp_data)
        result['concentration_adj'] = conc_adj

        # Final score (bounded 1-10)
        final_score = max(1, min(10, base_score + conc_adj))
        result['final_score'] = round(final_score, 1)

        # Build notes
        result['notes'] = f"{score_explanation} | {conc_note}"

        return result


def test_employer_stability():
    """Test with various locations."""
    checker = EmployerStabilityChecker()

    test_locations = [
        (38.9097, -94.8194, 'Fieldstone - Olathe, KS (suburban)'),
        (39.0553, -94.4867, 'North Oak Crossing - Kansas City, MO'),
        (29.7604, -95.3698, 'Houston, TX (oil/energy)'),
        (42.3314, -83.0458, 'Detroit, MI (manufacturing)'),
        (36.1627, -86.7816, 'Nashville, TN (healthcare hub)'),
        (33.7490, -84.3880, 'Atlanta, GA (diverse)'),
        (39.7392, -104.9903, 'Denver, CO'),
    ]

    for lat, lon, name in test_locations:
        print(f'\n{"="*60}')
        print(f'{name}')
        print(f'{"="*60}')

        result = checker.check_employer_stability(lat, lon)

        if result['error']:
            print(f"Error: {result['error']}")
            continue

        print(f"County: {result['county_name']}, {result['state']} (FIPS: {result['county_fips']})")
        print(f"Total Employment: {result['total_employment']:,}")
        print(f"\nEmployment Mix:")
        print(f"  Government: {result['government_pct']}%")
        print(f"  Recession-Proof (Healthcare/Ed/Utilities): {result['recession_proof_pct']}%")
        print(f"  Essential (Retail/Transport): {result['essential_pct']}%")
        print(f"  Cyclical (Construction/Mfg/Hospitality): {result['cyclical_pct']}%")
        print(f"\nRecession Resistance Index: {result['rri']}")
        print(f"Base Score: {result['base_score']}/10")
        print(f"Concentration Adjustment: {result['concentration_adj']}")
        print(f"FINAL SCORE: {result['final_score']}/10")
        print(f"\nNotes: {result['notes']}")


if __name__ == '__main__':
    test_employer_stability()
