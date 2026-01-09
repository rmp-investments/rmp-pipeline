"""
Stage 2 Score Calculator - Calculates automated scores for Stage 2 fields
All scores are 1-10 scale with transparent intermediate calculations

IMPORTANT: If you change any scoring scales here, also update:
  - RMP Screener_PreLinked_v3.xlsx -> "Scoring Reference" sheet
  - data_inputs_mapper.py -> field descriptions
"""

from typing import Dict, Any, Optional


class ScoreCalculator:
    """Calculates Stage 2 scores from extracted data."""

    def calculate_all_scores(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate all Stage 2 scores and add them to extracted_data.
        Returns the modified extracted_data dict with 'stage2_scores' added.
        """
        scores = {}

        # Supply-Demand Drivers
        supply_demand = self._calculate_supply_demand_score(extracted_data)
        scores['supply_demand'] = supply_demand

        # Submarket Supply-Demand Outlook
        submarket_outlook = self._calculate_submarket_outlook_score(extracted_data)
        scores['submarket_outlook'] = submarket_outlook

        # Migration / GDP Growth
        migration_gdp = self._calculate_migration_gdp_score(extracted_data)
        scores['migration_gdp'] = migration_gdp

        # Parking Ratio
        parking = self._calculate_parking_score(extracted_data)
        scores['parking'] = parking

        # Amenities & Lifestyle
        amenities = self._calculate_amenities_score(extracted_data)
        scores['amenities'] = amenities

        # Unit Mix & Size
        unit_mix = self._calculate_unit_mix_score(extracted_data)
        scores['unit_mix'] = unit_mix

        # Loss-to-Lease
        loss_to_lease = self._calculate_loss_to_lease_score(extracted_data)
        scores['loss_to_lease'] = loss_to_lease

        # Business-Friendly Environment
        business_friendly = self._calculate_business_friendly_score(extracted_data)
        scores['business_friendly'] = business_friendly

        # Nearby Nuisance Properties
        nuisance = self._calculate_nuisance_score(extracted_data)
        scores['nuisance'] = nuisance

        # Climate Risk
        climate_risk = self._calculate_climate_risk_score(extracted_data)
        scores['climate_risk'] = climate_risk

        # Employer Stability / Recession Resistance
        employer_stability = self._calculate_employer_stability_score(extracted_data)
        scores['employer_stability'] = employer_stability

        extracted_data['stage2_scores'] = scores
        return extracted_data

    def _calculate_supply_demand_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Supply-Demand Drivers score.

        Logic:
        - Base score from Absorption/Delivery ratio
        - Pipeline adjustment based on Under Construction vs Absorption

        Returns dict with all intermediate values for transparency.
        """
        market = data.get('market', {})

        absorption = market.get('absorption_12mo')
        delivered = market.get('delivered_12mo')
        under_construction = market.get('under_construction')

        result = {
            'absorption_12mo': absorption,
            'delivered_12mo': delivered,
            'under_construction': under_construction,
            'absorption_ratio': None,
            'pipeline_ratio': None,
            'base_score': None,
            'pipeline_adjustment': None,
            'final_score': None,
            'notes': None,
        }

        # Check for required data
        if absorption is None or delivered is None:
            result['notes'] = 'Missing absorption or delivery data'
            return result

        # Handle edge cases
        if delivered == 0 and absorption == 0:
            # Stagnant market
            result['absorption_ratio'] = 'N/A'
            result['base_score'] = 5
            result['pipeline_adjustment'] = 0
            result['final_score'] = 5
            result['notes'] = 'Stagnant market (no deliveries or absorption)'
            return result

        if delivered == 0 and absorption > 0:
            # No new supply, positive absorption = good
            result['absorption_ratio'] = 'Infinite (no deliveries)'
            result['base_score'] = 9
            result['pipeline_adjustment'] = 0
            result['final_score'] = 9
            result['notes'] = 'No deliveries, positive absorption'
            return result

        if delivered == 0 and absorption < 0:
            # No new supply but negative absorption = concerning
            result['absorption_ratio'] = 'N/A'
            result['base_score'] = 4
            result['pipeline_adjustment'] = 0
            result['final_score'] = 4
            result['notes'] = 'No deliveries but negative absorption (move-outs)'
            return result

        if absorption < 0:
            # Negative absorption (net move-outs) = red flag
            result['absorption_ratio'] = round(absorption / delivered, 2)
            result['base_score'] = 3
            result['notes'] = 'Negative absorption (net move-outs) - capped at 3'
        else:
            # Normal case: calculate ratio
            ratio = absorption / delivered
            result['absorption_ratio'] = round(ratio, 2)

            # Base score from ratio
            if ratio >= 2.0:
                result['base_score'] = 10
            elif ratio >= 1.5:
                result['base_score'] = 8
            elif ratio >= 1.0:
                result['base_score'] = 6
            elif ratio >= 0.5:
                result['base_score'] = 4
            else:
                result['base_score'] = 2

        # Pipeline adjustment
        if under_construction is not None and absorption is not None and absorption > 0:
            pipeline_ratio = under_construction / absorption
            result['pipeline_ratio'] = round(pipeline_ratio, 2)

            if pipeline_ratio > 1.5:
                result['pipeline_adjustment'] = -2
                result['notes'] = (result.get('notes') or '') + 'Heavy pipeline (-2)'
            elif pipeline_ratio > 1.0:
                result['pipeline_adjustment'] = -1
                result['notes'] = (result.get('notes') or '') + 'Moderate pipeline (-1)'
            elif pipeline_ratio < 0.5:
                result['pipeline_adjustment'] = 1
                result['notes'] = (result.get('notes') or '') + 'Light pipeline (+1)'
            else:
                result['pipeline_adjustment'] = 0
        else:
            result['pipeline_adjustment'] = 0
            if under_construction is None:
                result['notes'] = (result.get('notes') or '') + ' No UC data'

        # Final score (capped 1-10)
        final = result['base_score'] + result['pipeline_adjustment']
        result['final_score'] = max(1, min(10, final))

        return result

    def _calculate_submarket_outlook_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Submarket Supply-Demand Outlook score.

        Logic (3 components summed from base of 5):
        1. Vacancy Level vs Historical: Is current vacancy better or worse than normal?
        2. Vacancy Trend: Which direction is vacancy moving? (most important)
        3. Pipeline Pressure: Can the market absorb upcoming supply?

        Returns dict with all intermediate values for transparency.
        """
        market = data.get('market', {})

        current_vacancy = market.get('submarket_vacancy_rate')
        vacancy_yoy = market.get('vacancy_yoy_change')
        historical_avg = market.get('vacancy_historical_avg')
        under_construction = market.get('under_construction')
        absorption = market.get('absorption_12mo')

        result = {
            'current_vacancy': current_vacancy,
            'vacancy_yoy_change': vacancy_yoy,
            'vacancy_historical_avg': historical_avg,
            'under_construction': under_construction,
            'absorption_12mo': absorption,
            'vacancy_vs_historical': None,
            'level_adjustment': None,
            'trend_adjustment': None,
            'pipeline_adjustment': None,
            'pipeline_ratio': None,
            'base_score': 5,
            'final_score': None,
            'notes': None,
        }

        adjustments = []

        # === Part 1: Vacancy Level vs Historical ===
        if current_vacancy is not None and historical_avg is not None:
            diff = current_vacancy - historical_avg
            result['vacancy_vs_historical'] = round(diff, 1)

            if diff <= -2.0:
                result['level_adjustment'] = 2
                adjustments.append('Well below historical avg (+2)')
            elif diff <= -0.5:
                result['level_adjustment'] = 1
                adjustments.append('Below historical avg (+1)')
            elif diff <= 0.5:
                result['level_adjustment'] = 0
                adjustments.append('Near historical avg (0)')
            elif diff <= 2.0:
                result['level_adjustment'] = -1
                adjustments.append('Above historical avg (-1)')
            else:
                result['level_adjustment'] = -2
                adjustments.append('Well above historical avg (-2)')
        else:
            result['level_adjustment'] = 0
            adjustments.append('No historical data')

        # === Part 2: Vacancy Trend (YoY change) - Most important ===
        if vacancy_yoy is not None:
            if vacancy_yoy <= -1.0:
                result['trend_adjustment'] = 3
                adjustments.append(f'Improving fast {vacancy_yoy}% (+3)')
            elif vacancy_yoy <= -0.5:
                result['trend_adjustment'] = 2
                adjustments.append(f'Improving {vacancy_yoy}% (+2)')
            elif vacancy_yoy < 0:
                result['trend_adjustment'] = 1
                adjustments.append(f'Slightly improving {vacancy_yoy}% (+1)')
            elif vacancy_yoy == 0:
                result['trend_adjustment'] = 0
                adjustments.append('Flat trend (0)')
            elif vacancy_yoy <= 0.5:
                result['trend_adjustment'] = -1
                adjustments.append(f'Slightly worsening +{vacancy_yoy}% (-1)')
            elif vacancy_yoy <= 1.0:
                result['trend_adjustment'] = -2
                adjustments.append(f'Worsening +{vacancy_yoy}% (-2)')
            else:
                result['trend_adjustment'] = -3
                adjustments.append(f'Worsening fast +{vacancy_yoy}% (-3)')
        else:
            result['trend_adjustment'] = 0
            adjustments.append('No YoY trend data')

        # === Part 3: Pipeline Pressure ===
        if under_construction is not None and absorption is not None and absorption > 0:
            pipeline_ratio = under_construction / absorption
            result['pipeline_ratio'] = round(pipeline_ratio, 2)

            if pipeline_ratio < 0.5:
                result['pipeline_adjustment'] = 1
                adjustments.append(f'Light pipeline {pipeline_ratio:.1f}x (+1)')
            elif pipeline_ratio <= 1.0:
                result['pipeline_adjustment'] = 0
                adjustments.append(f'Manageable pipeline {pipeline_ratio:.1f}x (0)')
            elif pipeline_ratio <= 1.5:
                result['pipeline_adjustment'] = -1
                adjustments.append(f'Moderate pipeline {pipeline_ratio:.1f}x (-1)')
            else:
                result['pipeline_adjustment'] = -2
                adjustments.append(f'Heavy pipeline {pipeline_ratio:.1f}x (-2)')
        else:
            result['pipeline_adjustment'] = 0
            if absorption is not None and absorption <= 0:
                adjustments.append('Negative/zero absorption - pipeline N/A')
            else:
                adjustments.append('No pipeline data')

        # === Calculate Final Score ===
        total_adjustment = (
            (result['level_adjustment'] or 0) +
            (result['trend_adjustment'] or 0) +
            (result['pipeline_adjustment'] or 0)
        )
        final = result['base_score'] + total_adjustment
        result['final_score'] = max(1, min(10, final))
        result['notes'] = ' | '.join(adjustments)

        return result

    def _calculate_migration_gdp_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Migration / GDP Growth score (3% weight).

        Logic: Average of two sub-scores (each 1-10):
        1. Employment Growth Score - market job growth vs US average
        2. Population Growth Score - 5mi population growth (proxy for migration)

        Returns dict with all intermediate values for transparency.
        """
        employment = data.get('employment', {})
        demographics = data.get('demographics', {})

        emp_market = employment.get('current_growth_market')
        emp_us = employment.get('current_growth_us')
        pop_growth = demographics.get('population_growth_pct_5mi')

        result = {
            'emp_growth_market': emp_market,
            'emp_growth_us': emp_us,
            'emp_vs_us': None,
            'pop_growth_5mi': pop_growth,
            'emp_score': None,
            'pop_score': None,
            'final_score': None,
            'notes': None,
        }

        scores = []
        notes = []

        # === Employment Growth Score (market vs US) ===
        if emp_market is not None and emp_us is not None:
            diff = emp_market - emp_us
            result['emp_vs_us'] = round(diff, 2)

            # Scale: market vs US difference
            if diff >= 1.0:
                result['emp_score'] = 10
                notes.append(f'Jobs: +{diff:.1f}% vs US (10)')
            elif diff >= 0.5:
                result['emp_score'] = 8
                notes.append(f'Jobs: +{diff:.1f}% vs US (8)')
            elif diff >= 0:
                result['emp_score'] = 6
                notes.append(f'Jobs: +{diff:.1f}% vs US (6)')
            elif diff >= -0.5:
                result['emp_score'] = 5
                notes.append(f'Jobs: {diff:.1f}% vs US (5)')
            elif diff >= -1.0:
                result['emp_score'] = 4
                notes.append(f'Jobs: {diff:.1f}% vs US (4)')
            elif diff >= -1.5:
                result['emp_score'] = 3
                notes.append(f'Jobs: {diff:.1f}% vs US (3)')
            else:
                result['emp_score'] = 2
                notes.append(f'Jobs: {diff:.1f}% vs US (2)')
            scores.append(result['emp_score'])
        else:
            notes.append('No employment data')

        # === Population Growth Score (5mi, 5-year projection) ===
        if pop_growth is not None:
            # Scale: 5-year population growth %
            if pop_growth >= 10:
                result['pop_score'] = 10
                notes.append(f'Pop: +{pop_growth}% (10)')
            elif pop_growth >= 8:
                result['pop_score'] = 9
                notes.append(f'Pop: +{pop_growth}% (9)')
            elif pop_growth >= 6:
                result['pop_score'] = 8
                notes.append(f'Pop: +{pop_growth}% (8)')
            elif pop_growth >= 4:
                result['pop_score'] = 7
                notes.append(f'Pop: +{pop_growth}% (7)')
            elif pop_growth >= 2:
                result['pop_score'] = 6
                notes.append(f'Pop: +{pop_growth}% (6)')
            elif pop_growth >= 0:
                result['pop_score'] = 5
                notes.append(f'Pop: +{pop_growth}% (5)')
            elif pop_growth >= -2:
                result['pop_score'] = 4
                notes.append(f'Pop: {pop_growth}% (4)')
            else:
                result['pop_score'] = 2
                notes.append(f'Pop: {pop_growth}% (2)')
            scores.append(result['pop_score'])
        else:
            notes.append('No population data')

        # === Final Score (average of sub-scores) ===
        if scores:
            avg = sum(scores) / len(scores)
            result['final_score'] = round(avg)
        else:
            result['final_score'] = None

        result['notes'] = ' | '.join(notes)
        return result

    def _calculate_parking_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Parking Ratio score (3% weight).

        Logic: Direct lookup based on parking spaces per unit.
        Suburban workforce housing target is 1:1 or better.
        Penalty for underground/garage-only (no surface parking).

        Scoring Scale:
        >=2.0 = 10, 1.5-2.0 = 9, 1.25-1.5 = 8, 1.0-1.25 = 7,
        0.75-1.0 = 5, 0.5-0.75 = 3, <0.5 = 2
        Underground-only penalty: -1 point

        Returns dict with all intermediate values for transparency.
        """
        prop = data.get('property', {})
        subject = data.get('subject_property', {})

        # Try property first, fall back to subject_property
        # Use explicit None checks because 0 is a valid value for parking fields
        parking_ratio = prop.get('parking_ratio') if prop.get('parking_ratio') is not None else subject.get('parking_ratio')
        parking_spaces = prop.get('parking_spaces') if prop.get('parking_spaces') is not None else subject.get('parking_spaces')
        units = prop.get('units') if prop.get('units') is not None else subject.get('units')
        surface_spaces = prop.get('parking_surface_spaces') if prop.get('parking_surface_spaces') is not None else subject.get('parking_surface_spaces')
        covered_spaces = prop.get('parking_covered_spaces') if prop.get('parking_covered_spaces') is not None else subject.get('parking_covered_spaces')

        result = {
            'parking_ratio': parking_ratio,
            'parking_spaces': parking_spaces,
            'surface_spaces': surface_spaces,
            'covered_spaces': covered_spaces,
            'units': units,
            'base_score': None,
            'underground_penalty': 0,
            'final_score': None,
            'notes': None,
        }

        if parking_ratio is None:
            result['notes'] = 'No parking ratio data'
            return result

        notes = []

        # Scale: parking ratio to base score (adjusted: 2:1 = 10)
        if parking_ratio >= 2.0:
            result['base_score'] = 10
            notes.append(f'{parking_ratio}:1 ratio - Excellent (>=2.0)')
        elif parking_ratio >= 1.5:
            result['base_score'] = 9
            notes.append(f'{parking_ratio}:1 ratio - Very Good (1.5-2.0)')
        elif parking_ratio >= 1.25:
            result['base_score'] = 8
            notes.append(f'{parking_ratio}:1 ratio - Good (1.25-1.5)')
        elif parking_ratio >= 1.0:
            result['base_score'] = 7
            notes.append(f'{parking_ratio}:1 ratio - Adequate (1.0-1.25)')
        elif parking_ratio >= 0.75:
            result['base_score'] = 5
            notes.append(f'{parking_ratio}:1 ratio - Limited (0.75-1.0)')
        elif parking_ratio >= 0.5:
            result['base_score'] = 3
            notes.append(f'{parking_ratio}:1 ratio - Poor (0.5-0.75)')
        else:
            result['base_score'] = 2
            notes.append(f'{parking_ratio}:1 ratio - Insufficient (<0.5)')

        # Underground/garage-only penalty: -1 if no surface parking
        if surface_spaces is not None and covered_spaces is not None:
            if surface_spaces == 0 and covered_spaces > 0:
                result['underground_penalty'] = -1
                notes.append('Underground-only (-1)')
            elif surface_spaces > 0:
                notes.append(f'{surface_spaces} surface + {covered_spaces} covered')

        # Final score (capped 1-10)
        final = result['base_score'] + result['underground_penalty']
        result['final_score'] = max(1, min(10, final))
        result['notes'] = ' | '.join(notes)

        return result

    # Amenity scoring configuration - easy to reference/modify
    SITE_AMENITIES_SCORING = {
        'Pool': 1.0,
        'Fitness Center': 1.0,
        'Clubhouse': 1.0,
        'Business Center': 0.5,
        'Playground': 0.5,
        'Dog Park': 0.5,
        'Concierge': 0.5,
        'Property Manager on Site': 0.5,
        'Basketball Court': 0.5,
        'Tennis Court': 0.5,
        'Sport Court': 0.5,
        'Grill': 0.25,
        'Picnic Area': 0.25,
    }
    
    UNIT_AMENITIES_SCORING = {
        'Washer/Dryer': 1.5,
        'Washer/Dryer Hookup': 0.75,
        'Air Conditioning': 1.0,
        'Dishwasher': 0.5,
        'Balcony': 0.5,
        'Patio': 0.5,
        'Walk-In Closets': 0.5,
        'Fireplace': 0.5,
        'Hardwood Floors': 0.5,
        'Vaulted Ceiling': 0.25,
        'Stainless Steel Appliances': 0.25,
        'Granite Countertops': 0.25,
    }

    def _calculate_amenities_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Amenities & Lifestyle score (5% weight).

        Logic: Points-based checklist system.
        - Site amenities: max 5 pts (Pool, Fitness, Clubhouse high value)
        - Unit amenities: max 5 pts (In-Unit W/D highest value)
        - Total: 10 pts = score of 10

        Returns dict with all intermediate values for transparency.
        """
        prop = data.get('property', {})
        amenities = prop.get('amenities', {})
        
        site_amenities = amenities.get('site', [])
        unit_amenities = amenities.get('unit', [])

        result = {
            'site_amenities': site_amenities,
            'unit_amenities': unit_amenities,
            'site_score': 0,
            'unit_score': 0,
            'site_matches': [],
            'unit_matches': [],
            'final_score': None,
            'notes': None,
        }

        if not site_amenities and not unit_amenities:
            result['notes'] = 'No amenity data available'
            return result

        # Score site amenities
        site_pts = 0
        site_matches = []
        for amenity in site_amenities:
            for key, pts in self.SITE_AMENITIES_SCORING.items():
                if key.lower() in amenity.lower():
                    site_pts += pts
                    site_matches.append(f'{amenity}({pts})')
                    break
        result['site_score'] = min(5, round(site_pts, 1))
        result['site_matches'] = site_matches

        # Score unit amenities
        unit_pts = 0
        unit_matches = []
        for amenity in unit_amenities:
            for key, pts in self.UNIT_AMENITIES_SCORING.items():
                if key.lower() in amenity.lower():
                    unit_pts += pts
                    unit_matches.append(f'{amenity}({pts})')
                    break
        result['unit_score'] = min(5, round(unit_pts, 1))
        result['unit_matches'] = unit_matches

        # Final score (sum, capped at 10, min 1)
        total = result['site_score'] + result['unit_score']
        result['final_score'] = max(1, min(10, round(total)))
        
        result['notes'] = f"Site: {result['site_score']}/5 ({len(site_matches)} items) | Unit: {result['unit_score']}/5 ({len(unit_matches)} items)"

        return result

    def _calculate_unit_mix_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Unit Mix & Size score (5% weight).

        Logic: Average of two sub-scores (each 1-10):
        1. Size Score - based on avg unit SF (bigger = better for workforce housing)
        2. Mix Score - based on % of 2-3BR units (more = better for families)

        Returns dict with all intermediate values for transparency.
        """
        prop = data.get('property', {})
        subject = data.get('subject_property', {})

        # Get unit mix data
        unit_mix = prop.get('unit_mix', [])
        avg_sf = prop.get('avg_unit_size') or subject.get('avg_unit_size')
        total_units = prop.get('units') or subject.get('units')

        result = {
            'total_units': total_units,
            'avg_sf': avg_sf,
            'units_2_3_br': None,
            'pct_2_3_br': None,
            'size_score': None,
            'mix_score': None,
            'final_score': None,
            'notes': None,
        }

        notes = []

        # === Size Score (based on avg SF) ===
        if avg_sf is not None:
            if avg_sf >= 1000:
                result['size_score'] = 10
                notes.append(f'Size: {avg_sf}sf (10)')
            elif avg_sf >= 900:
                result['size_score'] = 8
                notes.append(f'Size: {avg_sf}sf (8)')
            elif avg_sf >= 800:
                result['size_score'] = 6
                notes.append(f'Size: {avg_sf}sf (6)')
            elif avg_sf >= 700:
                result['size_score'] = 4
                notes.append(f'Size: {avg_sf}sf (4)')
            else:
                result['size_score'] = 2
                notes.append(f'Size: {avg_sf}sf (2)')
        else:
            notes.append('No avg SF data')

        # === Mix Score (based on % 2-3BR) ===
        if unit_mix:
            # Calculate units by bedroom type
            units_2br = sum(u.get('units', 0) for u in unit_mix if u.get('bedrooms') == 2)
            units_3br = sum(u.get('units', 0) for u in unit_mix if u.get('bedrooms') == 3)
            total_from_mix = sum(u.get('units', 0) for u in unit_mix)

            units_2_3_br = units_2br + units_3br
            result['units_2_3_br'] = units_2_3_br

            if total_from_mix > 0:
                pct = (units_2_3_br / total_from_mix) * 100
                result['pct_2_3_br'] = round(pct, 1)

                if pct >= 70:
                    result['mix_score'] = 10
                    notes.append(f'Mix: {pct:.0f}% 2-3BR (10)')
                elif pct >= 60:
                    result['mix_score'] = 8
                    notes.append(f'Mix: {pct:.0f}% 2-3BR (8)')
                elif pct >= 50:
                    result['mix_score'] = 6
                    notes.append(f'Mix: {pct:.0f}% 2-3BR (6)')
                elif pct >= 40:
                    result['mix_score'] = 4
                    notes.append(f'Mix: {pct:.0f}% 2-3BR (4)')
                else:
                    result['mix_score'] = 3
                    notes.append(f'Mix: {pct:.0f}% 2-3BR (3)')
            else:
                notes.append('No unit count in mix')
        else:
            notes.append('No unit mix data')

        # === Final Score (average of sub-scores) ===
        scores = [s for s in [result['size_score'], result['mix_score']] if s is not None]
        if scores:
            avg = sum(scores) / len(scores)
            result['final_score'] = round(avg)
        else:
            result['final_score'] = None

        result['notes'] = ' | '.join(notes)
        return result

    def _calculate_loss_to_lease_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Loss-to-Lease score (10% weight).

        Logic: Blended comparison of subject rent vs market:
        - 60% weight: Subject vs Comp Average (direct competitors)
        - 40% weight: Subject vs Submarket Average (broader market)

        Loss-to-Lease % = (Subject - Market) / Market
        - Negative = below market (good - can raise rents) = higher score
        - Positive = above market (bad) = lower score

        Scoring Scale:
        <= -20% = 10, -15% to -20% = 9, -10% to -15% = 8, -5% to -10% = 7,
        -2.5% to -5% = 6, ±2.5% = 5, +2.5% to +5% = 4, +5% to +10% = 3,
        +10% to +15% = 2, +15% to +20% = 1, > +20% = 0

        Returns dict with all intermediate values for transparency.
        """
        rent_comps = data.get('rent_comps', {})
        subject = data.get('subject_property', {})
        demographics = data.get('demographics', {})

        # Get subject rent
        subject_rent = rent_comps.get('subject_current_rent') or subject.get('current_rent_per_unit')

        # Get market rents
        comp_avg_rent = rent_comps.get('avg_comp_rent_per_unit') or demographics.get('competitor_avg_rent')
        submarket_rent = rent_comps.get('submarket_avg_rent') or demographics.get('submarket_avg_rent')

        result = {
            'subject_rent': subject_rent,
            'comp_avg_rent': comp_avg_rent,
            'submarket_rent': submarket_rent,
            'ltl_vs_comps_pct': None,
            'ltl_vs_submarket_pct': None,
            'blended_ltl_pct': None,
            'final_score': None,
            'notes': None,
        }

        ltl_values = []
        notes = []

        # === Calculate LTL vs Comp Average (60% weight) ===
        if subject_rent is not None and comp_avg_rent is not None and comp_avg_rent > 0:
            ltl_comps = (subject_rent - comp_avg_rent) / comp_avg_rent * 100
            result['ltl_vs_comps_pct'] = round(ltl_comps, 1)
            ltl_values.append(('comps', ltl_comps, 0.6))
            notes.append(f'vs Comps: {ltl_comps:+.1f}%')
        else:
            notes.append('No comp rent data')

        # === Calculate LTL vs Submarket Average (40% weight) ===
        if subject_rent is not None and submarket_rent is not None and submarket_rent > 0:
            ltl_submarket = (subject_rent - submarket_rent) / submarket_rent * 100
            result['ltl_vs_submarket_pct'] = round(ltl_submarket, 1)
            ltl_values.append(('submarket', ltl_submarket, 0.4))
            notes.append(f'vs Submarket: {ltl_submarket:+.1f}%')
        else:
            notes.append('No submarket rent data')

        # === Calculate Blended LTL ===
        if ltl_values:
            # If we have both, use weighted average; if only one, use that
            if len(ltl_values) == 2:
                blended = sum(v * w for _, v, w in ltl_values)
            else:
                blended = ltl_values[0][1]  # Use the one we have
            result['blended_ltl_pct'] = round(blended, 1)

            # === Score based on blended LTL ===
            if blended <= -20:
                result['final_score'] = 10
            elif blended <= -15:
                result['final_score'] = 9
            elif blended <= -10:
                result['final_score'] = 8
            elif blended <= -5:
                result['final_score'] = 7
            elif blended <= -2.5:
                result['final_score'] = 6
            elif blended <= 2.5:
                result['final_score'] = 5
            elif blended <= 5:
                result['final_score'] = 4
            elif blended <= 10:
                result['final_score'] = 3
            elif blended <= 15:
                result['final_score'] = 2
            elif blended <= 20:
                result['final_score'] = 1
            else:
                result['final_score'] = 0

            notes.append(f'Blended: {blended:+.1f}%')
        else:
            result['notes'] = 'Missing rent data for LTL calculation'
            return result

        result['notes'] = ' | '.join(notes)
        return result

    # State business-friendly scores - based on landlord/regulatory environment
    STATE_BUSINESS_SCORES = {
        # Very Business Friendly (10)
        'TX': 10, 'FL': 10, 'TN': 10, 'AZ': 10,
        # Business Friendly (9)
        'GA': 9, 'NC': 9, 'SC': 9, 'NV': 9, 'IN': 9,
        # Good (8)
        'KS': 8, 'MO': 8, 'OH': 8, 'UT': 8, 'OK': 8, 'AL': 8,
        # Above Average (7)
        'CO': 7, 'ID': 7, 'KY': 7, 'AR': 7, 'NE': 7, 'LA': 7, 'MS': 7,
        # Average (6)
        'PA': 6, 'MI': 6, 'WI': 6, 'VA': 6, 'IA': 6, 'MT': 6, 'WY': 6, 'SD': 6, 'ND': 6,
        # Below Average (5)
        'IL': 5, 'MN': 5, 'NM': 5, 'WV': 5, 'AK': 5,
        # Less Friendly (4)
        'WA': 4, 'MD': 4, 'NH': 4, 'DE': 4,
        # Challenging (3)
        'MA': 3, 'NJ': 3, 'CT': 3, 'HI': 3, 'ME': 3,
        # Difficult (2)
        'NY': 2, 'VT': 2, 'RI': 2,
        # Heavy Regulation (1)
        'CA': 1, 'OR': 1, 'DC': 1,
    }

    def _calculate_business_friendly_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Business-Friendly Environment score (3% weight).

        Logic: State-level lookup based on landlord/regulatory environment.
        Considers: rent control laws, eviction processes, tenant protections,
        business taxes, and general regulatory burden.

        Scoring Scale (by state):
        10 = TX, FL, TN, AZ (very landlord-friendly, no rent control)
        9 = GA, NC, SC, NV, IN
        8 = KS, MO, OH, UT, OK, AL
        7 = CO, ID, KY, AR, NE, LA, MS
        6 = PA, MI, WI, VA, IA, MT, WY, SD, ND
        5 = IL, MN, NM, WV, AK
        4 = WA, MD, NH, DE
        3 = MA, NJ, CT, HI, ME
        2 = NY, VT, RI
        1 = CA, OR, DC (heavy regulation, rent control common)

        Returns dict with all intermediate values for transparency.
        """
        config = data.get('config', {})
        prop_details = config.get('property_details', {})

        state = prop_details.get('state')

        result = {
            'state': state,
            'final_score': None,
            'notes': None,
        }

        if not state:
            result['notes'] = 'No state data available'
            return result

        # Normalize state to uppercase 2-letter code
        state_upper = state.upper().strip()

        # Handle full state names if needed
        state_name_to_abbrev = {
            'TEXAS': 'TX', 'FLORIDA': 'FL', 'TENNESSEE': 'TN', 'ARIZONA': 'AZ',
            'GEORGIA': 'GA', 'NORTH CAROLINA': 'NC', 'SOUTH CAROLINA': 'SC',
            'NEVADA': 'NV', 'INDIANA': 'IN', 'KANSAS': 'KS', 'MISSOURI': 'MO',
            'OHIO': 'OH', 'UTAH': 'UT', 'OKLAHOMA': 'OK', 'ALABAMA': 'AL',
            'COLORADO': 'CO', 'IDAHO': 'ID', 'KENTUCKY': 'KY', 'ARKANSAS': 'AR',
            'NEBRASKA': 'NE', 'LOUISIANA': 'LA', 'MISSISSIPPI': 'MS',
            'PENNSYLVANIA': 'PA', 'MICHIGAN': 'MI', 'WISCONSIN': 'WI',
            'VIRGINIA': 'VA', 'IOWA': 'IA', 'MONTANA': 'MT', 'WYOMING': 'WY',
            'SOUTH DAKOTA': 'SD', 'NORTH DAKOTA': 'ND', 'ILLINOIS': 'IL',
            'MINNESOTA': 'MN', 'NEW MEXICO': 'NM', 'WEST VIRGINIA': 'WV',
            'ALASKA': 'AK', 'WASHINGTON': 'WA', 'MARYLAND': 'MD',
            'NEW HAMPSHIRE': 'NH', 'DELAWARE': 'DE', 'MASSACHUSETTS': 'MA',
            'NEW JERSEY': 'NJ', 'CONNECTICUT': 'CT', 'HAWAII': 'HI', 'MAINE': 'ME',
            'NEW YORK': 'NY', 'VERMONT': 'VT', 'RHODE ISLAND': 'RI',
            'CALIFORNIA': 'CA', 'OREGON': 'OR', 'DISTRICT OF COLUMBIA': 'DC',
        }

        if len(state_upper) > 2:
            state_upper = state_name_to_abbrev.get(state_upper, state_upper)

        score = self.STATE_BUSINESS_SCORES.get(state_upper)

        if score is not None:
            result['final_score'] = score
            if score >= 9:
                result['notes'] = f'{state_upper}: Very business-friendly (no rent control, easy eviction)'
            elif score >= 7:
                result['notes'] = f'{state_upper}: Business-friendly environment'
            elif score >= 5:
                result['notes'] = f'{state_upper}: Moderate regulatory environment'
            elif score >= 3:
                result['notes'] = f'{state_upper}: Some tenant protections/regulations'
            else:
                result['notes'] = f'{state_upper}: Heavy regulation (rent control, strict tenant laws)'
        else:
            result['notes'] = f'State {state_upper} not in lookup table'

        return result

    def _calculate_nuisance_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Nearby Nuisance Properties score (3% weight).

        Uses OpenStreetMap/Overpass API data from web_scraper.
        Returns COUNTS by category - Excel calculates final score with editable weights.

        Search radii by category:
        - Severe (prison, landfill, waste): 1 mile
        - Industrial: 0.5 mile
        - Moderate (motel, storage, pawn, liquor, shelter): 0.25 mile
        - Minor (gas station, auto repair): 500 ft

        Returns dict with counts for Excel-based scoring.
        """
        web_demo = data.get('web_demographics', {})
        nuisance_data = web_demo.get('nuisance_data', {})

        result = {
            'source': 'OpenStreetMap/Overpass API',
            'severe_count': 0,
            'industrial_count': 0,
            'moderate_count': 0,
            'minor_count': 0,
            'nuisances_list': None,
            'python_score': None,  # Reference score - Excel recalculates
            'notes': None,
        }

        # Check if we have nuisance data
        if not nuisance_data or nuisance_data.get('error'):
            error_msg = nuisance_data.get('error', 'No nuisance data') if nuisance_data else 'No nuisance data'
            result['notes'] = f'Nuisance check unavailable: {error_msg}'
            return result

        # Get counts by category
        result['severe_count'] = nuisance_data.get('severe_count', 0)
        result['industrial_count'] = nuisance_data.get('industrial_count', 0)
        result['moderate_count'] = nuisance_data.get('moderate_count', 0)
        result['minor_count'] = nuisance_data.get('minor_count', 0)

        # Build list of nuisances found (include names for verification)
        nuisances = nuisance_data.get('nuisances', [])
        if nuisances:
            # Format: "type (name)" so user can search to verify
            items = []
            for n in nuisances:
                name = n.get('name', 'Unnamed')
                ntype = n.get('type', 'unknown')
                if name and name != 'Unnamed':
                    items.append(f"{ntype} ({name})")
                else:
                    items.append(ntype)
            result['nuisances_list'] = ', '.join(items)
        else:
            result['nuisances_list'] = 'None'

        result['python_score'] = nuisance_data.get('final_score', 10)
        result['notes'] = nuisance_data.get('notes', 'No nuisances detected')

        return result

    def _calculate_climate_risk_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Climate Risk score (5% weight).

        Uses 4 risk factors with weighted scoring:
        - Flood: 50% - FEMA NFHL flood zones (most critical for insurance/value)
        - Fire: 20% - USDA wildfire burn probability
        - Heat: 15% - Days >90F per year (Open-Meteo climate data)
        - Cold: 15% - Days <32F per year (Open-Meteo climate data)

        Returns dict with all intermediate values for transparency.
        """
        web_demo = data.get('web_demographics', {})
        climate_data = web_demo.get('climate_risk_data', {})

        result = {
            'source': 'FEMA + USDA + Open-Meteo',
            'flood_zone': None,
            'flood_zone_desc': None,
            'flood_is_sfha': None,
            'flood_score': None,
            'fire_burn_probability': None,
            'fire_score': None,
            'heat_days': None,
            'heat_score': None,
            'cold_days': None,
            'cold_score': None,
            'final_score': None,
            'notes': None,
        }

        # Check if we have climate data
        if not climate_data or climate_data.get('error'):
            error_msg = climate_data.get('error', 'No climate data') if climate_data else 'No climate data'
            result['notes'] = f'Climate check unavailable: {error_msg}'
            return result

        # Get flood data
        result['flood_zone'] = climate_data.get('flood_zone')
        result['flood_zone_desc'] = climate_data.get('flood_zone_desc')
        result['flood_is_sfha'] = climate_data.get('flood_is_sfha')
        result['flood_score'] = climate_data.get('flood_score')

        # Get fire data
        result['fire_burn_probability'] = climate_data.get('fire_burn_probability')
        result['fire_score'] = climate_data.get('fire_score')

        # Get heat/cold data
        result['heat_days'] = climate_data.get('heat_days')
        result['heat_score'] = climate_data.get('heat_score')
        result['cold_days'] = climate_data.get('cold_days')
        result['cold_score'] = climate_data.get('cold_score')

        # Get combined score
        result['final_score'] = climate_data.get('final_score')
        result['notes'] = climate_data.get('notes', 'Climate data available')

        return result

    def _calculate_employer_stability_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Employer Stability / Recession Resistance score (5% weight).

        Uses BLS QCEW data to analyze county employment mix.
        Scores based on:
        - % in recession-proof industries (healthcare, education, government)
        - % in essential services (retail, transport)
        - % in cyclical industries (construction, manufacturing, hospitality)
        - Industry concentration risk

        Returns dict with all intermediate values for transparency.
        """
        web_demo = data.get('web_demographics', {})
        employer_data = web_demo.get('employer_stability_data', {})

        result = {
            'source': 'BLS QCEW',
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
            'final_score': None,
            'notes': None,
        }

        # Check if we have employer stability data
        if not employer_data or employer_data.get('error'):
            error_msg = employer_data.get('error', 'No employer data') if employer_data else 'No employer data'
            result['notes'] = f'Employer stability unavailable: {error_msg}'
            return result

        # Copy all data from the checker result
        result['county_fips'] = employer_data.get('county_fips')
        result['county_name'] = employer_data.get('county_name')
        result['state'] = employer_data.get('state')
        result['total_employment'] = employer_data.get('total_employment')
        result['government_pct'] = employer_data.get('government_pct')
        result['recession_proof_pct'] = employer_data.get('recession_proof_pct')
        result['essential_pct'] = employer_data.get('essential_pct')
        result['moderate_pct'] = employer_data.get('moderate_pct')
        result['cyclical_pct'] = employer_data.get('cyclical_pct')
        result['rri'] = employer_data.get('rri')
        result['concentration_adj'] = employer_data.get('concentration_adj')
        result['final_score'] = employer_data.get('final_score')
        result['notes'] = employer_data.get('notes', 'Employer data available')

        return result