"""
GIS Utilities Module for RMP Screener
Shared parcel lookup and GIS query functions
"""

import os
import re
import requests
from datetime import datetime


# Statewide parcel API endpoints (preferred - covers entire state)
STATE_GIS_ENDPOINTS = {
    'CO': {
        'name': 'Colorado Statewide Parcels',
        'url': 'https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0/query',
        'use_envelope': True,  # Colorado requires bounding box query, not point
    },
    'WI': {
        'name': 'Wisconsin Statewide Parcels',
        'url': 'https://services3.arcgis.com/n6uYoouQZW75n5WI/arcgis/rest/services/Wisconsin_Statewide_Parcels/FeatureServer/0/query',
        'use_envelope': False,
    },
}

# County GIS endpoints (fallback for states without statewide API)
COUNTY_GIS_ENDPOINTS = {
    'clay_mo': {
        'name': 'Clay County, MO',
        'url': 'https://services7.arcgis.com/3c8lLdmDNevrTlaV/ArcGIS/rest/services/ClayCountyParcelService/FeatureServer/0/query',
        'bbox_buffer': 0.002,
        'use_envelope': True,
    },
}


def identify_location_from_coords(lat, lon):
    """
    Identify state and county from coordinates using FCC API.
    Returns dict with 'state_code' (2-letter) and 'county_key' (for county endpoints).
    """
    try:
        url = f"https://geo.fcc.gov/api/census/block/find?latitude={lat}&longitude={lon}&format=json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            state_code = data.get('State', {}).get('code', '')
            county = data.get('County', {})
            state_fips = data.get('State', {}).get('FIPS', '')
            county_name = county.get('name', '').lower()

            # Determine county key for fallback
            county_key = None
            if 'clay' in county_name and state_fips == '29':
                county_key = 'clay_mo'

            return {'state_code': state_code, 'county_key': county_key}
    except:
        pass
    return None


def normalize_address_for_match(address):
    """Normalize address for fuzzy matching."""
    if not address:
        return ''
    addr = address.upper().strip()
    # Remove punctuation
    addr = addr.replace('.', '').replace(',', '')
    # Normalize whitespace
    addr = ' '.join(addr.split())
    # Replace common suffixes at word boundaries only
    replacements = [
        (r'\bSTREET\b', 'ST'), (r'\bAVENUE\b', 'AVE'), (r'\bBOULEVARD\b', 'BLVD'),
        (r'\bDRIVE\b', 'DR'), (r'\bROAD\b', 'RD'), (r'\bLANE\b', 'LN'), (r'\bCOURT\b', 'CT'),
        (r'\bPLACE\b', 'PL'), (r'\bCIRCLE\b', 'CIR'), (r'\bHIGHWAY\b', 'HWY'),
    ]
    for pattern, replacement in replacements:
        addr = re.sub(pattern, replacement, addr)
    return addr.strip()


def point_in_polygon(x, y, polygon):
    """Check if point (x,y) is inside polygon using ray casting algorithm."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def query_arcgis_parcel(url, lat, lon, use_wgs84_output=False, use_envelope=False, property_address=None):
    """
    Query an ArcGIS REST parcel layer and return centroid + polygon if found.

    Args:
        url: ArcGIS REST query endpoint
        lat: Latitude in WGS84
        lon: Longitude in WGS84
        use_wgs84_output: If True, request output in WGS84 (for statewide services)
        use_envelope: If True, use bounding box query instead of point (needed for some services)
        property_address: Optional street address to match against parcel situs address

    Returns:
        dict with 'centroid': (lat, lon) and 'polygon': [[lat, lon], ...] or None
    """
    try:
        # Some services (like Colorado) need envelope/bbox query instead of point
        if use_envelope:
            # Create small bounding box around point (~50m)
            buffer = 0.0005
            params = {
                'geometry': f'{lon-buffer},{lat-buffer},{lon+buffer},{lat+buffer}',
                'geometryType': 'esriGeometryEnvelope',
                'inSR': '4326',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': '*',
                'returnGeometry': 'true',
                'f': 'json'
            }
        else:
            params = {
                'geometry': f'{lon},{lat}',
                'geometryType': 'esriGeometryPoint',
                'inSR': '4326',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': '*',
                'returnGeometry': 'true',
                'f': 'json'
            }

        # Request WGS84 output for statewide services (they use state plane projections)
        if use_wgs84_output:
            params['outSR'] = '4326'

        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            features = data.get('features', [])

            if features:
                best_feature = None

                # PRIORITY 1: Match by situs/street address if provided
                if property_address and len(features) > 1:
                    normalized_prop_addr = normalize_address_for_match(property_address)
                    # Extract street number and significant street name parts
                    prop_parts = normalized_prop_addr.split()
                    if prop_parts:
                        prop_number = prop_parts[0] if prop_parts[0].isdigit() else None
                        # Skip common direction prefixes to find actual street name
                        directions = {'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW', 'NORTH', 'SOUTH', 'EAST', 'WEST'}
                        street_name_parts = [p for p in prop_parts[1:] if p not in directions]

                        for feature in features:
                            attrs = feature.get('attributes', {})
                            # Check common address field names
                            for addr_field in ['situsAdd', 'SITUS_ADDR', 'SITUS', 'ADDRESS', 'ADDR',
                                              'PHYADDR', 'PHYSADDR', 'STADDR', 'PROPADDR', 'situs_address',
                                              'situs_display', 'SITUS_DISPLAY']:
                                situs = attrs.get(addr_field, '')
                                if situs:
                                    normalized_situs = normalize_address_for_match(situs)
                                    # Match if street number matches and any street name part is found
                                    if prop_number and normalized_situs.startswith(prop_number + ' '):
                                        # Check if at least one street name part matches
                                        if street_name_parts and any(part in normalized_situs for part in street_name_parts):
                                            best_feature = feature
                                            break
                            if best_feature:
                                break

                # PRIORITY 2: If only one feature, use it
                if not best_feature and len(features) == 1:
                    best_feature = features[0]

                # PRIORITY 3: Check which parcel contains our query point
                if not best_feature:
                    for feature in features:
                        geometry = feature.get('geometry', {})
                        rings = geometry.get('rings', [])
                        if rings and rings[0]:
                            if point_in_polygon(lon, lat, rings[0]):
                                best_feature = feature
                                break

                # PRIORITY 4: If none contain the point, use the closest centroid
                if not best_feature:
                    min_dist = float('inf')
                    for feature in features:
                        geometry = feature.get('geometry', {})
                        rings = geometry.get('rings', [])
                        if rings and rings[0]:
                            pts = rings[0]
                            cx = sum(p[0] for p in pts) / len(pts)
                            cy = sum(p[1] for p in pts) / len(pts)
                            dist = (cx - lon)**2 + (cy - lat)**2
                            if dist < min_dist:
                                min_dist = dist
                                best_feature = feature

                if best_feature:
                    geometry = best_feature.get('geometry', {})
                    rings = geometry.get('rings', [])

                    if rings:
                        all_points = rings[0]  # Outer ring
                        if all_points:
                            # Calculate centroid
                            sum_x = sum(p[0] for p in all_points)
                            sum_y = sum(p[1] for p in all_points)
                            centroid_lon = sum_x / len(all_points)
                            centroid_lat = sum_y / len(all_points)

                            # Convert polygon to lat/lon format (ArcGIS returns lon/lat)
                            polygon = [[p[1], p[0]] for p in all_points]

                            return {
                                'centroid': (centroid_lat, centroid_lon),
                                'polygon': polygon
                            }
    except:
        pass
    return None


def log_missing_county(state_code, county_name, lat, lon, console=None):
    """Log a county that doesn't have a known GIS endpoint."""
    missing_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'missing_counties.txt')

    # Create entry
    entry = f"{county_name}, {state_code} | {lat:.6f}, {lon:.6f} | {datetime.now().strftime('%Y-%m-%d')}"

    # Check if already logged
    existing = set()
    if os.path.exists(missing_file):
        with open(missing_file, 'r') as f:
            for line in f:
                if '|' in line:
                    existing.add(line.split('|')[0].strip())

    county_state = f"{county_name}, {state_code}"
    if county_state not in existing:
        with open(missing_file, 'a') as f:
            f.write(entry + '\n')
        if console:
            console.print(f"[dim]Logged missing county: {county_state}[/dim]")


