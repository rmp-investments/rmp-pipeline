"""
Complete Data Mapper - Maps ALL available data to Excel screener
Includes calculated fields and comprehensive mappings
"""

from typing import Dict, Any, List, Tuple


class ScreenerDataMapper:
    """Complete mapper with calculations and all available field mappings."""

    def __init__(self):
        """Initialize mapper with field definitions."""
        self.field_mappings = self._define_mappings()

    def _define_mappings(self) -> Dict[str, Tuple[str, str, str]]:
        """
        Define mappings: {field_name: (data_category, sheet, cell)}
        """
        return {
            # === COVER SHEET ===
            'units': ('property', 'Screener Cover', 'C8'),
            'vintage': ('property', 'Screener Cover', 'C9'),
            'avg_unit_size': ('property', 'Screener Cover', 'F6'),
            'subject_current_rent': ('rent_comps', 'Screener Cover', 'F4'),
            'subject_current_rent_psf': ('rent_comps', 'Screener Cover', 'F5'),
            # F7 (Net Rental SF) will be calculated

            # === STAGE 1 - DEMOGRAPHICS ===
            'median_hh_income_1mi': ('demographics', 'Stage 1', 'D8'),
            # D9 will use same value as D8 (we only have 1-mile data)
            # D33, D34 population growth - calculated (need decimal conversion)
            # D64 rent growth - calculated (need decimal conversion)
            # D101 submarket occupancy - calculated (from vacancy rate)
            # Note: flood_risk and home_ownership_pct handled in special mappings section
            # 'flood_risk': ('web_demographics', 'Stage 1', 'D48'),  # Moved to special handling
            # 'home_ownership_pct': ('web_demographics', 'Stage 1', 'D24'),  # Moved to special handling
            # D67 Crime (crime grade like A+)
            # D71 Neighborhood Crime Score (crime index number)
            # D37 School Ranking
            # D39 Great Schools out of 10
            # D40 Assigned Schools Rating

            # === RENT COMPS ===
            'avg_comp_rent_per_unit': ('rent_comps', 'Rent Comps', 'E3'),
            'subject_current_rent_comp': ('rent_comps', 'Rent Comps', 'E4'),
            'subject_current_rent_psf_comp': ('rent_comps', 'Rent Comps', 'G4'),
            # G3 will be calculated from avg_comp_rent_per_unit

            # === METADATA/REFERENCE (not mapped to specific cells, stored in metadata) ===
            'population_1mi_2024': ('demographics', 'Comments', 'Comments'),
            'household_growth_pct': ('demographics', 'Comments', 'Comments'),
            'competitor_vacancy_rate': ('demographics', 'Comments', 'Comments'),
            'competitor_avg_rent': ('demographics', 'Comments', 'Comments'),
            'submarket_vacancy_rate': ('demographics', 'Comments', 'Comments'),
            'submarket_avg_rent': ('demographics', 'Comments', 'Comments'),
            'market_vacancy_rate': ('market', 'Comments', 'Comments'),
            'delivered_12mo': ('market', 'Comments', 'Comments'),
            'absorption_12mo': ('market', 'Comments', 'Comments'),
            'under_construction': ('market', 'Comments', 'Comments'),
            'land_area_acres': ('property', 'Comments', 'Comments'),
            'construction_type': ('property', 'Comments', 'Comments'),
            'parking_ratio': ('property', 'Comments', 'Comments'),
            'stories': ('property', 'Comments', 'Comments'),
            'vacancy_rate': ('property', 'Comments', 'Comments'),
        }

    def map_extracted_data(self, extracted_data: Dict[str, Any], config: Dict[str, Any] = None) -> List[Tuple[str, str, Any]]:
        """
        Map extracted data to Excel cell updates, including calculated fields.

        Args:
            extracted_data: Dictionary of all extracted data from various sources
            config: Optional config dict with property details (name, address, etc)

        Returns:
            List of tuples: (sheet_name, cell, value)
        """
        updates = []

        # Add fields from config if provided
        if config and 'property_details' in config:
            pd = config['property_details']
            updates.append(('Screener Cover', 'C4', pd.get('property_name', config.get('property_name'))))
            if pd.get('address'):
                updates.append(('Screener Cover', 'C5', pd['address']))
            if pd.get('city'):
                updates.append(('Screener Cover', 'C6', pd['city']))
            if pd.get('state'):
                updates.append(('Screener Cover', 'C7', pd['state']))

        # Map direct fields
        for category, data in extracted_data.items():
            if not isinstance(data, dict):
                continue

            for field_name, value in data.items():
                if value is None or isinstance(value, (dict, list)):
                    continue

                if field_name in self.field_mappings:
                    expected_category, sheet, cell = self.field_mappings[field_name]

                    if category == expected_category and cell != 'Comments':
                        updates.append((sheet, cell, value))

        # === CALCULATED FIELDS ===
        calculated = self._calculate_fields(extracted_data)
        updates.extend(calculated)

        # === WEB DEMOGRAPHICS - SPECIAL HANDLING FOR NESTED DICTS ===
        web_demo = extracted_data.get('web_demographics', {})

        # Home Ownership % - convert to decimal (74.26 -> 0.7426)
        if web_demo.get('home_ownership_pct'):
            home_ownership = web_demo['home_ownership_pct']
            if isinstance(home_ownership, (int, float)):
                # Convert from percentage to decimal for Excel percentage formatting
                home_ownership_decimal = home_ownership / 100
                updates.append(('Stage 1', 'D24', home_ownership_decimal))

        # Flood Risk - ONLY fill D48 (FEMA Flood Risk via CoStar), NOT D46
        # D48 is not blue but user wants it filled
        if web_demo.get('flood_risk'):
            flood_risk = web_demo['flood_risk']
            updates.append(('Stage 1', 'D48', flood_risk))  # FEMA Flood Risk Via CoStar

        # Crime data (nested dict) - ONLY fill D71 (Neighborhood Crime Score), NOT D67
        crime_data = web_demo.get('crime_data', {})
        if isinstance(crime_data, dict):
            # D67 (Crime grade) is NOT blue - don't fill
            # D71 (Neighborhood Crime Score) IS blue - fill with numeric crime index
            if crime_data.get('crime_index'):
                updates.append(('Stage 1', 'D71', crime_data['crime_index']))  # Crime score (numeric)

        # School ratings (nested dict)
        # D37, D39, D40 are NOT blue cells - don't fill
        # Schools would need to be manually entered or from a different source

        # Walkability (nested dict)
        walk_data = web_demo.get('walkability', {})
        if isinstance(walk_data, dict):
            if walk_data.get('walk_score'):
                # Store in metadata for now (no clear cell mapping found yet)
                pass

        # === DUPLICATE MAPPINGS (same data to multiple cells) ===
        demo = extracted_data.get('demographics', {})

        # Median HH Income: D9 (3-mile) - use real 3-mile data if available, else fallback to 1-mile
        if demo.get('median_hh_income_3mi'):
            updates.append(('Stage 1', 'D9', demo['median_hh_income_3mi']))
        elif demo.get('median_hh_income_1mi'):
            updates.append(('Stage 1', 'D9', demo['median_hh_income_1mi']))

        # Population Growth - ONLY fill BLUE input cells (D33, D34)
        # D29, D32 are NOT blue - don't fill
        if demo.get('population_growth_pct'):
            # D33: Pop Growth % (1-mile) - BLUE cell
            updates.append(('Stage 1', 'D33', demo['population_growth_pct'] / 100))

        # D34: 3-Mile Radius population growth - BLUE cell
        if demo.get('population_growth_3mi_pct'):
            updates.append(('Stage 1', 'D34', demo['population_growth_3mi_pct'] / 100))
        elif demo.get('population_growth_pct'):
            # Fallback to 1-mile if 3-mile not available
            updates.append(('Stage 1', 'D34', demo['population_growth_pct'] / 100))

        # Rent growth from market data
        market = extracted_data.get('market', {})

        # Submarket Annual Rent Growth Projections (CoStar EST)
        # D64 = Year 1, E65 = Year 2, F65 = Year 3, G65 = Year 4, H65 = Year 5
        projections = market.get('rent_growth_projections', {})
        if projections:
            if projections.get('rent_growth_2025'):
                updates.append(('Stage 1', 'D64', projections['rent_growth_2025'] / 100))
            if projections.get('rent_growth_2026'):
                updates.append(('Stage 1', 'E65', projections['rent_growth_2026'] / 100))
            if projections.get('rent_growth_2027'):
                updates.append(('Stage 1', 'F65', projections['rent_growth_2027'] / 100))
            if projections.get('rent_growth_2028'):
                updates.append(('Stage 1', 'G65', projections['rent_growth_2028'] / 100))
            if projections.get('rent_growth_2029'):
                updates.append(('Stage 1', 'H65', projections['rent_growth_2029'] / 100))

        # Subject rent to both Cover and Rent Comps sheets
        rent = extracted_data.get('rent_comps', {})
        if rent.get('subject_current_rent'):
            # Already mapped to Cover F4, also map to Rent Comps E4
            pass  # Already handled by subject_current_rent_comp mapping

        # === RENT COMPARABLES ROWS ===
        comp_updates = self._map_rent_comps(extracted_data)
        updates.extend(comp_updates)

        # === SALE COMPARABLES ROWS ===
        sale_comp_updates = self._map_sale_comps(extracted_data)
        updates.extend(sale_comp_updates)

        return updates

    def _calculate_fields(self, extracted_data: Dict[str, Any]) -> List[Tuple[str, str, Any]]:
        """Calculate derived fields from extracted data."""
        calculated = []

        prop = extracted_data.get('property', {})
        demo = extracted_data.get('demographics', {})
        rent = extracted_data.get('rent_comps', {})
        market = extracted_data.get('market', {})

        # 1. Net Rental SF (units * avg SF)
        if prop.get('units') and prop.get('avg_unit_size'):
            net_rental_sf = prop['units'] * prop['avg_unit_size']
            calculated.append(('Screener Cover', 'F7', net_rental_sf))

        # 2. Submarket Occupancy (1 - vacancy rate)
        if demo.get('submarket_vacancy_rate'):
            # Convert vacancy to occupancy (7.6% vacancy = 92.4% occupancy)
            occupancy = 1 - (demo['submarket_vacancy_rate'] / 100)
            calculated.append(('Stage 1', 'D101', occupancy))

        # D64 rent growth now handled by rent_growth_projections mapping above

        # 4. Convert population_growth_pct to decimal for D33
        if demo.get('population_growth_pct'):
            # Convert percentage to decimal (3.5% -> 0.035)
            pop_growth_decimal = demo['population_growth_pct'] / 100
            calculated.append(('Stage 1', 'D33', pop_growth_decimal))

        # 5. Calculate Supply/Demand ratio (D98)
        # Supply = Delivered Units (last 12 months)
        # Demand = Absorption Units (last 12 months)
        # Ratio = Demand / Supply (higher = better, means demand > supply)
        if market.get('delivered_12mo') and market.get('absorption_12mo'):
            delivered = market['delivered_12mo']
            absorbed = market['absorption_12mo']
            if delivered > 0:
                # Calculate as absorption rate (demand/supply ratio)
                supply_demand_ratio = absorbed / delivered
                # Format as text for display (e.g., "58.9% absorption" or "0.589")
                calculated.append(('Stage 1', 'D98', supply_demand_ratio))

        # Store calculated metrics in metadata
        # These could be used for Stage 2 scoring in future

        return calculated

    def _map_rent_comps(self, extracted_data: Dict[str, Any]) -> List[Tuple[str, str, Any]]:
        """
        Map individual rent comparable properties to Excel rows 10-26.

        Excel Rent Comps sheet structure (verified):
        - Row 8: Headers (Group, Map #, Building Name, etc.)
        - Row 9: Subject property
        - Rows 10-26: 17 comparable property rows

        Column mapping (verified from actual Excel file):
        - Column D: Building Name
        - Column L: Units
        - Column N: Yr Blt/Ren
        - Column O: Avg SF
        - Column Q: Rent/SF
        - Column S: Studio Rent
        - Column T: 1 Bed Rent
        - Column U: 2 Bed Rent
        - Column V: 3 Bed Rent
        """
        comp_updates = []

        rent_comps = extracted_data.get('rent_comps', {})
        comps = rent_comps.get('comparable_properties', [])

        if not comps:
            return comp_updates

        # Excel rows 10-26 = 17 comp rows
        start_row = 10
        max_comps = 17

        for i, comp in enumerate(comps[:max_comps]):
            row = start_row + i

            # Building Name - Column D
            if comp.get('name'):
                comp_updates.append(('Rent Comps', f'D{row}', comp['name']))

            # Units - Column L
            if comp.get('units'):
                comp_updates.append(('Rent Comps', f'L{row}', comp['units']))

            # Avg SF - Column O
            if comp.get('avg_sf'):
                comp_updates.append(('Rent Comps', f'O{row}', comp['avg_sf']))

            # Year Built - Column N
            if comp.get('year_built'):
                year_str = str(comp['year_built'])
                comp_updates.append(('Rent Comps', f'N{row}', year_str))

            # Rent PSF - Column Q
            if comp.get('rent_psf'):
                comp_updates.append(('Rent Comps', f'Q{row}', comp['rent_psf']))

            # Studio Rent - Column S
            if comp.get('studio_rent'):
                comp_updates.append(('Rent Comps', f'S{row}', comp['studio_rent']))

            # 1 Bedroom Rent - Column T
            if comp.get('rent_1bed'):
                comp_updates.append(('Rent Comps', f'T{row}', comp['rent_1bed']))

            # 2 Bedroom Rent - Column U
            if comp.get('rent_2bed'):
                comp_updates.append(('Rent Comps', f'U{row}', comp['rent_2bed']))

            # 3 Bedroom Rent - Column V
            if comp.get('rent_3bed'):
                comp_updates.append(('Rent Comps', f'V{row}', comp['rent_3bed']))

        return comp_updates

    def _map_sale_comps(self, extracted_data: Dict[str, Any]) -> List[Tuple[str, str, Any]]:
        """
        Map individual sale comparable properties to Excel Sale Comps sheet rows.

        Excel Sale Comps sheet structure:
        - Row 7: Headers
        - Rows 8-22: 15 comparable sale rows (data starts at row 8!)

        ACTUAL Column mapping from Excel file:
        - Column B: Address
        - Column C: Name
        - Column D: Rating
        - Column E: Yr Blt/Renov
        - Column F: Type
        - Column G: Units
        - Column H: Dist (mi)
        - Column I: Sale Date
        - Column J: Sale Price
        - Column K: Price/Unit
        - Column L: Price/SF
        - Column M: Cap Rate
        - Column N: Submarket
        """
        sale_comp_updates = []

        sale_comps = extracted_data.get('sale_comps', {})

        # Add summary statistics - these go in different cells
        # Summary stats are typically in row 3 or calculated cells
        # Skip for now since columns are different

        # Map individual sale comps to rows 8-22 (not 10-24!)
        comps = sale_comps.get('comparable_sales', [])
        if not comps:
            return sale_comp_updates

        start_row = 8  # Data starts at row 8, not row 10!
        max_comps = 15

        for i, comp in enumerate(comps[:max_comps]):
            row = start_row + i

            # Column C: Name
            if comp.get('name'):
                sale_comp_updates.append(('Sale Comps', f'C{row}', comp['name']))

            # Column E: Yr Blt/Renov (Year Built)
            if comp.get('year_built'):
                sale_comp_updates.append(('Sale Comps', f'E{row}', comp['year_built']))

            # Column G: Units
            if comp.get('units'):
                sale_comp_updates.append(('Sale Comps', f'G{row}', comp['units']))

            # Column I: Sale Date
            if comp.get('sale_date'):
                sale_comp_updates.append(('Sale Comps', f'I{row}', comp['sale_date']))

            # Column J: Sale Price
            if comp.get('sale_price'):
                sale_comp_updates.append(('Sale Comps', f'J{row}', comp['sale_price']))

            # Column K: Price/Unit
            if comp.get('price_per_unit'):
                sale_comp_updates.append(('Sale Comps', f'K{row}', comp['price_per_unit']))

            # Column M: Cap Rate (if available)
            # Note: Individual comps from our extraction don't have individual cap rates
            # Only have summary avg cap rate

            # Vacancy at Sale - not in the Excel columns we saw
            # Don't map this

        return sale_comp_updates

    def get_calculated_metrics(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate additional metrics for metadata/reference.

        Returns:
            Dictionary of calculated metrics
        """
        metrics = {}

        prop = extracted_data.get('property', {})
        demo = extracted_data.get('demographics', {})
        rent = extracted_data.get('rent_comps', {})
        market = extracted_data.get('market', {})

        # Rent-to-Income Ratio
        if demo.get('median_hh_income_1mi') and rent.get('subject_current_rent'):
            annual_rent = rent['subject_current_rent'] * 12
            metrics['rent_to_income_ratio'] = annual_rent / demo['median_hh_income_1mi']
            metrics['rent_to_income_pct'] = f"{metrics['rent_to_income_ratio']:.2%}"

        # Gap to Market Rents
        if rent.get('subject_current_rent') and rent.get('avg_comp_rent_per_unit'):
            metrics['gap_to_market'] = (
                (rent['subject_current_rent'] - rent['avg_comp_rent_per_unit'])
                / rent['avg_comp_rent_per_unit']
            )
            metrics['gap_to_market_pct'] = f"{metrics['gap_to_market']:.2%}"

        # Year-over-Year Rent Growth
        if rent.get('subject_current_rent') and rent.get('subject_rent_year_ago'):
            metrics['yoy_rent_growth'] = (
                (rent['subject_current_rent'] - rent['subject_rent_year_ago'])
                / rent['subject_rent_year_ago']
            )
            metrics['yoy_rent_growth_pct'] = f"{metrics['yoy_rent_growth']:.2%}"

        # Absorption Rate (submarket)
        if market.get('absorption_12mo') and market.get('delivered_12mo'):
            metrics['absorption_rate'] = market['absorption_12mo'] / market['delivered_12mo']
            metrics['absorption_rate_pct'] = f"{metrics['absorption_rate']:.2%}"

        # Occupancy (inverse of vacancy)
        if prop.get('vacancy_rate'):
            metrics['occupancy_rate'] = 100 - prop['vacancy_rate']
            metrics['occupancy_rate_pct'] = f"{metrics['occupancy_rate']:.1f}%"

        # Density (units per acre)
        if prop.get('units') and prop.get('land_area_acres'):
            metrics['units_per_acre'] = prop['units'] / prop['land_area_acres']

        return metrics

    def get_metadata_fields(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get all fields designated for metadata/reference.
        """
        metadata = {}

        for category, data in extracted_data.items():
            if not isinstance(data, dict):
                continue

            for field_name, value in data.items():
                if value is None:
                    continue

                if field_name in self.field_mappings:
                    _, _, cell = self.field_mappings[field_name]
                    if cell == 'Comments':
                        metadata[field_name] = value
                elif isinstance(value, (dict, list)):
                    metadata[field_name] = value

        # Add calculated metrics
        calculated = self.get_calculated_metrics(extracted_data)
        metadata.update(calculated)

        return metadata

    def get_summary(self, extracted_data: Dict[str, Any], config: Dict[str, Any] = None) -> str:
        """Get a summary of what will be mapped."""
        updates = self.map_extracted_data(extracted_data, config)
        metadata = self.get_metadata_fields(extracted_data)
        calculated = self.get_calculated_metrics(extracted_data)

        summary = []
        summary.append(f"=== DATA MAPPING SUMMARY ===\n")
        summary.append(f"Excel cells to update: {len(updates)}")
        summary.append(f"Calculated metrics: {len(calculated)}")
        summary.append(f"Metadata fields: {len(metadata)}\n")

        summary.append("Excel Updates:")
        for sheet, cell, value in sorted(updates):
            summary.append(f"  {sheet}!{cell} = {value}")

        summary.append(f"\nCalculated Metrics:")
        for field, value in calculated.items():
            summary.append(f"  {field}: {value}")

        return "\n".join(summary)


if __name__ == "__main__":
    # Test
    import sys
    sys.path.append('.')
    from pdf_extractor import CoStarPDFExtractor

    reports_dir = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\CoStar Reports"
    extractor = CoStarPDFExtractor(reports_dir)
    data = extractor.extract_all()

    mapper = ScreenerDataMapper()
    print(mapper.get_summary(data))
