"""
Map Generator Module for RMP Screener
Generates various maps for property analysis
"""

import folium
import os
import requests
import json
import time
from folium.plugins import HeatMap
from concurrent.futures import ThreadPoolExecutor, as_completed


class MapGenerator:
    """Generate maps for property analysis."""

    def __init__(self, lat: float, lon: float, property_name: str, output_dir: str):
        """
        Initialize map generator.

        Args:
            lat: Property latitude
            lon: Property longitude
            property_name: Name of the property
            output_dir: Directory to save map files
        """
        self.lat = lat
        self.lon = lon
        self.property_name = property_name
        self.output_dir = output_dir
        self.flood_zone_info = None  # Will be populated when flood map is created

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

    def get_flood_zone_info(self) -> dict:
        """
        Get the flood zone info for this property.
        If flood map hasn't been created yet, query FEMA directly.

        Returns:
            Dict with flood zone info: {'zone': 'X', 'zone_subtype': '', 'flood_risk': 'Minimal'}
        """
        if self.flood_zone_info is None:
            self.flood_zone_info = self._query_flood_zone_at_point()
        return self.flood_zone_info

    def _fetch_building_footprints(self, radius_meters: int = 150) -> list:
        """
        Fetch building footprints from OpenStreetMap Overpass API.

        Args:
            radius_meters: Search radius around property coordinates

        Returns:
            List of building polygons as [[lat, lon], ...] coordinates
        """
        # Overpass API query for buildings near the point
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:25];
        (
          way["building"](around:{radius_meters},{self.lat},{self.lon});
          relation["building"](around:{radius_meters},{self.lat},{self.lon});
        );
        out body;
        >;
        out skel qt;
        """

        try:
            response = requests.post(overpass_url, data={'data': query}, timeout=30)
            data = response.json()
        except Exception as e:
            print(f"Error fetching OSM data: {e}")
            return []

        # Parse nodes into coordinate lookup
        nodes = {}
        for element in data.get('elements', []):
            if element['type'] == 'node':
                nodes[element['id']] = [element['lat'], element['lon']]

        # Extract building polygons
        buildings = []
        for element in data.get('elements', []):
            if element['type'] == 'way' and 'nodes' in element:
                coords = []
                for node_id in element['nodes']:
                    if node_id in nodes:
                        coords.append(nodes[node_id])
                if len(coords) >= 3:
                    buildings.append(coords)

        return buildings

    def _calculate_zoom_for_polygon(self, parcel_polygon: list, crop_width: int = 800, crop_height: int = 700) -> int:
        """
        Calculate appropriate zoom level to fit the parcel polygon within the crop area.

        Args:
            parcel_polygon: List of [lat, lon] coordinates
            crop_width: Width of crop area in pixels
            crop_height: Height of crop area in pixels

        Returns:
            Appropriate zoom level (typically 16-19)
        """
        import math

        if not parcel_polygon or len(parcel_polygon) < 3:
            return 18  # Default for small/unknown parcels

        # Get bounding box
        lats = [p[0] for p in parcel_polygon]
        lons = [p[1] for p in parcel_polygon]

        lat_span = max(lats) - min(lats)
        lon_span = max(lons) - min(lons)

        # Add 20% padding
        lat_span *= 1.2
        lon_span *= 1.2

        # At zoom level 0, the world is 256 pixels
        # Each zoom level doubles the resolution
        # Latitude degrees per pixel at zoom Z = 360 / (256 * 2^Z)
        # But we need to account for Mercator projection for latitude

        center_lat = (max(lats) + min(lats)) / 2
        lat_rad = math.radians(center_lat)

        # Calculate required zoom for each dimension
        # For longitude: degrees per pixel = 360 / (256 * 2^zoom)
        # For latitude: degrees per pixel = 360 / (256 * 2^zoom) * cos(lat)

        if lon_span > 0:
            zoom_for_lon = math.log2(360 * (crop_width * 0.7) / (256 * lon_span))
        else:
            zoom_for_lon = 19

        if lat_span > 0:
            zoom_for_lat = math.log2(360 * math.cos(lat_rad) * (crop_height * 0.7) / (256 * lat_span))
        else:
            zoom_for_lat = 19

        # Use the smaller zoom (fits both dimensions)
        calculated_zoom = min(zoom_for_lon, zoom_for_lat)

        # Clamp to reasonable range (16-19)
        final_zoom = max(16, min(19, int(calculated_zoom)))

        return final_zoom

    def create_parcel_satellite(self, zoom: int = None, parcel_polygon: list = None) -> str:
        """
        Create a clean satellite view centered on the property.
        Optionally draws the parcel boundary polygon.

        Args:
            zoom: Map zoom level (auto-calculated from polygon if not specified)
            parcel_polygon: Optional list of [lat, lon] coordinates defining the parcel boundary

        Returns:
            Path to saved HTML file
        """
        # Use provided coordinates (already centered on parcel)
        center_lat = self.lat
        center_lon = self.lon

        # Calculate appropriate zoom based on parcel size
        if zoom is None:
            if parcel_polygon and len(parcel_polygon) >= 3:
                zoom = self._calculate_zoom_for_polygon(parcel_polygon)
                print(f"Auto-calculated zoom: {zoom} (based on parcel size)")
            else:
                zoom = 18  # Default for unknown parcel size

        # Use Esri satellite tiles - clean view
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            zoom_control=False,
            scrollWheelZoom=False,
            dragging=False
        )

        # Draw parcel polygon outline if provided
        if parcel_polygon and len(parcel_polygon) >= 3:
            print(f"Drawing parcel boundary ({len(parcel_polygon)} vertices)")
            folium.Polygon(
                locations=parcel_polygon,
                color='#00FFFF',  # Cyan color - visible on satellite
                weight=3,
                fill=False,
                opacity=0.9,
                popup=f"<b>{self.property_name}</b><br>Parcel Boundary"
            ).add_to(m)

        # Save to HTML
        output_path = os.path.join(self.output_dir, f"{self.property_name}_parcel.html")
        m.save(output_path)

        return output_path

    def create_parcel_for_adjustment(self, zoom: int = 16) -> str:
        """
        Create a zoomed-out interactive satellite map for manual parcel adjustment.
        User can pan/zoom to correct location.

        Args:
            zoom: Initial zoom level (16 = zoomed out enough to see area)

        Returns:
            Path to saved HTML file
        """
        print(f"Creating adjustment map at zoom {zoom}...")

        # Use Esri satellite tiles - WITH zoom/pan controls
        m = folium.Map(
            location=[self.lat, self.lon],
            zoom_start=zoom,
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            zoom_control=True,
            scrollWheelZoom=True,
            dragging=True
        )

        # Add a marker at the geocoded point (may be wrong - user will adjust)
        folium.Marker(
            [self.lat, self.lon],
            popup=f"<b>Geocoded location</b><br>{self.property_name}<br><i>Pan to correct location</i>",
            tooltip="Geocoded point (may be incorrect)",
            icon=folium.Icon(color='red', icon='question', prefix='fa')
        ).add_to(m)

        # Add crosshairs at center, crop overlay box, and Done button
        crosshair_js = """
        <style>
            .crosshair {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                z-index: 1000;
                pointer-events: none;
            }
            .crosshair-h, .crosshair-v {
                position: absolute;
                background: rgba(0, 150, 255, 0.7);
            }
            .crosshair-h {
                width: 40px;
                height: 2px;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
            }
            .crosshair-v {
                width: 2px;
                height: 40px;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
            }
            .center-dot {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 8px;
                height: 8px;
                background: rgba(0, 150, 255, 0.9);
                border-radius: 50%;
                border: 2px solid white;
            }
            /* Crop overlay box - shows exact capture area (800x700) */
            .crop-overlay {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 800px;
                height: 700px;
                border: 3px dashed rgba(255, 100, 0, 0.9);
                box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.3);
                z-index: 999;
                pointer-events: none;
                box-sizing: border-box;
            }
            .crop-label {
                position: fixed;
                top: calc(50% - 350px - 30px);
                left: 50%;
                transform: translateX(-50%);
                background: rgba(255, 100, 0, 0.9);
                color: white;
                padding: 5px 15px;
                border-radius: 4px;
                font-family: Arial, sans-serif;
                font-size: 12px;
                font-weight: bold;
                z-index: 1001;
                pointer-events: none;
            }
            .instructions {
                position: fixed;
                top: 10px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.8);
                color: white;
                padding: 10px 20px;
                border-radius: 5px;
                z-index: 1002;
                font-family: Arial, sans-serif;
                font-size: 14px;
                transition: all 0.3s;
            }
            .instructions.ready {
                background: rgba(0, 150, 0, 0.9);
            }
            .done-btn {
                position: fixed;
                bottom: 30px;
                left: 50%;
                transform: translateX(-50%);
                background: #4CAF50;
                color: white;
                border: none;
                padding: 15px 40px;
                font-size: 18px;
                font-weight: bold;
                border-radius: 8px;
                cursor: pointer;
                z-index: 1002;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                transition: all 0.2s;
            }
            .done-btn:hover {
                background: #45a049;
                transform: translateX(-50%) scale(1.05);
            }
            .done-btn.clicked {
                background: #2196F3;
            }
        </style>
        <!-- Crop overlay showing capture area -->
        <div class="crop-overlay"></div>
        <div class="crop-label">CROP AREA (800x700)</div>
        <div class="crosshair">
            <div class="crosshair-h"></div>
            <div class="crosshair-v"></div>
            <div class="center-dot"></div>
        </div>
        <div class="instructions" id="instructions">
            Pan & zoom so the PARCEL fits inside the orange box
        </div>
        <button class="done-btn" id="doneBtn" onclick="markDone()">DONE</button>
        <script>
            var isReady = false;
            var map = null;  // Will be set to the Leaflet map instance

            // Find the Leaflet map instance and expose it globally
            setTimeout(function() {
                for (var key in window) {
                    if (key.startsWith('map_') && window[key] && window[key]._leaflet_id) {
                        map = window[key];
                        window.map = map;
                        break;
                    }
                }
            }, 500);

            function markDone() {
                isReady = true;
                document.getElementById('instructions').textContent = 'Ready! Press Enter in terminal to capture';
                document.getElementById('instructions').classList.add('ready');
                document.getElementById('doneBtn').textContent = 'READY TO CAPTURE';
                document.getElementById('doneBtn').classList.add('clicked');
            }
        </script>
        """
        m.get_root().html.add_child(folium.Element(crosshair_js))

        # Save to HTML
        output_path = os.path.join(self.output_dir, f"{self.property_name}_parcel_adjust.html")
        m.save(output_path)
        print(f"Saved adjustment map: {output_path}")

        return output_path

    # Major US metros with coordinates
    MAJOR_METROS = {
        'New York': (40.7128, -74.0060),
        'Los Angeles': (34.0522, -118.2437),
        'Chicago': (41.8781, -87.6298),
        'Houston': (29.7604, -95.3698),
        'Phoenix': (33.4484, -112.0740),
        'Philadelphia': (39.9526, -75.1652),
        'San Antonio': (29.4241, -98.4936),
        'San Diego': (32.7157, -117.1611),
        'Dallas': (32.7767, -96.7970),
        'San Jose': (37.3382, -121.8863),
        'Austin': (30.2672, -97.7431),
        'Jacksonville': (30.3322, -81.6557),
        'Fort Worth': (32.7555, -97.3308),
        'Columbus': (39.9612, -82.9988),
        'Charlotte': (35.2271, -80.8431),
        'San Francisco': (37.7749, -122.4194),
        'Indianapolis': (39.7684, -86.1581),
        'Seattle': (47.6062, -122.3321),
        'Denver': (39.7392, -104.9903),
        'Boston': (42.3601, -71.0589),
        'Nashville': (36.1627, -86.7816),
        'Detroit': (42.3314, -83.0458),
        'Portland': (45.5152, -122.6784),
        'Memphis': (35.1495, -90.0490),
        'Louisville': (38.2527, -85.7585),
        'Baltimore': (39.2904, -76.6122),
        'Milwaukee': (43.0389, -87.9065),
        'Albuquerque': (35.0844, -106.6504),
        'Tucson': (32.2226, -110.9747),
        'Fresno': (36.7378, -119.7871),
        'Kansas City': (39.0997, -94.5786),
        'Atlanta': (33.7490, -84.3880),
        'Miami': (25.7617, -80.1918),
        'Minneapolis': (44.9778, -93.2650),
        'Cleveland': (41.4993, -81.6944),
        'Tampa': (27.9506, -82.4572),
        'St. Louis': (38.6270, -90.1994),
        'Pittsburgh': (40.4406, -79.9959),
        'Cincinnati': (39.1031, -84.5120),
        'Orlando': (28.5383, -81.3792),
        'Salt Lake City': (40.7608, -111.8910),
        'Las Vegas': (36.1699, -115.1398),
        'Raleigh': (35.7796, -78.6382),
        'Richmond': (37.5407, -77.4360),
        'Oklahoma City': (35.4676, -97.5164),
        'Hartford': (41.7658, -72.6734),
        'Birmingham': (33.5207, -86.8025),
        'Buffalo': (42.8864, -78.8784),
        'Rochester': (43.1566, -77.6088),
        'Omaha': (41.2565, -95.9345),
        'Tulsa': (36.1540, -95.9928),
        'Wichita': (37.6872, -97.3301),
        'New Orleans': (29.9511, -90.0715),
        'Boise': (43.6150, -116.2023),
    }

    def _find_nearest_metro(self) -> tuple:
        """Find the nearest major metro to the property coordinates."""
        import math

        def haversine(lat1, lon1, lat2, lon2):
            R = 3959  # Earth's radius in miles
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            return 2 * R * math.asin(math.sqrt(a))

        nearest = None
        min_dist = float('inf')

        for metro_name, (metro_lat, metro_lon) in self.MAJOR_METROS.items():
            dist = haversine(self.lat, self.lon, metro_lat, metro_lon)
            if dist < min_dist:
                min_dist = dist
                nearest = (metro_name, metro_lat, metro_lon, dist)

        return nearest

    def create_metro_location(self, zoom: int = 10) -> str:
        """
        Create a zoomed out map showing property location relative to nearest major metro.

        Args:
            zoom: Map zoom level (10-11 for metro view)

        Returns:
            Path to saved HTML file
        """
        # Auto-detect nearest metro
        metro_name, metro_lat, metro_lon, distance = self._find_nearest_metro()
        print(f"Nearest metro: {metro_name} ({distance:.1f} miles away)")

        # Calculate center point between property and metro
        center_lat = (self.lat + metro_lat) / 2
        center_lon = (self.lon + metro_lon) / 2

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles='OpenStreetMap'
        )

        # Add property marker (red)
        folium.Marker(
            [self.lat, self.lon],
            popup=f"<b>{self.property_name}</b>",
            tooltip=self.property_name,
            icon=folium.Icon(color='red', icon='home', prefix='fa')
        ).add_to(m)

        # Add metro center marker (blue)
        folium.Marker(
            [metro_lat, metro_lon],
            popup=f"<b>{metro_name}</b>",
            tooltip=metro_name,
            icon=folium.Icon(color='blue', icon='city', prefix='fa')
        ).add_to(m)

        # Draw line connecting them
        folium.PolyLine(
            [[self.lat, self.lon], [metro_lat, metro_lon]],
            color='gray',
            weight=2,
            opacity=0.7,
            dash_array='5, 10'
        ).add_to(m)

        # Save to HTML
        output_path = os.path.join(self.output_dir, f"{self.property_name}_metro_location.html")
        m.save(output_path)

        return output_path


    def _get_property_county(self) -> dict:
        """
        Get the county containing the property using FCC Area API.

        Returns:
            Dict with state_fips, county_fips (3-digit), county_name, state_code
        """
        url = "https://geo.fcc.gov/api/census/area"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'format': 'json'
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()

            if data.get('results'):
                result = data['results'][0]
                # FCC returns county_fips as 5-digit (state+county), extract just the 3-digit county
                full_county_fips = result['county_fips']
                county_fips_3digit = full_county_fips[2:]  # Remove state prefix
                return {
                    'state_fips': result['state_fips'],
                    'county_fips': county_fips_3digit,
                    'county_name': result['county_name'],
                    'state_code': result['state_code']
                }
        except Exception as e:
            print(f"Error getting property county: {e}")

        return None

    def _get_county_geometry(self, state_fips: str, county_fips: str) -> dict:
        """
        Get county boundary geometry from TIGERweb.

        Returns:
            Dict with geometry rings and county info
        """
        # Layer 78 = Counties in TIGERweb ACS2022
        tiger_url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2022/MapServer/78/query"

        params = {
            'where': f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
            'outFields': 'GEOID,NAME,STATE,COUNTY',
            'returnGeometry': 'true',
            'outSR': '4326',
            'f': 'json'
        }

        try:
            resp = requests.get(tiger_url, params=params, timeout=30)
            data = resp.json()

            if data.get('features'):
                feat = data['features'][0]
                return {
                    'geometry': feat.get('geometry', {}),
                    'attributes': feat.get('attributes', {})
                }
        except Exception as e:
            print(f"Error getting county geometry: {e}")

        return None

    def _get_adjacent_counties(self, state_fips: str, county_fips: str) -> list:
        """
        Find all counties that share a boundary with the subject county.
        Uses TIGERweb spatial query with bounding box + intersection filter.

        Returns:
            List of (state_fips, county_fips, county_name) tuples
        """
        # First get the subject county's geometry
        subject = self._get_county_geometry(state_fips, county_fips)
        if not subject or not subject.get('geometry'):
            print("Could not get subject county geometry")
            return []

        geometry = subject['geometry']
        rings = geometry.get('rings', [])

        if not rings:
            print("No geometry rings found")
            return []

        # Calculate bounding box from geometry with small buffer
        all_x = []
        all_y = []
        for ring in rings:
            for pt in ring:
                all_x.append(pt[0])
                all_y.append(pt[1])

        # Add a small buffer to ensure we catch touching counties
        buffer = 0.1  # degrees, roughly 7 miles
        envelope = {
            'xmin': min(all_x) - buffer,
            'ymin': min(all_y) - buffer,
            'xmax': max(all_x) + buffer,
            'ymax': max(all_y) + buffer,
            'spatialReference': {'wkid': 4326}
        }

        # Query for counties that intersect the bounding box
        tiger_url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2022/MapServer/78/query"

        params = {
            'where': '1=1',
            'geometry': json.dumps(envelope),
            'geometryType': 'esriGeometryEnvelope',
            'inSR': '4326',
            'outSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': 'GEOID,NAME,STATE,COUNTY',
            'returnGeometry': 'false',
            'f': 'json'
        }

        adjacent = []
        try:
            resp = requests.get(tiger_url, params=params, timeout=30)
            data = resp.json()

            for feat in data.get('features', []):
                attrs = feat.get('attributes', {})
                adj_state = attrs.get('STATE', '')
                adj_county = attrs.get('COUNTY', '')
                adj_name = attrs.get('NAME', '')

                # Skip the subject county itself
                if adj_state == state_fips and adj_county == county_fips:
                    continue

                adjacent.append((adj_state, adj_county, adj_name))

        except Exception as e:
            print(f"Error finding adjacent counties: {e}")

        return adjacent

    def _get_county_tracts(self, state_fips: str, county_fips: str, max_retries: int = 3) -> dict:
        """Fetch all census tracts for a county with geometry."""
        import time
        tiger_url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2022/MapServer/6/query"

        for attempt in range(max_retries):
            all_features = []
            offset = 0
            batch_size = 1000

            try:
                while True:
                    params = {
                        'where': f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
                        'outFields': 'GEOID,STATE,COUNTY,TRACT',
                        'returnGeometry': 'true',
                        'outSR': '4326',
                        'f': 'json',
                        'resultOffset': offset,
                        'resultRecordCount': batch_size
                    }

                    resp = requests.get(tiger_url, params=params, timeout=60)
                    data = resp.json()

                    features = data.get('features', [])
                    all_features.extend(features)

                    if not data.get('exceededTransferLimit', False):
                        break

                    offset += batch_size

                if all_features:
                    return {'features': all_features}

                if attempt < max_retries - 1:
                    time.sleep(1)

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)

        return {'features': all_features}

    def _get_county_incomes(self, state_fips: str, county_fips: str) -> dict:
        """Get median household income for all tracts in a county."""
        url = "https://api.census.gov/data/2022/acs/acs5"

        params = {
            'get': 'B19013_001E',
            'for': 'tract:*',
            'in': f'state:{state_fips}&in=county:{county_fips}'
        }

        incomes = {}
        try:
            resp = requests.get(url, params=params, timeout=30)
            data = resp.json()

            for row in data[1:]:
                income, st, cty, tract = row
                geoid = f"{st}{cty}{tract}"
                if income and income != '-666666666':
                    incomes[geoid] = float(income)
        except Exception as e:
            print(f"    Error fetching income for {state_fips}-{county_fips}: {e}")

        return incomes

    def _get_census_tracts_income(self, radius_miles: float = 5) -> list:
        """
        Fetch census tract boundaries and median household income data.
        Uses Census TIGERweb for boundaries and ACS for income data.

        Returns:
            List of dicts with tract geometry and income data
        """
        tracts_data = []

        # Convert radius to degrees (rough approximation)
        radius_deg = radius_miles / 69.0

        # Bounding box around property
        min_lat = self.lat - radius_deg
        max_lat = self.lat + radius_deg
        min_lon = self.lon - radius_deg
        max_lon = self.lon + radius_deg

        # Census TIGERweb API for boundaries (ACS 2022) - Layer 8 = Census Block Groups (smaller)
        tiger_url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2022/MapServer/8/query"

        # Use proper JSON envelope format
        envelope = {
            'xmin': min_lon,
            'ymin': min_lat,
            'xmax': max_lon,
            'ymax': max_lat,
            'spatialReference': {'wkid': 4326}
        }

        params = {
            'where': '1=1',
            'geometry': json.dumps(envelope),
            'geometryType': 'esriGeometryEnvelope',
            'inSR': '4326',
            'outSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': 'GEOID,STATE,COUNTY,TRACT',
            'returnGeometry': 'true',
            'f': 'json'
        }

        try:
            print("Fetching census tract boundaries...")
            resp = requests.get(tiger_url, params=params, timeout=30)
            data = resp.json()

            if 'features' not in data:
                print(f"No features in response: {data.get('error', 'Unknown error')}")
                return []

            print(f"Found {len(data['features'])} census tracts")

            # Parse all features first
            features_to_query = []
            for feature in data['features']:
                attrs = feature.get('attributes', {})
                geometry = feature.get('geometry', {})
                rings = geometry.get('rings', [])

                if not rings:
                    continue

                # Convert rings to lat/lon format for folium
                coords = []
                for ring in rings:
                    ring_coords = [[pt[1], pt[0]] for pt in ring]  # Swap lon/lat to lat/lon
                    coords.append(ring_coords)

                features_to_query.append({
                    'geoid': attrs.get('GEOID', ''),
                    'state': attrs.get('STATE', ''),
                    'county': attrs.get('COUNTY', ''),
                    'tract': attrs.get('TRACT', ''),
                    'blkgrp': attrs.get('BLKGRP', ''),
                    'coords': coords
                })

            # Group tracts by state+county for batch queries
            county_groups = {}
            for feat in features_to_query:
                key = (feat['state'], feat['county'])
                if key not in county_groups:
                    county_groups[key] = []
                county_groups[key].append(feat)

            print(f"Fetching income data for {len(features_to_query)} tracts across {len(county_groups)} counties...")

            # Batch query income by county (much faster)
            income_lookup = {}
            for (state, county), feats in county_groups.items():
                county_incomes = self._get_county_block_group_incomes(state, county)
                income_lookup.update(county_incomes)

            # Build final block group data - use GEOID for lookup
            for feat in features_to_query:
                tracts_data.append({
                    'geoid': feat['geoid'],
                    'coords': feat['coords'],
                    'income': income_lookup.get(feat['geoid'])
                })

        except Exception as e:
            print(f"Error fetching census data: {e}")

        return tracts_data

    def _get_tract_income(self, state: str, county: str, tract: str) -> float:
        """Get median household income for a census tract from ACS."""
        # ACS 5-year estimates, B19013_001E = Median Household Income
        url = f"https://api.census.gov/data/2022/acs/acs5"

        params = {
            'get': 'B19013_001E,NAME',
            'for': f'tract:{tract}',
            'in': f'state:{state}&in=county:{county}'
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if len(data) > 1:
                income = data[1][0]
                if income and income != '-666666666':  # Census null value
                    return float(income)
        except:
            pass

        return None

    def _get_county_block_group_incomes(self, state: str, county: str) -> dict:
        """Get median household income for ALL block groups in a county (batch query)."""
        url = "https://api.census.gov/data/2022/acs/acs5"

        params = {
            'get': 'B19013_001E',
            'for': 'block group:*',
            'in': f'state:{state}&in=county:{county}&in=tract:*'
        }

        incomes = {}
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()

            # Skip header row, parse data rows
            # Format: income, state, county, tract, block group
            for row in data[1:]:
                income, row_state, row_county, tract, blkgrp = row
                # Build GEOID format: state(2) + county(3) + tract(6) + blkgrp(1)
                geoid = f"{row_state}{row_county}{tract}{blkgrp}"
                if income and income != '-666666666':
                    incomes[geoid] = float(income)
        except Exception as e:
            print(f"  Error fetching county {state}-{county}: {e}")

        return incomes

    def create_income_heatmap(self, radius_miles: float = 5, zoom: int = 11) -> str:
        """
        Create a choropleth map showing median household income by census tract.

        Args:
            radius_miles: Radius around property to show
            zoom: Map zoom level

        Returns:
            Path to saved HTML file
        """
        print("Creating income heat map...")

        # Get census tract data with income
        tracts = self._get_census_tracts_income(radius_miles)

        if not tracts:
            print("No tract data available")
            return None

        # Filter tracts with valid income data
        valid_tracts = [t for t in tracts if t['income'] is not None]
        print(f"Got income data for {len(valid_tracts)}/{len(tracts)} tracts")

        if not valid_tracts:
            print("No income data available")
            return None

        # Calculate income range for color scaling
        incomes = [t['income'] for t in valid_tracts]
        min_income = min(incomes)
        max_income = max(incomes)

        print(f"Income range: ${min_income:,.0f} - ${max_income:,.0f}")

        # Create map
        m = folium.Map(
            location=[self.lat, self.lon],
            zoom_start=zoom,
            tiles='CartoDB positron'
        )

        # 6-color scheme (low to high income) - professional blues/greens
        colors = [
            '#d73027',  # Red - lowest
            '#fc8d59',  # Orange
            '#fee08b',  # Yellow
            '#d9ef8b',  # Light green
            '#91cf60',  # Green
            '#1a9850',  # Dark green - highest
        ]

        # Calculate quantile-based thresholds (equal number of tracts per bucket)
        sorted_incomes = sorted(incomes)
        n = len(sorted_incomes)
        thresholds = [sorted_incomes[0]]  # Start with min
        for i in range(1, 6):
            idx = int(n * i / 6)
            thresholds.append(sorted_incomes[idx])
        thresholds.append(sorted_incomes[-1])  # End with max

        print(f"Quantile thresholds: {[f'${t:,.0f}' for t in thresholds]}")

        def get_color(income):
            if income is None:
                return '#cccccc'
            for i in range(6):
                if income <= thresholds[i + 1]:
                    return colors[i]
            return colors[5]

        # Add tract polygons
        for tract in valid_tracts:
            color = get_color(tract['income'])

            for ring in tract['coords']:
                folium.Polygon(
                    locations=ring,
                    color='#666666',
                    weight=0.5,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.4,
                    popup=f"Median HH Income: ${tract['income']:,.0f}"
                ).add_to(m)

        # Add labels layer on top of choropleth (so city names are visible)
        folium.TileLayer(
            tiles='https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png',
            attr='CartoDB',
            name='Labels',
            overlay=True,
            control=False
        ).add_to(m)

        # Add property marker
        folium.Marker(
            [self.lat, self.lon],
            popup=f"<b>{self.property_name}</b>",
            tooltip=self.property_name,
            icon=folium.Icon(color='blue', icon='home', prefix='fa')
        ).add_to(m)

        # Add legend with 6 color buckets (50% larger for visibility)
        legend_html = f'''
        <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                    background-color: rgba(255,255,255,0.9); padding: 18px 22px;
                    border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.2);
                    font-family: Arial, sans-serif; font-size: 16px;">
            <div style="font-weight: bold; margin-bottom: 12px; font-size: 18px;">Median HH Income</div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="background:{colors[5]}; width:30px; height:21px; display:inline-block; border-radius: 3px; margin-right: 12px;"></span>
                <span>${thresholds[5]:,.0f}+</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="background:{colors[4]}; width:30px; height:21px; display:inline-block; border-radius: 3px; margin-right: 12px;"></span>
                <span>${thresholds[4]:,.0f} - ${thresholds[5]:,.0f}</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="background:{colors[3]}; width:30px; height:21px; display:inline-block; border-radius: 3px; margin-right: 12px;"></span>
                <span>${thresholds[3]:,.0f} - ${thresholds[4]:,.0f}</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="background:{colors[2]}; width:30px; height:21px; display:inline-block; border-radius: 3px; margin-right: 12px;"></span>
                <span>${thresholds[2]:,.0f} - ${thresholds[3]:,.0f}</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="background:{colors[1]}; width:30px; height:21px; display:inline-block; border-radius: 3px; margin-right: 12px;"></span>
                <span>${thresholds[1]:,.0f} - ${thresholds[2]:,.0f}</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="background:{colors[0]}; width:30px; height:21px; display:inline-block; border-radius: 3px; margin-right: 12px;"></span>
                <span>&lt; ${thresholds[1]:,.0f}</span>
            </div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        # Save
        output_path = os.path.join(self.output_dir, f"{self.property_name}_income_map.html")
        m.save(output_path)

        return output_path

    def create_income_map(self, zoom: int = 9) -> str:
        """
        Create income choropleth map showing the subject county plus all adjacent counties.
        Dynamically detects the property's county and finds neighboring counties.

        Args:
            zoom: Map zoom level (9 works well for county + neighbors view)

        Returns:
            Path to saved HTML file
        """
        print("Creating income map (subject county + adjacent counties)...")

        # Get the property's county
        prop_county = self._get_property_county()
        if not prop_county:
            print("Could not determine property county - falling back to radius method")
            return self.create_income_heatmap(radius_miles=15, zoom=zoom)

        state_fips = prop_county['state_fips']
        county_fips = prop_county['county_fips']
        county_name = prop_county['county_name']
        state_code = prop_county['state_code']

        print(f"Property located in: {county_name}, {state_code}")

        # Find adjacent counties
        print("Finding adjacent counties...")
        adjacent = self._get_adjacent_counties(state_fips, county_fips)
        print(f"Found {len(adjacent)} adjacent counties")

        # Build list of all counties to fetch (subject + adjacent)
        all_counties = [(state_fips, county_fips, f"{county_name} (Subject)")]
        all_counties.extend(adjacent)

        print(f"Fetching data for {len(all_counties)} counties...")

        # Collect tract data from all counties
        all_tracts = []
        for state, county, name in all_counties:
            print(f"  {name}...", end=" ", flush=True)

            # Get geometries
            geo_data = self._get_county_tracts(state, county)
            features = geo_data.get('features', [])

            # Get incomes
            incomes = self._get_county_incomes(state, county)
            print(f"{len(features)} tracts, {len(incomes)} with income")

            # Parse features
            for feat in features:
                attrs = feat.get('attributes', {})
                geom = feat.get('geometry', {})
                rings = geom.get('rings', [])

                if not rings:
                    continue

                geoid = attrs.get('GEOID', '')
                coords = [[[pt[1], pt[0]] for pt in ring] for ring in rings]

                all_tracts.append({
                    'geoid': geoid,
                    'coords': coords,
                    'income': incomes.get(geoid)
                })

        print(f"Total: {len(all_tracts)} tracts")

        # Filter valid income
        valid_tracts = [t for t in all_tracts if t['income'] is not None]
        print(f"With income data: {len(valid_tracts)}")

        if not valid_tracts:
            print("No income data available")
            return None

        # Calculate thresholds
        incomes = [t['income'] for t in valid_tracts]
        sorted_incomes = sorted(incomes)
        n = len(sorted_incomes)
        thresholds = [sorted_incomes[0]]
        for i in range(1, 6):
            thresholds.append(sorted_incomes[int(n * i / 6)])
        thresholds.append(sorted_incomes[-1])

        print(f"Income range: ${min(incomes):,.0f} - ${max(incomes):,.0f}")

        # Color scale
        colors = ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60', '#1a9850']

        def get_color(income):
            for i in range(6):
                if income <= thresholds[i + 1]:
                    return colors[i]
            return colors[5]

        # Create map
        m = folium.Map(location=[self.lat, self.lon], zoom_start=zoom, tiles='CartoDB positron')

        # Draw all tracts (gray for no data)
        print("Drawing map...")
        for tract in all_tracts:
            if tract['income'] is not None:
                color = get_color(tract['income'])
                popup = f"${tract['income']:,.0f}"
            else:
                color = '#999999'
                popup = "No data"

            for ring in tract['coords']:
                folium.Polygon(
                    locations=ring,
                    color='#666666',
                    weight=0.3,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.5,
                    popup=popup
                ).add_to(m)

        # Property marker
        folium.Marker(
            [self.lat, self.lon],
            popup=f"<b>{self.property_name}</b>",
            tooltip=self.property_name,
            icon=folium.Icon(color='blue', icon='home', prefix='fa')
        ).add_to(m)

        # Legend (50% larger for visibility)
        legend_html = f'''
        <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                    background-color: rgba(255,255,255,0.95); padding: 18px 22px;
                    border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.2);
                    font-family: Arial, sans-serif; font-size: 16px;">
            <div style="font-weight: bold; margin-bottom: 12px; font-size: 18px;">Median HH Income</div>
            <div style="margin: 5px 0;"><span style="background:{colors[5]}; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> ${thresholds[5]:,.0f}+</div>
            <div style="margin: 5px 0;"><span style="background:{colors[4]}; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> ${thresholds[4]:,.0f}-${thresholds[5]:,.0f}</div>
            <div style="margin: 5px 0;"><span style="background:{colors[3]}; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> ${thresholds[3]:,.0f}-${thresholds[4]:,.0f}</div>
            <div style="margin: 5px 0;"><span style="background:{colors[2]}; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> ${thresholds[2]:,.0f}-${thresholds[3]:,.0f}</div>
            <div style="margin: 5px 0;"><span style="background:{colors[1]}; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> ${thresholds[1]:,.0f}-${thresholds[2]:,.0f}</div>
            <div style="margin: 5px 0;"><span style="background:{colors[0]}; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> &lt;${thresholds[1]:,.0f}</div>
            <div style="margin-top: 8px; border-top: 1px solid #ddd; padding-top: 8px;"><span style="background:#999999; width:27px; height:18px; display:inline-block; margin-right: 8px; vertical-align: middle;"></span> No data</div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        # Save
        output_path = os.path.join(self.output_dir, f"{self.property_name}_income_map.html")
        m.save(output_path)
        print(f"Saved: {output_path}")

        return output_path

    def _query_flood_zone_at_point(self) -> dict:
        """
        Query FEMA to get the actual flood zone at the property coordinates.

        Returns:
            Dict with flood zone info: {'zone': 'X', 'zone_subtype': '', 'flood_risk': 'Minimal'}
        """
        try:
            # FEMA NFHL query endpoint - layer 28 is Flood Hazard Zones
            query_url = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query'
            params = {
                'geometry': f'{self.lon},{self.lat}',
                'geometryType': 'esriGeometryPoint',
                'inSR': '4326',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': 'FLD_ZONE,ZONE_SUBTY,SFHA_TF',
                'returnGeometry': 'false',
                'f': 'json'
            }

            resp = requests.get(query_url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                features = data.get('features', [])
                if features:
                    attrs = features[0].get('attributes', {})
                    zone = attrs.get('FLD_ZONE', 'Unknown')
                    subtype = attrs.get('ZONE_SUBTY', '')
                    sfha = attrs.get('SFHA_TF', '')  # T = Special Flood Hazard Area

                    # Determine risk level
                    if zone in ['A', 'AE', 'AH', 'AO', 'AR', 'A99']:
                        risk = 'High Risk (1% annual flood chance)'
                    elif zone in ['V', 'VE']:
                        risk = 'High Risk - Coastal (1% annual + wave action)'
                    elif zone == 'X' and subtype == '0.2 PCT ANNUAL CHANCE FLOOD HAZARD':
                        risk = 'Moderate Risk (0.2% annual flood chance)'
                    elif zone == 'X':
                        risk = 'Minimal Risk'
                    elif zone == 'D':
                        risk = 'Undetermined Risk'
                    else:
                        risk = 'Unknown'

                    print(f"  [OK] Flood zone at property: {zone} ({risk})")
                    return {'zone': zone, 'zone_subtype': subtype, 'flood_risk': risk, 'sfha': sfha}
                else:
                    print(f"  [INFO] No FEMA flood data at this location (likely unmapped area)")
                    return {'zone': 'Unmapped', 'zone_subtype': '', 'flood_risk': 'No FEMA data available'}
        except Exception as e:
            print(f"  [WARN] Could not query flood zone: {e}")

        return {'zone': 'Unknown', 'zone_subtype': '', 'flood_risk': 'Query failed'}

    def create_flood_zone_map(self, zoom: int = 16) -> str:
        """
        Create a flood zone map using FEMA National Flood Hazard Layer (NFHL).
        Shows flood zones overlaid on street map with property marker.
        Also queries the actual flood zone at the property point.

        Args:
            zoom: Map zoom level (15 for detailed property-level view)

        Returns:
            Path to saved HTML file
        """
        print("Creating flood zone map...")

        # First, query the actual flood zone at the property
        flood_info = self._query_flood_zone_at_point()
        self.flood_zone_info = flood_info  # Store for later use

        # Create base map
        m = folium.Map(
            location=[self.lat, self.lon],
            zoom_start=zoom,
            tiles=None
        )

        # Add Street Map base layer
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Street Map',
            overlay=False,
            control=True
        ).add_to(m)

        # Add Satellite base layer (can toggle in layer control)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satellite',
            overlay=False,
            control=True
        ).add_to(m)

        # Fetch FEMA flood zone image - LARGE area so zooming out still works
        import math

        # Convert lat/lon to Web Mercator
        x = self.lon * 20037508.34 / 180
        y_rad = self.lat * math.pi / 180
        y = math.log(math.tan(y_rad) + 1/math.cos(y_rad)) * 20037508.34 / math.pi

        # Large bounding box - about 5km around property (covers most zoom levels)
        delta = 5000  # meters in web mercator
        bbox = f'{x-delta},{y-delta},{x+delta},{y+delta}'

        export_url = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export'
        params = {
            'bbox': bbox,
            'bboxSR': '102100',
            'imageSR': '102100',
            'size': '2000,2000',
            'format': 'png32',
            'transparent': 'true',
            'layers': 'show:28',  # Flood Hazard Zones
            'f': 'image'
        }

        try:
            r = requests.get(export_url, params=params, timeout=30)
            if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
                flood_img_path = os.path.join(self.output_dir, f"{self.property_name}_flood_overlay.png")
                with open(flood_img_path, 'wb') as f:
                    f.write(r.content)

                # Calculate bounds for overlay
                def mercator_to_latlon(mx, my):
                    lon = mx * 180 / 20037508.34
                    lat = math.atan(math.sinh(my * math.pi / 20037508.34)) * 180 / math.pi
                    return lat, lon

                sw_lat, sw_lon = mercator_to_latlon(x - delta, y - delta)
                ne_lat, ne_lon = mercator_to_latlon(x + delta, y + delta)

                folium.raster_layers.ImageOverlay(
                    image=flood_img_path,
                    bounds=[[sw_lat, sw_lon], [ne_lat, ne_lon]],
                    opacity=0.92,
                    name='FEMA Flood Zones',
                    overlay=True,
                    control=True
                ).add_to(m)
                print(f"  [OK] FEMA flood zones loaded (5km radius)")
            else:
                print(f"  [WARN] FEMA returned non-image response: {r.status_code}")
        except Exception as e:
            print(f"  [WARN] Could not fetch FEMA flood data: {e}")

        # Property marker with flood zone info in popup
        popup_html = f"""
        <div style="font-family: Arial; min-width: 200px;">
            <b style="font-size: 14px;">{self.property_name}</b><br><br>
            <b>Flood Zone:</b> {flood_info['zone']}<br>
            <b>Risk Level:</b> {flood_info['flood_risk']}<br>
            {f"<b>Subtype:</b> {flood_info['zone_subtype']}<br>" if flood_info['zone_subtype'] else ""}
        </div>
        """
        folium.Marker(
            [self.lat, self.lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{self.property_name} - Zone {flood_info['zone']}",
            icon=folium.Icon(color='red', icon='home', prefix='fa')
        ).add_to(m)


        # Legend matching FEMA's actual color scheme
        # All high-risk zones (A/AE/AO/AH/V/VE) are the SAME blue - they're all 1% annual chance
        legend_html = f'''
        <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                    background-color: rgba(255,255,255,0.97); padding: 18px 22px;
                    border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.25);
                    font-family: Arial, sans-serif; font-size: 13px; max-width: 300px;">
            <div style="font-weight: bold; margin-bottom: 12px; font-size: 16px;">FEMA Flood Zones</div>

            <div style="margin: 8px 0;"><span style="background:repeating-linear-gradient(45deg, #D73B3B, #D73B3B 3px, #6B9FCD 3px, #6B9FCD 6px); width:24px; height:16px; display:inline-block; margin-right: 10px; vertical-align: middle; border: 1px solid #666;"></span> <b>Floodway</b></div>
            <div style="margin: 8px 0;"><span style="background:#6B9FCD; width:24px; height:16px; display:inline-block; margin-right: 10px; vertical-align: middle; border: 1px solid #666;"></span> <b>High Risk</b> <span style="color:#666;">(A/AE/V/VE)</span></div>
            <div style="margin: 8px 0;"><span style="background:#F5A623; width:24px; height:16px; display:inline-block; margin-right: 10px; vertical-align: middle; border: 1px solid #666;"></span> <b>Moderate</b> <span style="color:#666;">(X 0.2%)</span></div>
            <div style="margin: 8px 0;"><span style="background:#FFFFFF; width:24px; height:16px; display:inline-block; margin-right: 10px; vertical-align: middle; border: 1px solid #666;"></span> <b>Minimal</b> <span style="color:#666;">(X)</span></div>

            <div style="margin-top: 14px; padding-top: 10px; border-top: 2px solid #ddd;">
                <div style="font-weight: bold; color: #333;">Property Zone:</div>
                <div style="font-size: 16px; margin-top: 4px; color: #000;"><b>{flood_info['zone']}</b></div>
                <div style="font-size: 12px; color: #555;">{flood_info['flood_risk']}</div>
            </div>

            <div style="margin-top: 10px; font-size: 10px; color: #888;">
                Source: FEMA NFHL
            </div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        # Add layer control
        folium.LayerControl().add_to(m)

        # Save
        output_path = os.path.join(self.output_dir, f"{self.property_name}_flood_map.html")
        m.save(output_path)
        print(f"Saved: {output_path}")

        return output_path

    def capture_screenshot(self, html_path: str, width: int = 800, height: int = 500) -> str:
        """
        Capture a screenshot of an HTML map file using headless Chrome.

        Args:
            html_path: Path to the HTML map file
            width: Screenshot width in pixels
            height: Screenshot height in pixels

        Returns:
            Path to saved PNG screenshot, or None if failed
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            print("Selenium or webdriver-manager not installed. Skipping screenshot.")
            return None

        # Output path for screenshot
        base_name = os.path.splitext(os.path.basename(html_path))[0]
        output_path = os.path.join(self.output_dir, f"{base_name}.png")

        # Set up Chrome options for headless mode
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"--window-size={width},{height}")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--log-level=3")  # Suppress logging

        try:
            # Create driver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # Load the HTML file
            file_url = f"file:///{html_path.replace(os.sep, '/')}"
            driver.get(file_url)

            # Wait for map tiles to load (longer for flood maps with FEMA overlay)
            if 'flood' in html_path.lower():
                time.sleep(6)  # FEMA overlay needs more time
            else:
                time.sleep(3)

            # Take screenshot
            driver.save_screenshot(output_path)
            driver.quit()

            print(f"Screenshot saved: {output_path}")
            return output_path

        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None

    def capture_all_screenshots(self) -> dict:
        """
        Capture screenshots of all generated HTML maps in output directory.

        Returns:
            Dict mapping map type to screenshot path, plus html paths
        """
        screenshots = {}

        # Map types and their HTML file patterns with capture dimensions
        map_configs = {
            'location': (f"{self.property_name}_metro_location.html", 800, 500),
            'income': (f"{self.property_name}_income_map.html", 1900, 550),  # Wide + 10% taller for Stage 1
            'parcel': (f"{self.property_name}_parcel.html", 650, 700),  # Taller for full property view
            'flood': (f"{self.property_name}_flood_map.html", 1900, 550)  # Same size as income map
        }

        for map_type, (filename, width, height) in map_configs.items():
            html_path = os.path.join(self.output_dir, filename)
            if os.path.exists(html_path):
                print(f"Capturing {map_type} map screenshot...")
                screenshot = self.capture_screenshot(html_path, width=width, height=height)
                if screenshot:
                    screenshots[map_type] = screenshot
                    screenshots[f'{map_type}_html'] = html_path

        return screenshots


# Quick test
if __name__ == "__main__":
    # Fieldstone Apartments coordinates
    lat = 38.886462886948
    lon = -94.768785461941

    output_dir = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\Maps"

    generator = MapGenerator(lat, lon, "Fieldstone Apartments", output_dir)

    print("Generating maps...")

    # 1. Parcel satellite view
    path1 = generator.create_parcel_satellite(zoom=18)
    print(f"1. Parcel satellite: {path1}")

    # 2. Metro location map
    path2 = generator.create_metro_location(zoom=10)
    print(f"2. Metro location: {path2}")

    # 3. Income map (subject county + adjacent)
    path3 = generator.create_income_map(zoom=9)
    print(f"3. Income map: {path3}")

    print("\nDone! Open the HTML files in a browser to view.")
