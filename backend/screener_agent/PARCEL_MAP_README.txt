PARCEL MAP SYSTEM - HOW IT WORKS
=================================

OVERVIEW
--------
The screener automatically tries to find the exact parcel boundary for each
property and draw it on the satellite map. This works for some properties
but not others, depending on location.


WHEN PARCEL BOUNDARIES WORK (automatic)
---------------------------------------
Properties in these locations will automatically get parcel boundaries:

  - COLORADO (any county) - Statewide parcel API available
  - WISCONSIN (any county) - Statewide parcel API available
  - CLAY COUNTY, MO - County endpoint available

For these properties, the screener will:
  1. Query the GIS service with the property coordinates
  2. Find the matching parcel polygon
  3. Draw the red boundary outline on the satellite map
  4. Save the parcel data to the config file for future runs


WHEN PARCEL BOUNDARIES DON'T WORK
---------------------------------
Properties in states/counties WITHOUT public parcel APIs will NOT get
automatic boundaries. This includes:

  - KANSAS (all counties) - No public parcel API
  - MISSOURI (except Clay County) - No public parcel API
  - MINNESOTA - No public parcel API
  - MICHIGAN - No public parcel API

For these properties, the satellite map will show:
  - Centered on the geocoded address (may be slightly off)
  - NO red parcel boundary outline
  - May be cropped wrong or show wrong property


HOW TO FIX - "Fix Parcel Map" Mode
----------------------------------
Use the launcher menu option 3 "Fix parcel map" to manually set the parcel:

  1. Run the launcher (double-click RUN_SCREENER.bat)
  2. Select option 3 "Fix parcel map"
  3. Select the property to fix
  4. The system will try auto-detection first
     - If it works, confirm and you're done
     - If it fails, a browser window opens for manual adjustment
  5. For manual mode:
     - Pan/zoom the map to center on the property
     - Click DONE when the parcel is centered
     - Press Enter in the terminal to capture
  6. The new coordinates are saved to the config file
  7. The Excel file is updated with the new screenshot


CONFIG FILE - What Gets Saved
-----------------------------
When parcel data is found (auto or manual), these fields are saved:

  property_details: {
    "parcel_lat": 39.264217,      <- Parcel centroid latitude
    "parcel_lon": -94.577417,     <- Parcel centroid longitude
    "parcel_zoom": 18,            <- Map zoom level
    "parcel_polygon": [           <- Boundary coordinates (if auto-detected)
      [39.265, -94.578],
      [39.264, -94.576],
      ...
    ]
  }

If parcel_polygon exists: Red boundary is drawn on the map
If parcel_polygon is missing: No boundary, just centered on coordinates


MISSING COUNTIES LOG
--------------------
When a parcel lookup fails for a new county, it's logged to:
  screener_agent/missing_counties.txt

This helps track which counties need endpoints added in the future.


ADDING NEW COUNTY ENDPOINTS
---------------------------
If you find a county with a public ArcGIS parcel service, add it to:
  screener_agent/modules/gis_utils.py

Look for COUNTY_GIS_ENDPOINTS and add an entry like:
  'county_state': {
      'name': 'County Name, ST',
      'url': 'https://...arcgis.../query',
      'use_envelope': True or False,
  }

Test the endpoint first with a known property in that county.
