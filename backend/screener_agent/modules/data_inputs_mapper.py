"""
Data Inputs Mapper - Maps all extracted data to a single Data Inputs sheet
All other sheets reference this sheet via formulas
EVERY field gets its own input cell - no sharing/duplicating references
"""

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime


class DataInputsMapper:
    """Maps extracted data to the Data Inputs sheet with source tracking."""

    SHEET_NAME = "Data Inputs"

    # Field definitions: (display_name, data_path, section)
    # data_path is dot-notation: "property.units" means extracted_data['property']['units']
    # If data_path is None, the field exists but has no auto-source (manual entry required)

    FIELD_DEFINITIONS = [
        # === PROPERTY INFO ===
        ("Property Name", "config.property_name", "property"),
        ("Street Address", "config.property_details.address", "property"),
        ("City", "config.property_details.city", "property"),
        ("State", "config.property_details.state", "property"),
        ("ZIP Code", "config.property_details.zip_code", "property"),
        ("County", "web_demographics.county", "property"),
        ("Number of Units", "property.units", "property"),
        ("Year Built", "property.vintage", "property"),
        ("Year Renovated", "property.year_renovated", "property"),
        ("Stories", "property.stories", "property"),
        ("Avg Unit Size (SF)", "property.avg_unit_size", "property"),
        ("Net Rentable SF", "formula:=C12*C16", "calculated", "Units × Avg Unit Size (SF)"),  # C12=Units, C16=Avg SF

        # === LOCATION ===
        ("Latitude", "web_demographics.latitude", "location"),
        ("Longitude", "web_demographics.longitude", "location"),
        ("Flood Zone", "web_demographics.flood_zone", "location"),
    ("Flood Risk (Yes/No)", "web_demographics.flood_risk", "location"),
        # # ("Flood Risk Level", None, "location"),  # REMOVED - Flood Zone already covers this  # REMOVED - Flood Zone already covers this

        # === DEMOGRAPHICS - 1 MILE RADIUS ===
        ("Population (1mi) - 2024", "demographics.population_1mi_2024", "demo_1mi"),
        ("Population (1mi) - 2029", "demographics.population_1mi_2029", "demo_1mi"),
        ("Population Growth % (1mi)", "demographics.population_growth_pct", "demo_1mi"),
        ("Households (1mi) - 2024", "demographics.households_1mi_2024", "demo_1mi"),
        ("Households (1mi) - 2029", "demographics.households_1mi_2029", "demo_1mi"),
        ("Household Growth % (1mi)", "demographics.household_growth_pct", "demo_1mi"),
        ("Median HH Income (1mi)", "demographics.median_hh_income_1mi", "demo_1mi"),
        ("Avg Household Size (1mi)", "demographics.avg_household_size", "demo_1mi"),
        ("Median Age (1mi)", "demographics.avg_age_1mi", "demo_1mi"),
        ("Median Home Value (1mi)", "demographics.median_home_value", "demo_1mi"),

        # === DEMOGRAPHICS - 3 MILE RADIUS ===
        ("Population (3mi) - 2024", "demographics.population_3mi_2024", "demo_3mi"),
        ("Population (3mi) - 2029", "demographics.population_3mi_2029", "demo_3mi"),
        ("Population Growth % (3mi)", "demographics.population_growth_pct_3mi", "demo_3mi"),
        ("Households (3mi) - 2024", "demographics.households_3mi_2024", "demo_3mi"),
        ("Households (3mi) - 2029", "demographics.households_3mi_2029", "demo_3mi"),
        ("Household Growth % (3mi)", "demographics.household_growth_pct_3mi", "demo_3mi"),
        ("Median HH Income (3mi)", "demographics.median_hh_income_3mi", "demo_3mi"),
        ("Avg Household Size (3mi)", "demographics.avg_household_size_3mi", "demo_3mi"),
        ("Median Age (3mi)", "demographics.avg_age_3mi", "demo_3mi"),
        ("Median Home Value (3mi)", "demographics.median_home_value_3mi", "demo_3mi"),

        # === DEMOGRAPHICS - 5 MILE RADIUS ===
        ("Population (5mi) - 2024", "demographics.population_5mi_2024", "demo_5mi"),
        ("Population (5mi) - 2029", "demographics.population_5mi_2029", "demo_5mi"),
        ("Population Growth % (5mi)", "demographics.population_growth_pct_5mi", "demo_5mi"),
        ("Households (5mi) - 2024", "demographics.households_5mi_2024", "demo_5mi"),
        ("Households (5mi) - 2029", "demographics.households_5mi_2029", "demo_5mi"),
        ("Household Growth % (5mi)", "demographics.household_growth_pct_5mi", "demo_5mi"),
        ("Median HH Income (5mi)", "demographics.median_hh_income_5mi", "demo_5mi"),
        ("Avg Household Size (5mi)", "demographics.avg_household_size_5mi", "demo_5mi"),
        ("Median Age (5mi)", "demographics.avg_age_5mi", "demo_5mi"),
        ("Median Home Value (5mi)", "demographics.median_home_value_5mi", "demo_5mi"),

        # === DEMOGRAPHICS - OTHER ===
        ("Home Ownership %", "web_demographics.home_ownership_pct", "demo_other"),
        ("Renter Occupied %", "web_demographics.renter_occupied_pct", "demo_other"),
        ("Avg HH Vehicles", "demographics.avg_hh_vehicles", "demo_other"),
        ("Median Year Built (Housing)", "demographics.median_year_built_housing", "demo_other"),

        # === SUBMARKET DATA (All from CoStar Submarket reports) ===
        ("Submarket Vacancy Rate %", "market.submarket_vacancy_rate", "submarket"),
        ("Competitor Vacancy Rate %", "demographics.competitor_vacancy_rate", "submarket"),
        ("Subject Vacancy Rate %", "property.vacancy_rate", "submarket"),
        ("12 Mo Delivered Units", "market.delivered_12mo", "submarket"),
        ("12 Mo Absorption Units", "market.absorption_12mo", "submarket"),
        ("Under Construction Units", "market.under_construction", "submarket"),
        ("Asking Rent Growth % (YoY)", "market.asking_rent_growth", "submarket"),
        ("Actual Rent Growth % (YoY)", "market.rent_growth_actual", "submarket"),
        ("Rent Growth Yr1", "market.rent_growth_projections.rent_growth_2025", "submarket"),
        ("Rent Growth Yr2", "market.rent_growth_projections.rent_growth_2026", "submarket"),
        ("Rent Growth Yr3", "market.rent_growth_projections.rent_growth_2027", "submarket"),
        ("Rent Growth Yr4", "market.rent_growth_projections.rent_growth_2028", "submarket"),
        ("Rent Growth Yr5", "market.rent_growth_projections.rent_growth_2029", "submarket"),
        ("Absorption - Property (12mo)", "demographics.absorption_12mo_property", "submarket"),
        ("Absorption - Competitors (12mo)", "demographics.absorption_12mo_competitor_total", "submarket"),
        ("Absorption - Submarket (12mo)", "demographics.absorption_12mo_submarket", "submarket"),
        ("Vacancy YoY Change %", "market.vacancy_yoy_change", "submarket", "Year-over-year vacancy change in ppts. Negative = improving (vacancy falling)"),
        ("Vacancy Historical Avg %", "market.vacancy_historical_avg", "submarket", "Long-term historical average vacancy rate for submarket"),
        ("Vacancy Forecast Avg %", "market.vacancy_forecast_avg", "submarket", "CoStar forecasted average vacancy rate"),

        # === EMPLOYMENT DATA (from CoStar Economy section) ===
        ("Employment Growth - Market", "employment.current_growth_market", "employment", "Current YoY employment growth for metro area"),
        ("Employment Growth - US", "employment.current_growth_us", "employment", "Current YoY employment growth for US (national avg)"),

        # === SCORES & RATINGS ===
        # School data - method indicates 'Assigned' (actual zoned schools) or 'District Avg'
        ("School Data Type", "web_demographics.school_ratings.school_method", "scores", "'Assigned' = actual zoned schools for address, 'District Avg' = average of all schools in district by level"),
        ("Elementary School Rating", "web_demographics.school_ratings.elementary_avg", "scores", "SchoolDigger rating 1-10 scale. Higher=better. Top 10% of state = 9-10"),
        ("Elementary School Name", "web_demographics.school_ratings.elementary_name", "scores", "Name of assigned elementary school (if Assigned) or district name (if District Avg)"),
        ("Middle School Rating", "web_demographics.school_ratings.middle_avg", "scores", "SchoolDigger rating 1-10 scale. Higher=better. Top 10% of state = 9-10"),
        ("Middle School Name", "web_demographics.school_ratings.middle_name", "scores", "Name of assigned middle school (if Assigned) or district name (if District Avg)"),
        ("High School Rating", "web_demographics.school_ratings.high_avg", "scores", "SchoolDigger rating 1-10 scale. Higher=better. Top 10% of state = 9-10"),
        ("High School Name", "web_demographics.school_ratings.high_name", "scores", "Name of assigned high school (if Assigned) or district name (if District Avg)"),
        ("Manual School Lookup", "web_demographics.greatschools_url", "scores", "GreatSchools boundary map - click to see assigned schools for this address"),
        # Crime data - tries ZIP-level first, falls back to city-level
        # Format: (field_name, data_path, section, description)
        ("Crime Data Level", "web_demographics.crime_data.source", "scores", "ZIP or City - indicates granularity of crime data"),
        # Crime Source URL removed - link now in Sources column for Crime Score
        ("Crime Score (1-10)", "web_demographics.crime_data.crime_score_avg", "scores", "1-10 scale where 5=US average. Lower=safer. Formula: (index / US avg index) × 5"),
        ("Crime Index", "web_demographics.crime_data.crime_index", "scores", "BestPlaces weighted index: (violent×0.6 + property×0.4)"),
        ("US Avg Crime Index", "web_demographics.crime_data.us_avg_index", "scores", "National average index (pulled from BestPlaces page)"),
        ("Violent Crime Index", "web_demographics.crime_data.violent_crime", "scores", "BestPlaces violent crime index (1-100 scale)"),
        ("US Avg Violent", "web_demographics.crime_data.us_avg_violent", "scores", "National avg violent crime (pulled from BestPlaces)"),
        ("Property Crime Index", "web_demographics.crime_data.property_crime", "scores", "BestPlaces property crime index (1-100 scale)"),
        ("US Avg Property", "web_demographics.crime_data.us_avg_property", "scores", "National avg property crime (pulled from BestPlaces)"),
        ("Crime Data Warning", "web_demographics.crime_data.validation_warning", "scores", "Shows if regex extracted unexpected values - CHECK IF PRESENT"),
        # ("Walk Score", "web_demographics.walkability.walk_score", "scores"),  # REMOVED per user request
        # ("Walk Score Description", "web_demographics.walkability.walk_description", "scores"),  # REMOVED
        # ("Bike Score", "web_demographics.walkability.bike_score", "scores"),  # REMOVED
        # ("Transit Score", "web_demographics.transit_score.transit_score", "scores"),  # REMOVED
        # ("Transit Description", "web_demographics.transit_score.transit_description", "scores"),  # REMOVED

        # === RENT DATA - SUBJECT ===
        ("Subject Current Rent (Avg)", "rent_comps.subject_current_rent", "rent_subject"),
        ("Subject Rent PSF", "rent_comps.subject_current_rent_psf", "rent_subject"),
        ("Subject Rent - Year Ago", "rent_comps.subject_rent_year_ago", "rent_subject"),
        ("Subject Rent - Last Quarter", "rent_comps.subject_last_quarter_rent", "rent_subject"),
        ("Subject Rent - Studio", "property.unit_mix_rents.studio", "rent_subject"),
        ("Subject Rent - 1BR", "property.unit_mix_rents.bed_1", "rent_subject"),
        ("Subject Rent - 2BR", "property.unit_mix_rents.bed_2", "rent_subject"),
        ("Subject Rent - 3BR", "property.unit_mix_rents.bed_3", "rent_subject"),
        # Unit counts by bedroom type
        ("Subject Units - Studio", "property.unit_counts.studio", "rent_subject"),
        ("Subject Units - 1BR", "property.unit_counts.bed_1", "rent_subject"),
        ("Subject Units - 2BR", "property.unit_counts.bed_2", "rent_subject"),
        ("Subject Units - 3BR", "property.unit_counts.bed_3", "rent_subject"),

        # === RENT DATA - MARKET ===
        ("Avg Comp Rent/Unit", "rent_comps.avg_comp_rent_per_unit", "rent_market"),
        ("Avg Comp Rent PSF", "rent_comps.avg_comp_rent_psf", "rent_market"),
        ("Submarket Avg Rent", "demographics.submarket_avg_rent", "rent_market"),

        # === STAGE 2 CALCULATED SCORES ===
        # Supply-Demand Drivers (5% weight in Stage 2)
        ("SD: Absorption (12mo)", "stage2_scores.supply_demand.absorption_12mo", "stage2_scores", "Units absorbed in submarket over trailing 12 months (CoStar pg 58)"),
        ("SD: Delivered (12mo)", "stage2_scores.supply_demand.delivered_12mo", "stage2_scores", "New units delivered in submarket over trailing 12 months (CoStar pg 58)"),
        ("SD: Under Construction", "stage2_scores.supply_demand.under_construction", "stage2_scores", "Units currently under construction in submarket - future supply pressure"),
        ("SD: Absorption Ratio", "stage2_scores.supply_demand.absorption_ratio", "stage2_scores", "Absorption / Delivered. Measures if market absorbs new supply. >2.0=strong demand, 1.0=balanced, <0.5=oversupply"),
        ("SD: Pipeline Ratio", "stage2_scores.supply_demand.pipeline_ratio", "stage2_scores", "Under Construction / Absorption. Measures future supply pressure. >1.5=heavy pipeline risk, <0.5=light pipeline"),
        ("SD: Base Score", "stage2_scores.supply_demand.base_score", "stage2_scores", "SCALE: Ratio>=2.0=10, 1.5-2.0=8, 1.0-1.5=6, 0.5-1.0=4, <0.5=2. Negative absorption caps at 3"),
        ("SD: Pipeline Adjustment", "stage2_scores.supply_demand.pipeline_adjustment", "stage2_scores", "Pipeline penalty/bonus: >1.5x absorption=-2, >1.0x=-1, <0.5x=+1. Adjusts for future supply wave"),
        ("SD: Final Score", "stage2_scores.supply_demand.final_score", "stage2_scores", "SUPPLY-DEMAND DRIVERS (5% wt). Base+Adj capped 1-10. High=demand outpaces supply, Low=oversupply risk"),
        ("SD: Notes", "stage2_scores.supply_demand.notes", "stage2_scores", "Auto-generated explanation of score factors"),
        # Submarket Supply-Demand Outlook (10% weight)
        ("SO: Current Vacancy %", "stage2_scores.submarket_outlook.current_vacancy", "stage2_scores", "Current submarket vacancy rate"),
        ("SO: Vacancy YoY Change", "stage2_scores.submarket_outlook.vacancy_yoy_change", "stage2_scores", "Year-over-year vacancy change. Negative=improving (vacancy falling)"),
        ("SO: Historical Avg Vacancy", "stage2_scores.submarket_outlook.vacancy_historical_avg", "stage2_scores", "Long-term historical avg vacancy for this submarket"),
        ("SO: Vacancy vs Historical", "stage2_scores.submarket_outlook.vacancy_vs_historical", "stage2_scores", "Current minus Historical. Negative=below normal (good), Positive=above normal (bad)"),
        ("SO: Level Adjustment", "stage2_scores.submarket_outlook.level_adjustment", "stage2_scores", "SCALE: >2ppts below hist=+2, 0.5-2 below=+1, within 0.5=0, 0.5-2 above=-1, >2 above=-2"),
        ("SO: Trend Adjustment", "stage2_scores.submarket_outlook.trend_adjustment", "stage2_scores", "SCALE: YoY<=-1%=+3, -0.5 to -1%=+2, 0 to -0.5%=+1, 0=0, 0-0.5%=-1, 0.5-1%=-2, >1%=-3"),
        ("SO: Pipeline Ratio", "stage2_scores.submarket_outlook.pipeline_ratio", "stage2_scores", "Under Construction / Absorption. Future supply pressure indicator"),
        ("SO: Pipeline Adjustment", "stage2_scores.submarket_outlook.pipeline_adjustment", "stage2_scores", "SCALE: <0.5x=+1, 0.5-1x=0, 1-1.5x=-1, >1.5x=-2"),
        ("SO: Final Score", "stage2_scores.submarket_outlook.final_score", "stage2_scores", "SUBMARKET OUTLOOK (10% wt). Base 5 + adjustments, capped 1-10. High=improving/tight, Low=worsening/loose"),
        ("SO: Notes", "stage2_scores.submarket_outlook.notes", "stage2_scores", "Auto-generated breakdown of all adjustment factors"),
        # Migration / GDP Growth (3% weight)
        ("MG: Employment Growth - Market", "stage2_scores.migration_gdp.emp_growth_market", "stage2_scores", "Current YoY job growth for metro area (from CoStar Economy)"),
        ("MG: Employment Growth - US", "stage2_scores.migration_gdp.emp_growth_us", "stage2_scores", "Current YoY job growth for US (national benchmark)"),
        ("MG: Employment vs US", "stage2_scores.migration_gdp.emp_vs_us", "stage2_scores", "Market minus US. Positive=outperforming, Negative=underperforming"),
        ("MG: Employment Score", "stage2_scores.migration_gdp.emp_score", "stage2_scores", "SCALE: >=+1% vs US=10, +0.5-1%=8, 0-0.5%=6, 0 to -0.5%=5, -0.5 to -1%=4, -1 to -1.5%=3, <-1.5%=2"),
        ("MG: Pop Growth (5mi)", "stage2_scores.migration_gdp.pop_growth_5mi", "stage2_scores", "5-year population growth projection for 5-mile radius (migration proxy)"),
        ("MG: Population Score", "stage2_scores.migration_gdp.pop_score", "stage2_scores", "SCALE: >=10%=10, 8-10%=9, 6-8%=8, 4-6%=7, 2-4%=6, 0-2%=5, -2-0%=4, <-2%=2"),
        ("MG: Final Score", "stage2_scores.migration_gdp.final_score", "stage2_scores", "MIGRATION/GDP (3% wt). Avg of Emp+Pop scores. High=strong jobs+migration, Low=weak economy"),
        ("MG: Notes", "stage2_scores.migration_gdp.notes", "stage2_scores", "Auto-generated breakdown: employment score | population score"),
        # Parking Ratio (3% weight)
        ("PR: Parking Ratio", "stage2_scores.parking.parking_ratio", "stage2_scores", "Parking spaces per unit (from CoStar Property)"),
        ("PR: Parking Spaces", "stage2_scores.parking.parking_spaces", "stage2_scores", "Total parking spaces"),
        ("PR: Surface Spaces", "stage2_scores.parking.surface_spaces", "stage2_scores", "Surface lot parking spaces"),
        ("PR: Covered Spaces", "stage2_scores.parking.covered_spaces", "stage2_scores", "Covered/garage parking spaces"),
        ("PR: Units", "stage2_scores.parking.units", "stage2_scores", "Total units"),
        ("PR: Base Score", "stage2_scores.parking.base_score", "stage2_scores", "SCALE: >=2.0=10, 1.5-2.0=9, 1.25-1.5=8, 1.0-1.25=7, 0.75-1.0=5, 0.5-0.75=3, <0.5=2"),
        ("PR: Underground Penalty", "stage2_scores.parking.underground_penalty", "stage2_scores", "-1 if underground/garage only (no surface parking)"),
        ("PR: Final Score", "stage2_scores.parking.final_score", "stage2_scores", "PARKING RATIO (3% wt). Base score + underground penalty, capped 1-10"),
        ("PR: Notes", "stage2_scores.parking.notes", "stage2_scores", "Auto-generated score explanation"),
        # Amenities & Lifestyle (5% weight)
        ("AM: Site Score", "stage2_scores.amenities.site_score", "stage2_scores", "Site amenities pts (max 5). Pool/Fitness/Clubhouse=1ea, Business/Playground/Dog Park=0.5ea"),
        ("AM: Unit Score", "stage2_scores.amenities.unit_score", "stage2_scores", "Unit amenities pts (max 5). In-Unit W/D=1.5, AC=1, Dishwasher/Balcony/Walk-In=0.5ea"),
        ("AM: Final Score", "stage2_scores.amenities.final_score", "stage2_scores", "AMENITIES (5% wt). Site+Unit scores, capped 1-10. See score_calculator.py for full point values"),
        ("AM: Notes", "stage2_scores.amenities.notes", "stage2_scores", "Auto-generated breakdown: site score | unit score"),
        # Unit Mix & Size (5% weight)
        ("UM: Total Units", "stage2_scores.unit_mix.total_units", "stage2_scores", "Total number of units"),
        ("UM: 2-3BR Units", "stage2_scores.unit_mix.units_2_3_br", "stage2_scores", "Count of 2BR + 3BR units"),
        ("UM: 2-3BR %", "stage2_scores.unit_mix.pct_2_3_br", "stage2_scores", "Percentage of units that are 2-3 bedrooms"),
        ("UM: Avg SF", "stage2_scores.unit_mix.avg_sf", "stage2_scores", "Average unit size in square feet"),
        ("UM: Size Score", "stage2_scores.unit_mix.size_score", "stage2_scores", "SCALE: >=1000sf=10, 900-1000=8, 800-900=6, 700-800=4, <700=2"),
        ("UM: Mix Score", "stage2_scores.unit_mix.mix_score", "stage2_scores", "SCALE: >=70% 2-3BR=10, 60-70%=8, 50-60%=6, 40-50%=4, <40%=3"),
        ("UM: Final Score", "stage2_scores.unit_mix.final_score", "stage2_scores", "UNIT MIX (5% wt). Avg of Size+Mix scores. High=family-friendly units, Low=small/studio-heavy"),
        ("UM: Notes", "stage2_scores.unit_mix.notes", "stage2_scores", "Auto-generated breakdown: size score | mix score"),
        # Loss-to-Lease (10% weight)
        ("LTL: Subject Rent", "stage2_scores.loss_to_lease.subject_rent", "stage2_scores", "Subject property average rent per unit"),
        ("LTL: Comp Avg Rent", "stage2_scores.loss_to_lease.comp_avg_rent", "stage2_scores", "Average rent of comparable properties"),
        ("LTL: Submarket Rent", "stage2_scores.loss_to_lease.submarket_rent", "stage2_scores", "Submarket average rent"),
        ("LTL: vs Comps %", "stage2_scores.loss_to_lease.ltl_vs_comps_pct", "stage2_scores", "(Subject-Comps)/Comps. Negative=below market, Positive=above market"),
        ("LTL: vs Submarket %", "stage2_scores.loss_to_lease.ltl_vs_submarket_pct", "stage2_scores", "(Subject-Submarket)/Submarket. Negative=below market, Positive=above market"),
        ("LTL: Blended %", "stage2_scores.loss_to_lease.blended_ltl_pct", "stage2_scores", "Weighted avg: 60% vs Comps + 40% vs Submarket"),
        ("LTL: Final Score", "stage2_scores.loss_to_lease.final_score", "stage2_scores", "LOSS-TO-LEASE (10% wt). SCALE: <=-20%=10, -15 to -20=9, -10 to -15=8, -5 to -10=7, -2.5 to -5=6, +/-2.5%=5, +2.5 to +5=4, +5 to +10=3, +10 to +15=2, +15 to +20=1, >+20%=0"),
        ("LTL: Notes", "stage2_scores.loss_to_lease.notes", "stage2_scores", "Auto-generated breakdown: vs comps | vs submarket | blended"),
        # Business-Friendly Environment (3% weight)
        ("BF: State", "stage2_scores.business_friendly.state", "stage2_scores", "State from property address"),
        ("BF: Final Score", "stage2_scores.business_friendly.final_score", "stage2_scores", "BUSINESS-FRIENDLY (3% wt). State lookup: TX/FL/TN/AZ=10, GA/NC/SC/NV/IN=9, KS/MO/OH/UT/OK/AL=8, CO/ID/KY/AR/NE=7, PA/MI/WI/VA/IA=6, IL/MN/NM=5, WA/MD/NH/DE=4, MA/NJ/CT/HI=3, NY/VT/RI=2, CA/OR/DC=1"),
        ("BF: Notes", "stage2_scores.business_friendly.notes", "stage2_scores", "Auto-generated explanation of state regulatory environment"),
        # Nearby Nuisance Properties (3% weight) - Counts for Excel-based scoring
        ("NU: Source", "stage2_scores.nuisance.source", "stage2_scores", "Data source for nuisance detection"),
        ("NU: Severe Count", "stage2_scores.nuisance.severe_count", "stage2_scores", "Count of severe nuisances within 1mi (prison, landfill, waste facility)"),
        ("NU: Industrial Count", "stage2_scores.nuisance.industrial_count", "stage2_scores", "Count of industrial areas within 0.5mi"),
        ("NU: Moderate Count", "stage2_scores.nuisance.moderate_count", "stage2_scores", "Count of moderate nuisances within 0.25mi (motel, storage, pawn, liquor, shelter)"),
        ("NU: Minor Count", "stage2_scores.nuisance.minor_count", "stage2_scores", "Count of minor nuisances within 500ft (gas station, auto repair)"),
        ("NU: Nuisances List", "stage2_scores.nuisance.nuisances_list", "stage2_scores", "Nuisances found with names for verification (e.g., 'industrial area (YRC Freight)')"),
        ("NU: Python Score", "stage2_scores.nuisance.python_score", "stage2_scores", "Reference score from Python (Excel recalculates with editable weights)"),
        ("NU: Notes", "stage2_scores.nuisance.notes", "stage2_scores", "Auto-generated summary of detected nuisances by category"),
        # Climate Risk (5% weight) - Uses FEMA flood + USDA fire + Open-Meteo heat/cold
        ("CR: Source", "stage2_scores.climate_risk.source", "stage2_scores", "Data source: FEMA + USDA + Open-Meteo"),
        ("CR: Flood Zone", "stage2_scores.climate_risk.flood_zone", "stage2_scores", "FEMA flood zone code (X=minimal, A/AE=high, V/VE=coastal high)"),
        ("CR: Flood Zone Desc", "stage2_scores.climate_risk.flood_zone_desc", "stage2_scores", "Full description of flood zone classification"),
        ("CR: Is SFHA", "stage2_scores.climate_risk.flood_is_sfha", "stage2_scores", "Special Flood Hazard Area (True=high risk, requires flood insurance)"),
        ("CR: Flood Score", "stage2_scores.climate_risk.flood_score", "stage2_scores", "Flood risk score 1-10 (10=Zone X, 2=Zone A/AE, 1=Zone V/VE) - 50% weight"),
        ("CR: Fire Burn Prob", "stage2_scores.climate_risk.fire_burn_probability", "stage2_scores", "Annual burn probability (0.01 = 1% chance of fire per year)"),
        ("CR: Fire Score", "stage2_scores.climate_risk.fire_score", "stage2_scores", "Fire risk score 1-10 (10=<0.01% prob, 1=>5% prob) - 20% weight"),
        ("CR: Heat Days", "stage2_scores.climate_risk.heat_days", "stage2_scores", "Avg days per year with max temp >90F (32C)"),
        ("CR: Heat Score", "stage2_scores.climate_risk.heat_score", "stage2_scores", "Heat risk score 1-10 (10=<10 days, 1=>150 days) - 15% weight"),
        ("CR: Cold Days", "stage2_scores.climate_risk.cold_days", "stage2_scores", "Avg days per year with min temp <32F (0C)"),
        ("CR: Cold Score", "stage2_scores.climate_risk.cold_score", "stage2_scores", "Cold risk score 1-10 (10=<15 days, 1=>180 days) - 15% weight"),
        ("CR: Final Score", "stage2_scores.climate_risk.final_score", "stage2_scores", "CLIMATE RISK (5% wt). Weighted: 50% flood + 20% fire + 15% heat + 15% cold"),
        ("CR: Notes", "stage2_scores.climate_risk.notes", "stage2_scores", "Auto-generated breakdown: flood | fire | heat days | cold days"),
        # Employer Stability / Recession Resistance (5% weight) - Uses BLS QCEW employment data
        # Source is determined dynamically in _get_nested_value() based on field type
        ("ES: Source", "stage2_scores.employer_stability.source", "stage2_scores", "Data source: BLS QCEW (Quarterly Census of Employment and Wages)"),
        ("ES: County FIPS", "stage2_scores.employer_stability.county_fips", "stage2_scores", "5-digit county FIPS code for employment data lookup"),
        ("ES: County Name", "stage2_scores.employer_stability.county_name", "stage2_scores", "County name where property is located"),
        ("ES: State", "stage2_scores.employer_stability.state", "stage2_scores", "State abbreviation"),
        ("ES: Total Employment", "stage2_scores.employer_stability.total_employment", "stage2_scores", "Total county employment (all sectors)"),
        ("ES: Government %", "stage2_scores.employer_stability.government_pct", "stage2_scores", "% of jobs in government (federal + state + local)"),
        ("ES: Recession-Proof %", "stage2_scores.employer_stability.recession_proof_pct", "stage2_scores", "% in healthcare, education, utilities (stable during recessions)"),
        ("ES: Essential %", "stage2_scores.employer_stability.essential_pct", "stage2_scores", "% in retail, transportation, wholesale (essential services)"),
        ("ES: Moderate %", "stage2_scores.employer_stability.moderate_pct", "stage2_scores", "% in finance, professional services, admin (moderate stability)"),
        ("ES: Cyclical %", "stage2_scores.employer_stability.cyclical_pct", "stage2_scores", "% in construction, manufacturing, hospitality (first to layoff)"),
        ("ES: RRI", "stage2_scores.employer_stability.rri", "stage2_scores", "Recession Resistance Index: stable% + 0.6*essential% + 0.3*moderate% - 0.4*cyclical%"),
        ("ES: Concentration Adj", "stage2_scores.employer_stability.concentration_adj", "stage2_scores", "Adjustment for industry concentration (-1.5 if >35% in one industry)"),
        ("ES: Final Score", "stage2_scores.employer_stability.final_score", "stage2_scores", "EMPLOYER STABILITY (5% wt). Based on RRI + concentration adjustment"),
        ("ES: Notes", "stage2_scores.employer_stability.notes", "stage2_scores", "Auto-generated: stable% breakdown | concentration analysis"),
    ]

    def __init__(self):
        """Initialize the mapper."""
        self.source_tracking = {}

    def _get_nested_value(self, data: Dict, path: str) -> Tuple[Any, str]:
        """
        Get a value from nested dictionary using dot notation.
        Returns (value, source) tuple.

        Special handling for formula paths starting with "formula:".
        """
        if path is None:
            return None, None

        # Handle formula fields - return the formula as value with explanation as source
        if path.startswith('formula:'):
            formula = path[8:]  # Remove "formula:" prefix
            # Create human-readable explanation of the formula
            formula_explanation = formula.replace('=', '').replace('*', ' × ')
            # Map cell references to field names for clarity
            formula_explanation = formula_explanation.replace('C12', '[Units]').replace('C16', '[Avg SF]')
            return formula, f"Formula: {formula_explanation}"

        parts = path.split('.')
        current = data
        source = parts[0]  # First part is the data source category

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None, None

        # Determine source label
        source_labels = {
            'config': 'Config',
            'property': 'CoStar Property',
            'demographics': 'CoStar Demographics',
            'market': 'CoStar Submarket',  # All market data comes from submarket reports
            'submarket': 'CoStar Submarket',
            'employment': 'CoStar Economy',  # Employment data from Economy section
            'rent_comps': 'CoStar Rent Comps',
            'sale_comps': 'CoStar Sale Comps',
            'web_demographics': 'Web Scraping',
            'calculated': 'Auto-Generated',
            'stage2_scores': 'Calculated',
        }

        source_label = source_labels.get(source, source)

        # Try to get page number from _page_sources
        page_num = None
        field_key = parts[-1]  # Default: last part of path

        if source in ['market', 'submarket']:
            market_data = data.get('market', {})
            page_sources = market_data.get('_page_sources', {})
            # Handle nested paths like rent_growth_projections.rent_growth_2025
            if 'rent_growth_projections' in path and len(parts) > 2:
                field_key = parts[-1]  # e.g., 'rent_growth_2025'
            page_num = page_sources.get(field_key)

        elif source == 'property':
            property_data = data.get('property', {})
            page_sources = property_data.get('_page_sources', {})
            # Handle nested paths like unit_mix_rents.studio
            if 'unit_mix_rents' in path:
                full_key = '.'.join(parts[1:])  # e.g., "unit_mix_rents.studio"
                page_num = page_sources.get(full_key, page_sources.get(field_key))
            else:
                page_num = page_sources.get(field_key)

        elif source == 'subject_property':
            subject_data = data.get('subject_property', {})
            page_sources = subject_data.get('_page_sources', {})
            page_num = page_sources.get(field_key)

        elif source == 'demographics':
            demo_data = data.get('demographics', {})
            page_sources = demo_data.get('_page_sources', {})
            page_num = page_sources.get(field_key)

        elif source == 'rent_comps':
            rent_data = data.get('rent_comps', {})
            page_sources = rent_data.get('_page_sources', {})
            page_num = page_sources.get(field_key)

        elif source == 'sale_comps':
            sale_data = data.get('sale_comps', {})
            page_sources = sale_data.get('_page_sources', {})
            page_num = page_sources.get(field_key)

        elif source == 'employment':
            emp_data = data.get('employment', {})
            page_sources = emp_data.get('_page_sources', {})
            page_num = page_sources.get('employment')  # All employment fields use same page

        # Append page number to source label if available
        if page_num:
            source_label = f"{source_label} (pg {page_num})"

        # More specific source if available (with URLs for hyperlinks)
        source_url = None
        if source == 'web_demographics':
            if 'school' in path:
                school_data = data.get('web_demographics', {}).get('school_ratings', {})
                if school_data:
                    if school_data.get('source'):
                        source_label = school_data['source']
                    if school_data.get('source_url'):
                        source_url = school_data['source_url']
            elif 'crime' in path:
                source_label = 'BestPlaces.net'
                # Could add crime URL here if stored
                crime_data = data.get('web_demographics', {}).get('crime_data', {})
                if crime_data.get('source_url'):
                    source_url = crime_data['source_url']
            elif 'walkability' in path or 'walk' in path.lower():
                walk_data = data.get('web_demographics', {}).get('walkability', {})
                if walk_data and walk_data.get('source'):
                    source_label = walk_data['source']
                else:
                    source_label = 'Walk Score'
            elif 'transit' in path:
                transit_data = data.get('web_demographics', {}).get('transit_score', {})
                if transit_data and transit_data.get('source'):
                    source_label = transit_data['source']
            elif 'flood' in path:
                source_label = 'FEMA API'
                # Add FEMA map URL if we have address info
                flood_url = data.get('web_demographics', {}).get('flood_source_url')
                if flood_url:
                    source_url = flood_url
            elif 'home_ownership' in path or 'renter_occupied' in path:
                source_label = 'Census API'  # Both come from same Census source

        # Special handling for employer_stability (stage2_scores) to show actual API sources
        elif source == 'stage2_scores' and 'employer_stability' in path:
            # County lookup fields come from FCC Census API
            if any(x in path for x in ['county_fips', 'county_name', 'state']):
                source_label = 'FCC Census API'
            # Raw employment data comes from BLS QCEW API
            elif any(x in path for x in ['total_employment', 'government_pct', 'recession_proof_pct',
                                          'essential_pct', 'moderate_pct', 'cyclical_pct']):
                source_label = 'BLS QCEW API'
            # Calculated fields derived from BLS data
            elif any(x in path for x in ['rri', 'concentration_adj', 'final_score', 'base_score']):
                source_label = 'Calculated (BLS)'
            elif 'source' in path:
                source_label = 'BLS QCEW API'
            else:
                source_label = 'BLS QCEW API'  # Default for employer_stability

        # Return source as dict if URL available, otherwise just the label string
        if source_url:
            return current, {'label': source_label, 'url': source_url}
        return current, source_label

    def map_to_data_inputs(self, extracted_data: Dict[str, Any], config: Dict[str, Any]) -> List[Tuple[int, str, Any, str]]:
        """
        Map extracted data to Data Inputs sheet rows.

        Returns list of tuples: (row_number, field_name, value, source)
        Only returns rows where we have actual data (no None values).
        """
        # Combine config into extracted_data for unified access
        combined_data = {**extracted_data}
        combined_data['config'] = config

        # Note: Net Rentable SF is now calculated via Excel formula (=C12*C16)
        # for full transparency - no hidden Python calculations

        updates = []
        current_row = 4
        current_section = None

        for field_def in self.FIELD_DEFINITIONS:
            # Handle both 3-element and 4-element tuples (with optional description)
            field_name = field_def[0]
            data_path = field_def[1]
            section = field_def[2]
            description = field_def[3] if len(field_def) > 3 else None

            # Track section changes for row calculation
            if section != current_section:
                current_row += 2  # Section header + blank row
                current_section = section

            # Get value and source (only if data_path is defined)
            if data_path:
                value, source = self._get_nested_value(combined_data, data_path)

                # Only add if we have a real value (not None, not empty string)
                if value is not None and value != '':
                    updates.append((current_row, field_name, value, source, description))

            current_row += 1

        return updates

    def get_cell_references(self) -> Dict[str, str]:
        """
        Get cell references for each field in the Data Inputs sheet.
        Returns dict mapping field_name to cell reference like 'C5'.
        """
        references = {}
        current_row = 4
        current_section = None

        for field_def in self.FIELD_DEFINITIONS:
            field_name = field_def[0]
            section = field_def[2]

            if section != current_section:
                current_row += 2
                current_section = section

            references[field_name] = f"C{current_row}"
            current_row += 1

        return references


