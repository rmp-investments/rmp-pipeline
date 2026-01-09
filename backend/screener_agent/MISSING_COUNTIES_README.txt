================================================================================
MISSING COUNTIES - CONTEXT FOR CLAUDE
================================================================================

WHAT IS THIS?
-------------
When the RMP Screener can't find a parcel from GIS services, it logs the
county to "missing_counties.txt" in this folder. Bring this file to Claude
to research and add new GIS endpoints.

HOW TO USE:
-----------
1. Copy the contents of missing_counties.txt
2. Paste to Claude with: "Here are missing counties from my screener,
   can you research and add GIS endpoints for these?"
3. Claude will search for ArcGIS REST API endpoints and update the code

FILE LOCATIONS:
---------------
- Missing counties log: screener_agent/missing_counties.txt
- Statewide endpoints:  screener_agent/agent_v2.py (STATE_GIS_ENDPOINTS dict)
- County endpoints:     screener_agent/agent_v2.py (COUNTY_GIS_ENDPOINTS dict)
- Launcher copy:        screener_agent/launcher.py (same dicts, keep in sync)

CURRENT COVERAGE:
-----------------
Statewide APIs (auto-detect for entire state):
  - Colorado (CO) - FeatureServer with envelope query
  - Wisconsin (WI) - FeatureServer with point query

County-level APIs (KC metro area):
  - Jackson County, MO
  - Clay County, MO
  - Platte County, MO
  - Johnson County, KS
  - Wyandotte County, KS

WHAT CLAUDE NEEDS TO ADD A NEW ENDPOINT:
----------------------------------------
1. State code (2-letter) or county name + state
2. Sample coordinates from missing_counties.txt to test
3. Find ArcGIS REST API endpoint (MapServer or FeatureServer)
4. Test if point query or envelope query is needed
5. Add to both agent_v2.py AND launcher.py

ENDPOINT FORMAT:
----------------
Statewide:
  'STATE_CODE': {
      'name': 'State Name Statewide Parcels',
      'url': 'https://...../FeatureServer/0/query',
      'use_envelope': True/False,  # True if point query doesn't work
  }

County:
  'county_state': {
      'name': 'County Name, ST',
      'url': 'https://...../MapServer/0/query',
      'bbox_buffer': 0.001
  }

NOTES:
------
- Statewide APIs are preferred (one endpoint covers all counties)
- Some states (MN, MI) don't have statewide parcel APIs
- use_envelope=True means the service needs bounding box query, not point
- use_wgs84_output=True is added automatically for statewide services
- Test endpoints before adding to confirm they return polygon geometry
================================================================================
