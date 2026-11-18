"""
periodization_engine.py
Szabályalapú periodizációs döntési motor.
Bemenet: sportoló profilja -> Kimenet: javasolt heti struktúra (zóna-eloszlás, erő-paraméterek)
"""
 
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
 
 
class SportCategory(str, Enum):
    AEROBIC = "aerobic"              # A - hosszútávfutás, kerékpár, úszás, triatlon
    MIXED_INTERMITTENT = "mixed"     # B - foci, kosár, kézilabda, jégkorong
    ANAEROBIC_ALACTIC = "anaerobic"  # C - sprint, súlyemelés, dobóatlétika
    STRENGTH_HYPERTROPHY = "strength" # D - testépítés, erőemelés
 
 
class TrainingAge(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
 
 
class Phase(str, Enum):
    GPP = "general_prep"         # alapozó
    BUILD = "build_specific"     # sportágspecifikus build
    PEAK = "peak_competition"    # verseny-csúcsosítás
    TRANSITION = "transition"    # átmeneti/regeneráció
 
 
@dataclass
class AthleteProfile:
    sport_category: SportCategory
    training_age: TrainingAge
    current_phase: Phase
    weekly_available_sessions: int
    endurance_goal_weight: float = 0.5   # 0.0-1.0, mennyire domináns az állóképesség cél
    event_duration_minutes: Optional[int] = None  # pl. maraton vs 5km megkülönböztetéshez
 
 
@dataclass
class WeeklyPlan:
    zone_distribution: dict        # pl. {"Z1": 0.8, "Z2": 0.1, "Z3": 0.1}
    strength_sessions_per_week: int
    strength_intensity_range: tuple  # (%1RM min, max)
    model_name: str                  # pl. "polarized", "pyramidal", "block"
    interference_rule: str
    notes: list = field(default_factory=list)
 
 
def _get_zone_distribution(profile: AthleteProfile) -> tuple[dict, str]:
    """Visszaadja a zóna-eloszlást és a modell nevét a sportág-kategória és fázis alapján."""
 
    if profile.sport_category == SportCategory.AEROBIC:
        if profile.current_phase == Phase.GPP:
            return {"Z1": 0.80, "Z2": 0.10, "Z3": 0.10}, "polarized"
 
        elif profile.current_phase == Phase.BUILD:
            # Hosszabb versenytáv -> több küszöb körüli munka (piramidális eltolódás)
            if profile.event_duration_minutes and profile.event_duration_minutes > 60:
                return {"Z1": 0.70, "Z2": 0.20, "Z3": 0.10}, "pyramidal"
            else:
                return {"Z1": 0.75, "Z2": 0.15, "Z3": 0.10}, "polarized"
 
        elif profile.current_phase == Phase.PEAK:
            return {"Z1": 0.75, "Z2": 0.10, "Z3": 0.15}, "taper_sharpening"
 
        else:  # TRANSITION
            return {"Z1": 1.0, "Z2": 0.0, "Z3": 0.0}, "active_recovery"
 
    elif profile.sport_category == SportCategory.MIXED_INTERMITTENT:
        if profile.current_phase in (Phase.GPP, Phase.BUILD):
            return {"Z1": 0.50, "RSA_HIIT": 0.40, "Z3": 0.10}, "hiit_dominant"
        elif profile.current_phase == Phase.PEAK:
            return {"Z1": 0.40, "RSA_HIIT": 0.50, "Z3": 0.10}, "sport_specific_sim"
        else:
            return {"Z1": 1.0}, "active_recovery"
 
    elif profile.sport_category == SportCategory.ANAEROBIC_ALACTIC:
        # Állóképesség itt másodlagos -> minimális aerob kiegészítés
        return {"Z1": 0.9, "alactic_power": 0.1}, "force_velocity_continuum"
 
    else:  # STRENGTH_HYPERTROPHY
        return {}, "linear_or_block_strength"
 
 
def _get_strength_params(profile: AthleteProfile) -> tuple[int, tuple]:
    """Erő session-szám és intenzitás-tartomány meghatározása."""
 
    base_sessions = {
        TrainingAge.BEGINNER: 2,
        TrainingAge.INTERMEDIATE: 3,
        TrainingAge.ADVANCED: 3,
    }[profile.training_age]
 
    # Ha állóképesség-domináns a sportág és a cél, csökkentjük az erő-frekvenciát
    if profile.sport_category == SportCategory.AEROBIC and profile.endurance_goal_weight > 0.6:
        base_sessions = min(base_sessions, 2)
 
    intensity_by_phase = {
        Phase.GPP: (0.60, 0.70),
        Phase.BUILD: (0.70, 0.85),
        Phase.PEAK: (0.80, 0.95),
        Phase.TRANSITION: (0.0, 0.0),
    }
 
    return base_sessions, intensity_by_phase[profile.current_phase]
 
 
def _get_interference_rule(profile: AthleteProfile) -> str:
    """Konkurens edzés (erő + állóképesség) kezelési szabálya."""
 
    if profile.sport_category == SportCategory.AEROBIC:
        return ("Állóképesség prioritás: erő max 2x/hét, min. 6 óra elválasztás "
                "azonos napi session esetén, erő mindig állóképesség UTÁN.")
 
    elif profile.sport_category == SportCategory.MIXED_INTERMITTENT:
        return ("Erő/erő-sebesség prioritás, aerob csak fenntartó szinten. "
                "Interferencia-kockázat közepes, kerülni a nagy volumenű extenzív "
                "futást közvetlenül erő-sebesség session előtt.")
 
    elif profile.sport_category == SportCategory.ANAEROBIC_ALACTIC:
        return "Interferencia-kockázat alacsony, aerob komponens minimális."
 
    else:
        return "Nincs releváns interferencia-szabály (tiszta erő/hipertrófia cél)."
 
 
def generate_weekly_plan(profile: AthleteProfile) -> WeeklyPlan:
    """Fő belépési pont: profil alapján legenerálja a heti tervet."""
 
    zone_distribution, model_name = _get_zone_distribution(profile)
    strength_sessions, intensity_range = _get_strength_params(profile)
    interference_rule = _get_interference_rule(profile)
 
    notes = []
    if profile.weekly_available_sessions < strength_sessions + 2:
        notes.append(
            "Figyelem: a rendelkezésre álló heti session-szám alacsonyabb, mint "
            "az ajánlott minimum. Javasolt kombinált (hibrid) session-ek beépítése."
        )
 
    return WeeklyPlan(
        zone_distribution=zone_distribution,
        strength_sessions_per_week=strength_sessions,
        strength_intensity_range=intensity_range,
        model_name=model_name,
        interference_rule=interference_rule,
        notes=notes,
    )
 
 
# --- Gyors teszt futtatáshoz ---
if __name__ == "__main__":
    test_profile = AthleteProfile(
        sport_category=SportCategory.AEROBIC,
        training_age=TrainingAge.INTERMEDIATE,
        current_phase=Phase.BUILD,
        weekly_available_sessions=6,
        endurance_goal_weight=0.8,
        event_duration_minutes=150,  # pl. maraton
    )
 
    plan = generate_weekly_plan(test_profile)
    print(plan)