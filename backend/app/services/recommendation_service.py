"""
AquaLens AI - Deterministic Recommendation Engine
Generates evidence-based, traceable recommendations derived strictly from
feature deviations, data quality warnings, and baseline comparison.
Never invents contamination sources or chemical potability conclusions.
"""

import json
from typing import List, Optional
from sqlalchemy.orm import Session

from ..db.models import (
    MonitoringStation,
    Observation,
    AnomalyResult,
    Recommendation,
)


class RecommendationService:
    @classmethod
    def generate_recommendations_for_observation(
        cls,
        db: Session,
        observation: Observation,
    ) -> List[Recommendation]:
        """
        Derives actionable recommendations based strictly on:
        1. Anomaly severity and persistence
        2. Dominant deviating features
        3. Acquisition and lighting flags
        """
        recs = []
        station_id = observation.station_id
        anomaly: Optional[AnomalyResult] = observation.anomaly_result

        if not anomaly or anomaly.status == "unassessed":
            rec = Recommendation(
                station_id=station_id,
                observation_id=observation.id,
                category="QualityControl",
                title="Establish Validated Station Baseline",
                description=(
                    "This observation lacks an established source-specific baseline. "
                    "Fingerprinting requires at least 5 validated reference observations under consistent conditions."
                ),
                hypothesis="Baseline not yet initialized for this sampling point.",
                action_items_json=json.dumps([
                    "Schedule regular visual image acquisition across consecutive days.",
                    "Verify camera alignment and shroud positioning at the station.",
                    "Record concurrent ambient weather and illumination conditions.",
                ]),
                priority="medium",
            )
            recs.append(rec)
            return recs

        deviations = anomaly.get_deviations()
        top_features = anomaly.get_top_contributors()

        # Rule 1: High texture intensity variance
        if "texture_intensity_variance" in deviations and deviations["texture_intensity_variance"]["is_deviated"]:
            dev = deviations["texture_intensity_variance"]
            recs.append(
                Recommendation(
                    station_id=station_id,
                    observation_id=observation.id,
                    category="AcquisitionCheck",
                    title="Inspect Water Surface Roughness & Camera Glare",
                    description=(
                        f"Texture intensity variance is {dev['observed_value']}, deviating from the reference "
                        f"median of {dev['baseline_median']} (robust z-score: {dev['robust_z_score']})."
                    ),
                    hypothesis=(
                        "Hypothesis: Possible direct sunlight reflections, rapid surface turbulence, "
                        "or surface suspended particulates."
                    ),
                    action_items_json=json.dumps([
                        "Check station camera polarizing filter or hood for optical glare.",
                        "Inspect water surface for turbulent flow or surface foam.",
                        "Perform follow-up image acquisition during diffused lighting (overcast/shaded).",
                    ]),
                    priority="medium" if anomaly.status == "potential_anomaly" else "high",
                )
            )

        # Rule 2: Color ratio / cast shift (colour_cast_blue_red or colour_ratio_gb)
        color_shifted = any(
            f in deviations and deviations[f]["is_deviated"]
            for f in ["colour_cast_blue_red", "colour_ratio_gb", "colour_ratio_rb", "hsv_hue_median"]
        )
        if color_shifted:
            recs.append(
                Recommendation(
                    station_id=station_id,
                    observation_id=observation.id,
                    category="LaboratoryVerification",
                    title="Recommend Turbidity & Suspended Solids Verification",
                    description=(
                        "Chromatic descriptors show statistically significant departure from the station's historical baseline."
                    ),
                    hypothesis=(
                        "Hypothesis: Visual hue and chromatic shifts often correlate with suspended sediment runoff, "
                        "organic tannin presence, or phytoplankton blooms."
                    ),
                    action_items_json=json.dumps([
                        "Collect a grab sample for laboratory Turbidity (NTU) measurement.",
                        "Perform Total Suspended Solids (TSS) gravimetric test.",
                        "Check upstream catchment for recent rainfall or dredging activities.",
                    ]),
                    priority="high" if anomaly.status == "persistent_anomaly" else "medium",
                )
            )

        # Rule 3: Persistent Anomaly
        if anomaly.status == "persistent_anomaly":
            recs.append(
                Recommendation(
                    station_id=station_id,
                    observation_id=observation.id,
                    category="AnomalyInvestigation",
                    title="Initiate Multi-Observation Trend Verification Protocol",
                    description=(
                        "Deviations have persisted across consecutive observation windows at this monitoring station."
                    ),
                    hypothesis=(
                        "Hypothesis: Sustained optical change may indicate an enduring hydrological event "
                        "or station sensor drift."
                    ),
                    action_items_json=json.dumps([
                        "Dispatch field officer to inspect sensor lens cleanliness.",
                        "Cross-reference with municipal rainfall and flow-rate telemetry.",
                        "Collect certified laboratory sample for comprehensive physicochemical analysis (DO, pH, Conductivity).",
                    ]),
                    priority="high",
                )
            )

        # Default normal variation rule
        if not recs and anomaly.status == "normal_variation":
            recs.append(
                Recommendation(
                    station_id=station_id,
                    observation_id=observation.id,
                    category="MonitoringRoutine",
                    title="Routine Sampling Cycle Maintained",
                    description="Observation matches the station's established baseline within normal statistical bounds.",
                    hypothesis="System is in stable equilibrium.",
                    action_items_json=json.dumps([
                        "Continue scheduled visual telemetry according to standard monitoring intervals.",
                        "No immediate physical inspection required.",
                    ]),
                    priority="low",
                )
            )

        return recs

    @classmethod
    def sync_recommendations(cls, db: Session, observation: Observation) -> List[Recommendation]:
        recs = cls.generate_recommendations_for_observation(db, observation)
        # Clear previous recs for this observation
        db.query(Recommendation).filter(Recommendation.observation_id == observation.id).delete()
        for r in recs:
            db.add(r)
        db.commit()
        return recs
