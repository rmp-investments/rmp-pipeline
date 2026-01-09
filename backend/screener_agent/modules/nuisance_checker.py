"""
Nearby Nuisance Checker - Uses OpenStreetMap/Overpass API to detect nuisances
Free API, no key required

Tiered search by nuisance type (based on actual impact):
- Landfill/Prison: 1 mile (smell travels, major stigma)
- Waste Transfer Station: 0.5 mile (truck traffic, brief odor)
- Industrial: 0.5 mile (noise/trucks if visible/audible)
- Motel/Shelter: 0.25 mile (neighborhood character)
- Storage/Pawn/Liquor: 0.25 mile (neighborhood character)
- Gas Station/Auto: 500ft (only if adjacent)
"""
import requests
import time
from typing import Dict, Any, List, Tuple


class NuisanceChecker:
    """Checks for nearby nuisance properties using OpenStreetMap data."""

    OVERPASS_URL = 'https://overpass-api.de/api/interpreter'

    # Search radii in meters (tiered by actual impact)
    RADII = {
        'landfill': 1609,           # 1 mile - smell travels
        'prison': 1609,             # 1 mile - major stigma
        'waste_transfer': 800,      # 0.5 mile - truck traffic
        'industrial': 800,          # 0.5 mile - noise if visible
        'motel_shelter': 400,       # 0.25 mile - neighborhood feel
        'vice': 400,                # 0.25 mile - pawn/liquor/etc
        'minor': 150,               # 500 ft - gas station/auto
    }

    # Deductions by type (edit these in Excel for fine-tuning)
    DEDUCTIONS = {
        'landfill': -4,
        'prison': -4,
        'waste_transfer': -3,
        'industrial': -2,
        'motel_shelter': -1.5,
        'vice': -1,
        'minor': -0.5,
    }

    # Category mapping for Excel output
    CATEGORY_MAP = {
        'landfill': 'severe',
        'prison': 'severe',
        'waste_transfer': 'industrial',
        'industrial': 'industrial',
        'motel_shelter': 'moderate',
        'vice': 'moderate',
        'minor': 'minor',
    }

    def __init__(self):
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Rate limiting

    def _rate_limit(self):
        """Ensure we don't hit API too fast."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _build_query(self, lat: float, lon: float) -> str:
        """
        Build Overpass QL query with appropriate radius for each nuisance type.
        """
        r_landfill = self.RADII['landfill']
        r_prison = self.RADII['prison']
        r_waste = self.RADII['waste_transfer']
        r_industrial = self.RADII['industrial']
        r_motel = self.RADII['motel_shelter']
        r_vice = self.RADII['vice']
        r_minor = self.RADII['minor']

        return f'''
[out:json][timeout:30];
(
  // === LANDFILL (1 mile) - Smell travels ===
  nwr["landuse"="landfill"](around:{r_landfill},{lat},{lon});

  // === PRISON (1 mile) - Major stigma ===
  nwr["amenity"="prison"](around:{r_prison},{lat},{lon});

  // === WASTE TRANSFER (0.5 mile) - Truck traffic ===
  nwr["amenity"="waste_transfer_station"](around:{r_waste},{lat},{lon});

  // === INDUSTRIAL (0.5 mile) - Noise if visible ===
  nwr["landuse"="industrial"](around:{r_industrial},{lat},{lon});
  nwr["man_made"="works"](around:{r_industrial},{lat},{lon});

  // === MOTEL/SHELTER (0.25 mile) - Neighborhood feel ===
  nwr["tourism"="motel"](around:{r_motel},{lat},{lon});
  nwr["tourism"="hostel"](around:{r_motel},{lat},{lon});
  nwr["social_facility"="shelter"](around:{r_motel},{lat},{lon});
  nwr["amenity"="shelter"]["shelter_type"="homeless"](around:{r_motel},{lat},{lon});
  nwr["healthcare"="drug_rehabilitation"](around:{r_motel},{lat},{lon});

  // === VICE (0.25 mile) - Neighborhood character ===
  nwr["amenity"="storage_rental"](around:{r_vice},{lat},{lon});
  nwr["shop"="storage_rental"](around:{r_vice},{lat},{lon});
  nwr["building"="storage"](around:{r_vice},{lat},{lon});
  nwr["shop"="alcohol"](around:{r_vice},{lat},{lon});
  nwr["shop"="pawnbroker"](around:{r_vice},{lat},{lon});
  nwr["amenity"="nightclub"](around:{r_vice},{lat},{lon});
  nwr["amenity"="stripclub"](around:{r_vice},{lat},{lon});
  nwr["amenity"="gambling"](around:{r_vice},{lat},{lon});
  nwr["amenity"="casino"](around:{r_vice},{lat},{lon});
  nwr["shop"="cannabis"](around:{r_vice},{lat},{lon});

  // === MINOR (500ft) - Only if adjacent ===
  nwr["amenity"="fuel"](around:{r_minor},{lat},{lon});
  nwr["shop"="car_repair"](around:{r_minor},{lat},{lon});
  nwr["craft"="car_repair"](around:{r_minor},{lat},{lon});
  nwr["shop"="scrap_metal"](around:{r_minor},{lat},{lon});
);
out body;
'''

    def _categorize_element(self, tags: Dict) -> Tuple[str, str, str, float]:
        """
        Categorize an OSM element.
        Returns (nuisance_type, display_name, category, deduction).
        Returns (None, None, None, 0) if not a nuisance.
        """
        # === LANDFILL ===
        if tags.get('landuse') == 'landfill':
            return ('landfill', 'landfill', 'severe', self.DEDUCTIONS['landfill'])

        # === PRISON ===
        if tags.get('amenity') == 'prison':
            return ('prison', 'prison/jail', 'severe', self.DEDUCTIONS['prison'])

        # === WASTE TRANSFER ===
        if tags.get('amenity') == 'waste_transfer_station':
            return ('waste_transfer', 'waste transfer station', 'industrial', self.DEDUCTIONS['waste_transfer'])

        # === INDUSTRIAL ===
        if tags.get('landuse') == 'industrial':
            return ('industrial', 'industrial area', 'industrial', self.DEDUCTIONS['industrial'])
        if tags.get('man_made') == 'works':
            return ('industrial', 'factory/plant', 'industrial', self.DEDUCTIONS['industrial'])

        # === MOTEL/SHELTER ===
        if tags.get('tourism') == 'motel':
            return ('motel_shelter', 'motel', 'moderate', self.DEDUCTIONS['motel_shelter'])
        if tags.get('tourism') == 'hostel':
            return ('motel_shelter', 'hostel', 'moderate', self.DEDUCTIONS['motel_shelter'])
        if tags.get('social_facility') == 'shelter' or tags.get('shelter_type') == 'homeless':
            return ('motel_shelter', 'homeless shelter', 'moderate', self.DEDUCTIONS['motel_shelter'])
        if tags.get('healthcare') == 'drug_rehabilitation':
            return ('motel_shelter', 'drug rehab', 'moderate', self.DEDUCTIONS['motel_shelter'])

        # === VICE ===
        if 'storage' in str(tags.get('amenity', '')) + str(tags.get('shop', '')) + str(tags.get('building', '')):
            return ('vice', 'self-storage', 'moderate', self.DEDUCTIONS['vice'])
        if tags.get('shop') == 'alcohol':
            return ('vice', 'liquor store', 'moderate', self.DEDUCTIONS['vice'])
        if tags.get('shop') == 'pawnbroker':
            return ('vice', 'pawn shop', 'moderate', self.DEDUCTIONS['vice'])
        if tags.get('amenity') == 'nightclub':
            return ('vice', 'nightclub', 'moderate', self.DEDUCTIONS['vice'])
        if tags.get('amenity') == 'stripclub':
            return ('vice', 'strip club', 'moderate', self.DEDUCTIONS['vice'] * 1.5)
        if tags.get('amenity') in ['gambling', 'casino']:
            return ('vice', 'casino/gambling', 'moderate', self.DEDUCTIONS['vice'])
        if tags.get('shop') == 'cannabis':
            return ('vice', 'cannabis dispensary', 'moderate', self.DEDUCTIONS['vice'])

        # === MINOR ===
        if tags.get('amenity') == 'fuel':
            return ('minor', 'gas station', 'minor', self.DEDUCTIONS['minor'])
        if tags.get('shop') == 'car_repair' or tags.get('craft') == 'car_repair':
            return ('minor', 'auto repair', 'minor', self.DEDUCTIONS['minor'])
        if tags.get('shop') == 'scrap_metal':
            return ('minor', 'scrap yard', 'minor', self.DEDUCTIONS['minor'])

        return (None, None, None, 0)

    def check_nuisances(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Check for nuisance properties near the given coordinates.
        Uses tiered search radii based on nuisance type.

        Returns:
            Dict with nuisance findings and calculated score
        """
        result = {
            'latitude': lat,
            'longitude': lon,
            'radii': self.RADII.copy(),
            'nuisances': [],
            'by_category': {
                'severe': [],
                'industrial': [],
                'moderate': [],
                'minor': [],
            },
            'severe_count': 0,
            'industrial_count': 0,
            'moderate_count': 0,
            'minor_count': 0,
            'total_deduction': 0,
            'final_score': None,
            'notes': None,
            'error': None
        }

        if not lat or not lon:
            result['error'] = 'Missing coordinates'
            result['notes'] = 'No coordinates available'
            return result

        try:
            self._rate_limit()
            query = self._build_query(lat, lon)
            response = requests.post(self.OVERPASS_URL, data={'data': query}, timeout=45)

            if response.status_code != 200:
                result['error'] = f'API error: {response.status_code}'
                return result

            data = response.json()
            elements = data.get('elements', [])

            total_deduction = 0
            seen_types = set()  # Avoid double-counting same type

            for elem in elements:
                tags = elem.get('tags', {})
                name = tags.get('name', 'Unnamed')
                nuisance_type, display_name, category, deduction = self._categorize_element(tags)

                if nuisance_type and display_name not in seen_types:
                    nuisance_info = {
                        'name': name,
                        'type': display_name,
                        'nuisance_type': nuisance_type,
                        'category': category,
                        'deduction': deduction,
                        'search_radius_m': self.RADII.get(nuisance_type, 0),
                    }
                    result['nuisances'].append(nuisance_info)
                    result['by_category'][category].append(nuisance_info)
                    total_deduction += deduction
                    seen_types.add(display_name)

            # Store counts by category for Excel
            result['severe_count'] = len(result['by_category']['severe'])
            result['industrial_count'] = len(result['by_category']['industrial'])
            result['moderate_count'] = len(result['by_category']['moderate'])
            result['minor_count'] = len(result['by_category']['minor'])

            # Calculate final score (base 10, min 0, max 10)
            result['total_deduction'] = round(total_deduction, 1)
            result['final_score'] = max(0, min(10, round(10 + total_deduction)))

            # Build notes
            notes = []
            for cat in ['severe', 'industrial', 'moderate', 'minor']:
                items = result['by_category'][cat]
                if items:
                    types = [n['type'] for n in items]
                    notes.append(f"{cat.upper()}: {', '.join(types)}")

            if not notes:
                notes.append("No nuisances detected")

            result['notes'] = ' | '.join(notes)

        except requests.exceptions.Timeout:
            result['error'] = 'API timeout'
            result['notes'] = 'OpenStreetMap API timeout - try again later'
        except Exception as e:
            result['error'] = str(e)
            result['notes'] = f'Error checking nuisances: {str(e)[:50]}'

        return result


def test_nuisance_checker():
    """Test the nuisance checker with various locations."""
    checker = NuisanceChecker()

    test_locations = [
        (38.9097, -94.8194, 'Fieldstone (Olathe) - Suburban'),
        (39.0553, -94.4867, 'North Oak Crossing - Near industrial'),
        (39.0408, -94.8089, 'Near Johnson County Landfill'),
        (39.1069, -94.5567, 'Independence Ave KC - Commercial'),
    ]

    for lat, lon, name in test_locations:
        print(f'\n{"="*60}')
        print(f'{name}')
        print(f'{"="*60}')
        result = checker.check_nuisances(lat, lon)
        print(f"Score: {result['final_score']}/10 (deduction: {result['total_deduction']})")
        print(f"Counts: severe={result['severe_count']}, industrial={result['industrial_count']}, moderate={result['moderate_count']}, minor={result['minor_count']}")
        print(f"Notes: {result['notes']}")

        if result['nuisances']:
            print("Found:")
            for n in result['nuisances']:
                radius_ft = round(n['search_radius_m'] * 3.28084)
                print(f"  - {n['name']}: {n['type']} ({n['deduction']} pts, <{radius_ft}ft)")


if __name__ == '__main__':
    test_nuisance_checker()
