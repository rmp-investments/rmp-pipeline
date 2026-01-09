"""
Climate Risk Checker - Uses free government APIs for climate/hazard risk assessment
- FEMA National Flood Hazard Layer for flood zones
- USDA Forest Service for wildfire burn probability
- Open-Meteo Climate API for heat/cold extreme days

No API keys required.

Weighting (logical for real estate):
- Flood: 50% - Most critical (insurance requirements, property value impact)
- Fire: 20% - Regional catastrophic risk
- Heat: 15% - Extreme heat days affect A/C costs, tenant comfort
- Cold: 15% - Extreme cold days affect heating costs, pipes, snow removal
"""
import requests
import time
from typing import Dict, Any, Optional


class ClimateRiskChecker:
    """Checks climate and natural hazard risks using free government APIs."""

    # FEMA NFHL flood zone API
    FEMA_FLOOD_URL = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query'

    # USDA Forest Service wildfire risk
    USDA_FIRE_URL = 'https://apps.fs.usda.gov/arcx/rest/services/RDW_Wildfire/ProbabilisticWildfireRisk/MapServer/identify'

    # Flood zone risk mapping (higher = worse)
    FLOOD_ZONE_SCORES = {
        # High-risk coastal (storm surge)
        'V': 1, 'VE': 1, 'V1-30': 1,
        # High-risk areas (100-year flood)
        'A': 2, 'AE': 2, 'AH': 2, 'AO': 2, 'AR': 3, 'A99': 3, 'A1-30': 2,
        # Moderate risk (500-year flood)
        'X PROTECTED BY LEVEE': 5,
        '0.2 PCT ANNUAL CHANCE FLOOD HAZARD': 6,
        # Minimal risk
        'X': 10, 'AREA OF MINIMAL FLOOD HAZARD': 10,
        # Undetermined
        'D': 5,
    }

    # Burn probability thresholds (probability -> score)
    # Burn probability is typically 0 to 0.05 (5%) for high-risk areas
    FIRE_SCORE_THRESHOLDS = [
        (0.0001, 10),   # < 0.01% - Very low risk
        (0.001, 9),     # < 0.1%
        (0.005, 7),     # < 0.5%
        (0.01, 5),      # < 1%
        (0.02, 3),      # < 2%
        (0.05, 2),      # < 5%
        (1.0, 1),       # >= 5% - Very high risk
    ]

    # Open-Meteo Climate API for heat/cold days
    OPEN_METEO_CLIMATE_URL = 'https://climate-api.open-meteo.com/v1/climate'

    # Heat days scoring (days >90F/32C per year) - higher days = worse
    HEAT_SCORE_THRESHOLDS = [
        (10, 10),    # 0-10 days - Minimal heat (Pacific NW, northern states)
        (20, 9),     # 11-20 days
        (30, 8),     # 21-30 days - Moderate (Midwest)
        (45, 7),     # 31-45 days
        (60, 6),     # 46-60 days - Warm climate
        (80, 5),     # 61-80 days
        (100, 4),    # 81-100 days - Hot climate (Texas)
        (120, 3),    # 101-120 days
        (150, 2),    # 121-150 days - Very hot (Phoenix suburbs)
        (365, 1),    # >150 days - Extreme heat
    ]

    # Cold days scoring (days <32F/0C per year) - higher days = worse
    COLD_SCORE_THRESHOLDS = [
        (15, 10),    # 0-15 days - Minimal cold (SoCal, Florida)
        (30, 9),     # 16-30 days
        (50, 8),     # 31-50 days - Mild winters
        (70, 7),     # 51-70 days
        (90, 6),     # 71-90 days - Moderate cold (Kansas/Missouri)
        (110, 5),    # 91-110 days
        (130, 4),    # 111-130 days - Cold winters (Chicago)
        (150, 3),    # 131-150 days
        (180, 2),    # 151-180 days - Harsh winters (Minnesota)
        (365, 1),    # >180 days - Extreme cold
    ]

    # Component weights for final score
    WEIGHTS = {
        'flood': 0.50,  # Most critical - insurance/value
        'fire': 0.20,   # Catastrophic risk
        'heat': 0.15,   # Operational cost
        'cold': 0.15,   # Operational cost
    }

    def __init__(self):
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Rate limiting

    def _rate_limit(self):
        """Ensure we don't hit APIs too fast."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _get_flood_zone(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Query FEMA NFHL for flood zone at coordinates.
        Returns flood zone code and description.
        """
        result = {
            'zone': None,
            'zone_subtype': None,
            'is_sfha': None,  # Special Flood Hazard Area
            'score': None,
            'error': None
        }

        try:
            self._rate_limit()
            params = {
                'where': '1=1',
                'geometry': f'{lon},{lat}',
                'geometryType': 'esriGeometryPoint',
                'inSR': '4326',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': 'FLD_ZONE,ZONE_SUBTY,SFHA_TF',
                'returnGeometry': 'false',
                'f': 'json'
            }

            response = requests.get(self.FEMA_FLOOD_URL, params=params, timeout=30)

            if response.status_code != 200:
                result['error'] = f'API error: {response.status_code}'
                return result

            data = response.json()

            if 'error' in data:
                result['error'] = data['error'].get('message', 'Unknown API error')
                return result

            features = data.get('features', [])
            if not features:
                result['zone'] = 'NOT MAPPED'
                result['zone_subtype'] = 'Area not in FEMA flood maps'
                result['score'] = 8  # Assume low risk if not mapped
                return result

            # Get first feature (most relevant)
            attrs = features[0].get('attributes', {})
            zone = attrs.get('FLD_ZONE', '')
            zone_subtype = attrs.get('ZONE_SUBTY', '')
            sfha = attrs.get('SFHA_TF', '')

            result['zone'] = zone
            result['zone_subtype'] = zone_subtype
            result['is_sfha'] = sfha == 'T'

            # Calculate score
            # Try zone first, then subtype
            score = self.FLOOD_ZONE_SCORES.get(zone)
            if score is None:
                score = self.FLOOD_ZONE_SCORES.get(zone_subtype, 5)
            result['score'] = score

        except requests.exceptions.Timeout:
            result['error'] = 'API timeout'
        except Exception as e:
            result['error'] = str(e)[:100]

        return result

    def _get_wildfire_risk(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Query USDA Forest Service for wildfire burn probability.
        Returns burn probability and derived score.
        """
        result = {
            'burn_probability': None,
            'score': None,
            'error': None
        }

        try:
            self._rate_limit()
            params = {
                'geometry': f'{lon},{lat}',
                'geometryType': 'esriGeometryPoint',
                'sr': '4326',
                'layers': 'all:1',  # Layer 1 = Burn Probability
                'tolerance': '1',
                'mapExtent': f'{lon-1},{lat-1},{lon+1},{lat+1}',
                'imageDisplay': '100,100,96',
                'returnGeometry': 'false',
                'f': 'json'
            }

            response = requests.get(self.USDA_FIRE_URL, params=params, timeout=30)

            if response.status_code != 200:
                result['error'] = f'API error: {response.status_code}'
                return result

            data = response.json()
            results = data.get('results', [])

            if not results:
                result['burn_probability'] = 0
                result['score'] = 10  # No data = assume very low risk
                return result

            # Get burn probability value
            for r in results:
                if r.get('layerName') == 'Burn Probability':
                    attrs = r.get('attributes', {})
                    bp_str = attrs.get('Classify.Pixel Value', '0')
                    try:
                        result['burn_probability'] = float(bp_str)
                    except ValueError:
                        result['burn_probability'] = 0

            # Calculate score based on burn probability
            bp = result['burn_probability'] or 0
            result['score'] = 10  # Default to best
            for threshold, score in self.FIRE_SCORE_THRESHOLDS:
                if bp < threshold:
                    result['score'] = score
                    break
            else:
                result['score'] = 1  # Very high risk

        except requests.exceptions.Timeout:
            result['error'] = 'API timeout'
        except Exception as e:
            result['error'] = str(e)[:100]

        return result

    def _get_heat_cold_risk(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Query Open-Meteo Climate API for extreme temperature days.
        Uses 3-year average (2020-2022) for stable climate normals.

        Returns:
            - hot_days: Annual days with max temp >32C (90F)
            - cold_days: Annual days with min temp <0C (32F)
            - heat_score: 1-10 score (10=minimal heat)
            - cold_score: 1-10 score (10=minimal cold)
        """
        result = {
            'hot_days': None,
            'cold_days': None,
            'heat_score': None,
            'cold_score': None,
            'error': None
        }

        try:
            self._rate_limit()

            # Query 3 years of climate data for averaging
            params = {
                'latitude': lat,
                'longitude': lon,
                'start_date': '2020-01-01',
                'end_date': '2022-12-31',
                'models': 'EC_Earth3P_HR',  # High-resolution model
                'daily': 'temperature_2m_max,temperature_2m_min'
            }

            response = requests.get(self.OPEN_METEO_CLIMATE_URL, params=params, timeout=30)

            if response.status_code != 200:
                result['error'] = f'API error: {response.status_code}'
                return result

            data = response.json()
            daily = data.get('daily', {})
            tmax = daily.get('temperature_2m_max', [])
            tmin = daily.get('temperature_2m_min', [])

            if not tmax or not tmin:
                result['error'] = 'No temperature data returned'
                return result

            # Count hot days (>32C = 90F) and cold days (<0C = 32F)
            hot_count = sum(1 for t in tmax if t is not None and t > 32)
            cold_count = sum(1 for t in tmin if t is not None and t < 0)

            # Average per year (3 years of data)
            years = 3
            result['hot_days'] = round(hot_count / years)
            result['cold_days'] = round(cold_count / years)

            # Calculate heat score
            for threshold, score in self.HEAT_SCORE_THRESHOLDS:
                if result['hot_days'] <= threshold:
                    result['heat_score'] = score
                    break
            else:
                result['heat_score'] = 1

            # Calculate cold score
            for threshold, score in self.COLD_SCORE_THRESHOLDS:
                if result['cold_days'] <= threshold:
                    result['cold_score'] = score
                    break
            else:
                result['cold_score'] = 1

        except requests.exceptions.Timeout:
            result['error'] = 'API timeout'
        except Exception as e:
            result['error'] = str(e)[:100]

        return result

    def check_climate_risk(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Check all climate risks for a location.

        Returns dict with flood, fire, heat, cold risks and weighted combined score.
        Weights: Flood 50%, Fire 20%, Heat 15%, Cold 15%
        """
        result = {
            'latitude': lat,
            'longitude': lon,
            'source': 'FEMA + USDA + Open-Meteo',

            # Flood data
            'flood_zone': None,
            'flood_zone_desc': None,
            'flood_is_sfha': None,
            'flood_score': None,

            # Fire data
            'fire_burn_probability': None,
            'fire_score': None,

            # Heat data
            'heat_days': None,
            'heat_score': None,

            # Cold data
            'cold_days': None,
            'cold_score': None,

            # Combined
            'final_score': None,
            'notes': None,
            'error': None
        }

        if not lat or not lon:
            result['error'] = 'Missing coordinates'
            result['notes'] = 'No coordinates available'
            return result

        errors = []

        # Get flood zone data (with retry)
        flood_data = None
        for attempt in range(3):
            flood_data = self._get_flood_zone(lat, lon)
            if not flood_data.get('error'):
                break
            time.sleep(2)

        if flood_data:
            result['flood_zone'] = flood_data.get('zone')
            result['flood_zone_desc'] = flood_data.get('zone_subtype')
            result['flood_is_sfha'] = flood_data.get('is_sfha')
            result['flood_score'] = flood_data.get('score')
            if flood_data.get('error'):
                errors.append(f"Flood: {flood_data['error']}")

        # Get wildfire risk (with retry)
        fire_data = None
        for attempt in range(3):
            fire_data = self._get_wildfire_risk(lat, lon)
            if not fire_data.get('error'):
                break
            time.sleep(2)

        if fire_data:
            result['fire_burn_probability'] = fire_data.get('burn_probability')
            result['fire_score'] = fire_data.get('score')
            if fire_data.get('error'):
                errors.append(f"Fire: {fire_data['error']}")

        # Get heat/cold risk (with retry)
        heat_cold_data = None
        for attempt in range(2):
            heat_cold_data = self._get_heat_cold_risk(lat, lon)
            if not heat_cold_data.get('error'):
                break
            time.sleep(2)

        if heat_cold_data:
            result['heat_days'] = heat_cold_data.get('hot_days')
            result['heat_score'] = heat_cold_data.get('heat_score')
            result['cold_days'] = heat_cold_data.get('cold_days')
            result['cold_score'] = heat_cold_data.get('cold_score')
            if heat_cold_data.get('error'):
                errors.append(f"Heat/Cold: {heat_cold_data['error']}")

        # Calculate weighted combined score
        # Flood: 50%, Fire: 20%, Heat: 15%, Cold: 15%
        scores = {}
        if result['flood_score'] is not None:
            scores['flood'] = result['flood_score']
        if result['fire_score'] is not None:
            scores['fire'] = result['fire_score']
        if result['heat_score'] is not None:
            scores['heat'] = result['heat_score']
        if result['cold_score'] is not None:
            scores['cold'] = result['cold_score']

        if scores:
            # Calculate weighted average with available scores
            total_weight = sum(self.WEIGHTS[k] for k in scores.keys())
            weighted_sum = sum(scores[k] * self.WEIGHTS[k] for k in scores.keys())
            # Normalize if not all scores available
            combined = weighted_sum / total_weight if total_weight > 0 else 5
            result['final_score'] = round(combined * 2) / 2  # Round to nearest 0.5

        # Build notes
        notes = []
        if result['flood_zone']:
            sfha_note = " (SFHA)" if result['flood_is_sfha'] else ""
            notes.append(f"Flood: Zone {result['flood_zone']}{sfha_note} ({result['flood_score']})")
        if result['fire_burn_probability'] is not None:
            bp_pct = result['fire_burn_probability'] * 100
            notes.append(f"Fire: {bp_pct:.2f}% ({result['fire_score']})")
        if result['heat_days'] is not None:
            notes.append(f"Heat: {result['heat_days']} days>90F ({result['heat_score']})")
        if result['cold_days'] is not None:
            notes.append(f"Cold: {result['cold_days']} days<32F ({result['cold_score']})")

        if errors:
            notes.extend(errors)

        result['notes'] = ' | '.join(notes) if notes else 'Unable to retrieve data'
        result['error'] = '; '.join(errors) if errors else None

        return result


def test_climate_risk():
    """Test the climate risk checker with various locations."""
    checker = ClimateRiskChecker()

    test_locations = [
        (38.9097, -94.8194, 'Fieldstone (Olathe, KS) - Suburban'),
        (39.0553, -94.4867, 'North Oak Crossing (Independence, MO)'),
        (33.4484, -112.0740, 'Phoenix, AZ - Extreme heat'),
        (44.9778, -93.2650, 'Minneapolis, MN - Extreme cold'),
        (29.7604, -95.3698, 'Houston, TX - Flood/heat risk'),
        (25.7617, -80.1918, 'Miami, FL - Coastal flood risk'),
    ]

    for lat, lon, name in test_locations:
        print(f'\n{"="*70}')
        print(f'{name}')
        print(f'{"="*70}')
        result = checker.check_climate_risk(lat, lon)
        print(f"FINAL SCORE: {result['final_score']}/10")
        print(f"")
        print(f"Flood: Zone {result['flood_zone']} - Score {result['flood_score']}/10 (50% weight)")
        print(f"Fire:  {result['fire_burn_probability']*100 if result['fire_burn_probability'] else 0:.3f}% burn prob - Score {result['fire_score']}/10 (20% weight)")
        print(f"Heat:  {result['heat_days']} days >90F/yr - Score {result['heat_score']}/10 (15% weight)")
        print(f"Cold:  {result['cold_days']} days <32F/yr - Score {result['cold_score']}/10 (15% weight)")
        print(f"")
        print(f"Notes: {result['notes']}")
        if result['error']:
            print(f"Errors: {result['error']}")


if __name__ == '__main__':
    test_climate_risk()
