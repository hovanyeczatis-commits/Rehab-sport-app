# mesocycle_engine.py
 
from dataclasses import dataclass, field
from typing import List, Optional
from periodization_engine import WeeklyPlan, generate_weekly_plan  # meglévő motor
 
# --- Deload szabályok fázisonként (NSCA / EXOS alapján) ---
# Base: 3:1 (3 terhelő hét, 1 deload)
# Build: 3:1, de magasabb intenzitással
# Peak: 2:1 (rövidebb ciklus, nagyobb fáradtság-akkumuláció)
# Taper: nincs klasszikus deload, hanem monoton volumencsökkentés
 
DELOAD_PATTERNS = {
    "base": {"cycle_length": 4, "deload_week_index": 3},   # 0,1,2 terhelő, 3 deload
    "build": {"cycle_length": 4, "deload_week_index": 3},
    "peak": {"cycle_length": 3, "deload_week_index": 2},
    "taper": {"cycle_length": None, "deload_week_index": None},  # speciális kezelés
}
 
DELOAD_VOLUME_MULTIPLIER = 0.6   # deload héten a volumen ~60%-ra csökken
DELOAD_INTENSITY_MULTIPLIER = 0.9  # intenzitás kevésbé csökken, mint volumen
 
 
@dataclass
class MesocyclePlan:
    phase: str
    duration_weeks: int
    weekly_plans: List[WeeklyPlan]
    deload_weeks: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
 
 
def _is_deload_week(phase: str, week_index: int) -> bool:
    """week_index: 0-tól indexelt, a mezocikluson belüli hét sorszáma."""
    pattern = DELOAD_PATTERNS.get(phase)
    if pattern is None or pattern["cycle_length"] is None:
        return False
    return (week_index % pattern["cycle_length"]) == pattern["deload_week_index"]
 
 
def _apply_taper_progression(week_index: int, total_weeks: int, base_plan: WeeklyPlan) -> WeeklyPlan:
    """
    Taper fázis: monoton, nem lépcsős volumencsökkenés.
    Lineáris lecsökkentés a hét sorszáma alapján, az utolsó hét a legkönnyebb.
    Intenzitás szinten tartva vagy enyhén emelve (sebesség/erő megtartás miatt).
    """
    progress_ratio = (week_index + 1) / total_weeks  # pl. 1/3, 2/3, 3/3
    volume_multiplier = 1.0 - (0.5 * progress_ratio)  # max 50%-os csökkenés a végére
 
    adjusted = WeeklyPlan(
        zone_distribution=base_plan.zone_distribution,
        strength_sessions_per_week=max(1, round(base_plan.strength_sessions_per_week * volume_multiplier)),
        strength_intensity_range=(
            base_plan.strength_intensity_range[0],
            min(0.95, base_plan.strength_intensity_range[1] + 0.05),  # kicsit nő a csúcsintenzitás
        ),
        model_name=base_plan.model_name,
        interference_rule=base_plan.interference_rule,
        notes=base_plan.notes + [f"Taper hét {week_index+1}/{total_weeks}: volumen {volume_multiplier:.0%}"],
    )
    return adjusted
 
 
def _apply_deload_adjustment(base_plan: WeeklyPlan, week_label: str) -> WeeklyPlan:
    """Deload héten: volumen (session-szám) csökken jobban, mint az intenzitás."""
    adjusted = WeeklyPlan(
        zone_distribution=base_plan.zone_distribution,
        strength_sessions_per_week=max(1, round(base_plan.strength_sessions_per_week * DELOAD_VOLUME_MULTIPLIER)),
        strength_intensity_range=(
            base_plan.strength_intensity_range[0] * DELOAD_INTENSITY_MULTIPLIER,
            base_plan.strength_intensity_range[1] * DELOAD_INTENSITY_MULTIPLIER,
        ),
        model_name=base_plan.model_name,
        interference_rule=base_plan.interference_rule,
        notes=base_plan.notes + [f"Deload hét ({week_label}): volumen -{int((1-DELOAD_VOLUME_MULTIPLIER)*100)}%"],
    )
    return adjusted
 
 
def generate_mesocycle(
    phase: str,
    duration_weeks: int,
    athlete_profile: dict,
    sport: str,
) -> MesocyclePlan:
    """
    Fő generátor függvény: a macrocycle_engine.py által kiadott fázisból
    (phase, duration_weeks) és a sportoló profiljából heti bontású tervet épít.
 
    athlete_profile: dict, pl. {"endurance_level": "intermediate", "strength_level": "novice", ...}
    sport: pl. "triathlon", "running", "cycling" — továbbadva a periodization_engine-nek
    """
    weekly_plans: List[WeeklyPlan] = []
    deload_weeks: List[int] = []
    notes: List[str] = []
 
    for week_index in range(duration_weeks):
        # 1. Alap heti terv lekérése a meglévő motorból
        base_plan = generate_weekly_plan(
            phase=phase,
            athlete_profile=athlete_profile,
            sport=sport,
        )
 
        # 2. Fázis-specifikus módosítás
        if phase == "taper":
            final_plan = _apply_taper_progression(week_index, duration_weeks, base_plan)
        elif _is_deload_week(phase, week_index):
            final_plan = _apply_deload_adjustment(base_plan, week_label=f"{week_index+1}. hét")
            deload_weeks.append(week_index + 1)
        else:
            # Normál terhelő hét — enyhe progresszió a ciklus pozíciótól függően
            final_plan = base_plan
 
        weekly_plans.append(final_plan)
 
    if phase in DELOAD_PATTERNS and DELOAD_PATTERNS[phase]["cycle_length"]:
        notes.append(
            f"Deload minta: {DELOAD_PATTERNS[phase]['cycle_length']}:1 arány "
            f"({phase} fázis, NSCA/EXOS ajánlás alapján)."
        )
 
    return MesocyclePlan(
        phase=phase,
        duration_weeks=duration_weeks,
        weekly_plans=weekly_plans,
        deload_weeks=deload_weeks,
        notes=notes,
    )