def get_formula_mappings() -> Dict[str, Tuple[str, str]]:
    """
    Define formulas for other sheets that reference Data Inputs.
    Returns dict: {(sheet, cell): formula}

    IMPORTANT: Every output cell references its OWN input cell - no sharing!
    """
    mapper = DataInputsMapper()
    refs = mapper.get_cell_references()

    # Build formulas - each references a UNIQUE input cell
    # Sources are in column D of Data Inputs (value is in C, source is in D)
    formulas = {
        # Screener Cover (labels in B, values in C, SOURCES in D)
        # Row 5: Project Name
        ('Screener Cover', 'C5'): f"='Data Inputs'!{refs['Property Name']}",
        ('Screener Cover', 'D5'): f"='Data Inputs'!D{refs['Property Name'][1:]}",
        # Row 6: Address
        ('Screener Cover', 'C6'): f"='Data Inputs'!{refs['Street Address']}",
        ('Screener Cover', 'D6'): f"='Data Inputs'!D{refs['Street Address'][1:]}",
        # Row 7: City
        ('Screener Cover', 'C7'): f"='Data Inputs'!{refs['City']}",
        ('Screener Cover', 'D7'): f"='Data Inputs'!D{refs['City'][1:]}",
        # Row 8: State
        ('Screener Cover', 'C8'): f"='Data Inputs'!{refs['State']}",
        ('Screener Cover', 'D8'): f"='Data Inputs'!D{refs['State'][1:]}",
        # Row 9: # of Units
        ('Screener Cover', 'C9'): f"='Data Inputs'!{refs['Number of Units']}",
        ('Screener Cover', 'D9'): f"='Data Inputs'!D{refs['Number of Units'][1:]}",
        # Row 10: Vintage
        ('Screener Cover', 'C10'): f"='Data Inputs'!{refs['Year Built']}",
        ('Screener Cover', 'D10'): f"='Data Inputs'!D{refs['Year Built'][1:]}",
        # Column F - Rent data (sources in G)
        # Row 5: AVG Rent Per Unit
        ('Screener Cover', 'F5'): f"='Data Inputs'!{refs['Subject Current Rent (Avg)']}",
        ('Screener Cover', 'G5'): f"='Data Inputs'!D{refs['Subject Current Rent (Avg)'][1:]}",
        # Row 6: AVG Rent Per SF
        ('Screener Cover', 'F6'): f"='Data Inputs'!{refs['Subject Rent PSF']}",
        ('Screener Cover', 'G6'): f"='Data Inputs'!D{refs['Subject Rent PSF'][1:]}",
        # Row 7: AVG SF Per Unit
        ('Screener Cover', 'F7'): f"='Data Inputs'!{refs['Avg Unit Size (SF)']}",
        ('Screener Cover', 'G7'): f"='Data Inputs'!D{refs['Avg Unit Size (SF)'][1:]}",

        # Stage 1 - Demographics (1mi)
        ('Stage 1', 'D8'): f"='Data Inputs'!{refs['Median HH Income (1mi)']}",
        # Stage 1 - Demographics (3mi) - SEPARATE cell
        ('Stage 1', 'D9'): f"='Data Inputs'!{refs['Median HH Income (3mi)']}",

        # Population Growth - 1mi
        ('Stage 1', 'D33'): f"='Data Inputs'!{refs['Population Growth % (1mi)']}/100",
        # Population Growth - 3mi - SEPARATE cell
        ('Stage 1', 'D34'): f"='Data Inputs'!{refs['Population Growth % (3mi)']}/100",

        # Home Ownership
        ('Stage 1', 'D24'): f"='Data Inputs'!{refs['Home Ownership %']}/100",

        # Schools
        ('Stage 1', 'D41'): f"='Data Inputs'!{refs['High School Rating']}",
        ('Stage 1', 'D42'): f"='Data Inputs'!{refs['Middle School Rating']}",
        ('Stage 1', 'D43'): f"='Data Inputs'!{refs['Elementary School Rating']}",

        # Flood
        ('Stage 1', 'D48'): f"='Data Inputs'!{refs['Flood Zone']}",

        # Rent Growth Projections (CoStar EST) - 5 Year
        ('Stage 1', 'D64'): f"='Data Inputs'!{refs['Rent Growth Yr1']}/100",
        ('Stage 1', 'E65'): f"='Data Inputs'!{refs['Rent Growth Yr2']}/100",
        ('Stage 1', 'F65'): f"='Data Inputs'!{refs['Rent Growth Yr3']}/100",
        ('Stage 1', 'G65'): f"='Data Inputs'!{refs['Rent Growth Yr4']}/100",
        ('Stage 1', 'H65'): f"='Data Inputs'!{refs['Rent Growth Yr5']}/100",

        # Crime - use the 1-10 score (ZIP or City level)
        ('Stage 1', 'D71'): f"='Data Inputs'!{refs['Crime Score (1-10)']}",

        # Submarket Occupancy (calculated from vacancy)
        ('Stage 1', 'D101'): f"=1-'Data Inputs'!{refs['Submarket Vacancy Rate %']}/100",

        # Rent Comps
        ('Rent Comps', 'E3'): f"='Data Inputs'!{refs['Avg Comp Rent/Unit']}",
    }

    return formulas