def try_get_parcel_data(lat, lon, property_address=None, console=None):
    """
    Try to get parcel centroid and polygon from GIS services.
    Tries statewide APIs first, then falls back to county-level.
    Logs unknown counties for future research.

    Args:
        lat: Latitude in WGS84
        lon: Longitude in WGS84
        property_address: Optional street address to match against parcel situs address
        console: Optional Rich console for output

    Returns:
        dict with 'centroid': (lat, lon) and 'polygon': [[lat, lon], ...] or None
    """
    # First identify the location
    location = identify_location_from_coords(lat, lon)

    state_code = ''
    county_name = ''

    if location:
        state_code = location.get('state_code', '')
        county_key = location.get('county_key')

        # Get full county name for logging
        try:
            url = f"https://geo.fcc.gov/api/census/block/find?latitude={lat}&longitude={lon}&format=json"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                county_name = resp.json().get('County', {}).get('name', '')
        except:
            pass

        # Try statewide endpoint first (if available for this state)
        if state_code in STATE_GIS_ENDPOINTS:
            endpoint = STATE_GIS_ENDPOINTS[state_code]
            if console:
                console.print(f"[dim]Trying: {endpoint['name']}[/dim]")
            use_envelope = endpoint.get('use_envelope', False)
            result = query_arcgis_parcel(endpoint['url'], lat, lon, use_wgs84_output=True, use_envelope=use_envelope, property_address=property_address)
            if result:
                if console:
                    console.print(f"[green]Found via: {endpoint['name']}[/green]")
                return result

        # Try county-specific endpoint
        if county_key and county_key in COUNTY_GIS_ENDPOINTS:
            endpoint = COUNTY_GIS_ENDPOINTS[county_key]
            if console:
                console.print(f"[dim]Trying: {endpoint['name']}[/dim]")
            use_envelope = endpoint.get('use_envelope', False)
            result = query_arcgis_parcel(endpoint['url'], lat, lon, use_wgs84_output=True, use_envelope=use_envelope, property_address=property_address)
            if result:
                if console:
                    console.print(f"[green]Found via: {endpoint['name']}[/green]")
                return result

    # Fallback: try all county endpoints
    if console:
        console.print("[dim]Trying all known county GIS services...[/dim]")
    for key, endpoint in COUNTY_GIS_ENDPOINTS.items():
        use_envelope = endpoint.get('use_envelope', False)
        result = query_arcgis_parcel(endpoint['url'], lat, lon, use_wgs84_output=True, use_envelope=use_envelope, property_address=property_address)
        if result:
            if console:
                console.print(f"[dim]Found in: {endpoint['name']}[/dim]")
            return result

    # No parcel found - log the missing county for future research
    if state_code and county_name:
        log_missing_county(state_code, county_name, lat, lon, console)

    if console:
        console.print("[yellow]Could not auto-detect parcel from GIS services.[/yellow]")

    return None
