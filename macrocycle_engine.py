"""
macrocycle_engine.py
 
Makrociklus-szintű periodizációs motor.
A MesocyclePlan-eket fázisokba (GPP, Build, Peak, Taper, Transition)
rendezi és összefűzi a cél típusa és a hátralévő idő alapján.
 
Épít a korábbi periodization_engine.py WeeklyPlan/MesocyclePlan logikájára.
"""
 
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional
 
# ---------------------------------------------------------------------------
# Feltételezett importok a meglévő motorból (periodization_engine.py)
# ---------------------------------------------------------------------------
# from periodization_engine import (
#     WeeklyPlan,
#     MesocyclePlan,
#     generate_mesocycle,
#     GoalType,
# )
 
 
class PhaseType(str, Enum):
    GPP = "GPP"                # General Physical Preparation
    BUILD = "Build"            # Sportágspecifikus építő fázis
    PEAK = "Peak"              # Intenzitás-dominált, csúcsra járatás előkészítés
    TAPER = "Taper"            # Verseny előtti levezetés
    TRANSITION = "Transition"  # Aktív pihenő / szezon utáni
 
 
@dataclass
class MesocyclePlan:
    """Feltételezett struktúra az előző lépésből — ide illesztve a kontextushoz."""
    phase: PhaseType
    week_count: int
    weekly_plans: List[object] = field(default_factory=list)  # List[WeeklyPlan]
    notes: List[str] = field(default_factory=list)
 
 
@dataclass
class MacrocyclePlan:
    goal_type: str
    target_date: date
    total_weeks: int
    mesocycles: List[MesocyclePlan] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Sportág-specifikus taper szabályok (NSCA + irodalom alapján, kiindulási keret)
# ---------------------------------------------------------------------------
 
TAPER_RULES = {
    "endurance_long":      {"weeks": 2, "volume_reduction": 0.50, "intensity_change": 0.0},   # pl. maraton
    "endurance_short":     {"weeks": 1, "volume_reduction": 0.40, "intensity_change": 0.05},  # pl. 5-10km
    "team_sport":          {"weeks": 1, "volume_reduction": 0.30, "intensity_change": 0.0},   # csapatsport, szezonstruktúra miatt rövidebb
    "strength_power":      {"weeks": 2, "volume_reduction": 0.60, "intensity_change": 0.05},  # erőemelés/power, NSCA klasszikus taper
    "default":             {"weeks": 1, "volume_reduction": 0.40, "intensity_change": 0.0},
}
 
 
# ---------------------------------------------------------------------------
# Fázisarány-meghatározás a hátralévő idő alapján
# ---------------------------------------------------------------------------
 
def _determine_phase_structure(goal_type: str, weeks_to_goal: int) -> List[tuple]:
    """
    Visszaadja a fázisok sorrendjét és hosszát (hetekben) tuple listaként:
    [(PhaseType, week_count), ...]
 
    Szabályok (edzéselméleti keret, NSCA / Bompa alapján):
    - Taper hossza és mértéke sportág-specifikus (lásd TAPER_RULES).
    - Ha a hátralévő idő rövid (<6 hét), GPP kimarad vagy minimális (1 hét),
      a hangsúly Build/Peak-re tolódik.
    - Minimum 1 hetes GPP mindig ajánlott, ha az idő engedi (edzésalap nélkül
      a Build fázis sérülésveszélyes terhelésugrást jelentene).
    - Transition fázis csak akkor kerül be, ha a motor több egymást követő
      makrociklust fűzne össze (itt: egyetlen célra optimalizált láncnál nem,
      csak jelzésként szerepel a végén, ha weeks_to_goal elegendő).
    """
    taper_rule = TAPER_RULES.get(goal_type, TAPER_RULES["default"])
    taper_weeks = taper_rule["weeks"]
 
    remaining = weeks_to_goal - taper_weeks
    if remaining < 1:
        # Extrém rövid idő: csak taper, figyelmeztetéssel a hívó oldalon kezelendő
        return [(PhaseType.TAPER, max(weeks_to_goal, 1))]
 
    # Arányok: GPP 30% / Build 45% / Peak 25% a taper előtti időből,
    # minimum 1-1 hét biztosításával
    gpp_weeks = max(1, round(remaining * 0.30)) if remaining >= 4 else 0
    build_weeks = max(1, round(remaining * 0.45))
    peak_weeks = remaining - gpp_weeks - build_weeks
 
    if peak_weeks < 1:
        # Igazítás: Peak-nek mindig kell legalább 1 hét a Taper előtt
        diff = 1 - peak_weeks
        peak_weeks = 1
        build_weeks = max(1, build_weeks - diff)
 
    phases = []
    if gpp_weeks > 0:
        phases.append((PhaseType.GPP, gpp_weeks))
    phases.append((PhaseType.BUILD, build_weeks))
    phases.append((PhaseType.PEAK, peak_weeks))
    phases.append((PhaseType.TAPER, taper_weeks))
 
    return phases
 
 
# ---------------------------------------------------------------------------
# Fázis-specifikus modellválasztás (kapcsolódás a periodization_engine logikához)
# ---------------------------------------------------------------------------
 
def _phase_model_adjustments(phase: PhaseType) -> dict:
    """
    Visszaadja, hogy az adott fázisban milyen irányba kell tolni
    a meglévő generate_mesocycle() paramétereit.
 
    Ez a réteg NEM duplikálja a zóna-eloszlás / erő-session logikát,
    csak a fázis-specifikus "súlyokat" adja át a mesociklus generátornak.
    """
    if phase == PhaseType.GPP:
        return {
            "endurance_emphasis": "volume",       # alapállóképesség-építés
            "strength_emphasis": "hypertrophy",   # izom-keresztmetszet, alapstabilitás
            "intensity_bias": "low",
        }
    elif phase == PhaseType.BUILD:
        return {
            "endurance_emphasis": "mixed",        # zóna-eloszlás a modellhez igazodva (polarizált/piramidális)
            "strength_emphasis": "strength",
            "intensity_bias": "medium",
        }
    elif phase == PhaseType.PEAK:
        return {
            "endurance_emphasis": "intensity",    # csökkenő volumen, emelkedő intenzitás (verseny-specifikus zónák)
            "strength_emphasis": "power",         # erő-sebesség kontinuum felé (Suchomel)
            "intensity_bias": "high",
        }
    elif phase == PhaseType.TAPER:
        return {
            "endurance_emphasis": "maintenance",
            "strength_emphasis": "power_maintenance",
            "intensity_bias": "maintained_or_slightly_up",
        }
    else:  # TRANSITION
        return {
            "endurance_emphasis": "active_recovery",
            "strength_emphasis": "none_or_general",
            "intensity_bias": "very_low",
        }
 
 
# ---------------------------------------------------------------------------
# Folytonossági ellenőrzés: ne legyen két egymást követő deload-szerű hét
# fázisváltásnál (pl. Build utolsó hete deload + Peak első hete taper-szerű)
# ---------------------------------------------------------------------------
 
def _validate_phase_transitions(mesocycles: List[MesocyclePlan]) -> List[str]:
    """
    Egyszerű heurisztikus ellenőrzés a fázisok határán.
    Feltételezi, hogy minden MesocyclePlan.weekly_plans utolsó eleme
    rendelkezik 'is_deload' attribútummal (a meglévő motorból örökölve).
    """
    warnings = []
    for i in range(len(mesocycles) - 1):
        current = mesocycles[i]
        next_meso = mesocycles[i + 1]
 
        current_last_deload = (
            bool(current.weekly_plans)
            and getattr(current.weekly_plans[-1], "is_deload", False)
        )
        next_first_deload = (
            bool(next_meso.weekly_plans)
            and getattr(next_meso.weekly_plans[0], "is_deload", False)
        )
 
        if current_last_deload and next_first_deload:
            warnings.append(
                f"Figyelem: {current.phase.value} utolsó hete és "
                f"{next_meso.phase.value} első hete is deload-jellegű — "
                f"terhelés-folytonossági kockázat, fázishatár felülvizsgálata javasolt."
            )
 
    return warnings
 
 
# ---------------------------------------------------------------------------
# Fő belépési pont
# ---------------------------------------------------------------------------
 
def generate_macrocycle(
    goal_type: str,
    target_date: date,
    start_date: Optional[date] = None,
    athlete_level: str = "intermediate",
) -> MacrocyclePlan:
    """
    Fő generátor függvény.
 
    Paraméterek:
        goal_type: pl. "endurance_long", "endurance_short", "team_sport",
                   "strength_power" — meghatározza a taper-szabályt és
                   a fázis-hangsúlyokat.
        target_date: a célesemény (verseny) dátuma.
        start_date: tervezés kezdete (alapértelmezett: ma).
        athlete_level: a mesociklus-generátor felé továbbított kontextus
                       (pl. deload-gyakoriság módosításához).
 
    Visszatér: MacrocyclePlan, benne a fázisokra bontott mesociklusokkal.
 
    FONTOS: a tényleges WeeklyPlan-ek legenerálása a meglévő
    generate_mesocycle() hívásával történik (periodization_engine.py),
    itt csak a fázis-struktúra és a köztük lévő döntési logika szerepel.
    A generate_mesocycle() hívását placeholderként jelöltem, mivel a
    pontos szignatúrája a te kódodban van — ezt a következő lépésben
    be kell illeszteni.
    """
    if start_date is None:
        start_date = date.today()
 
    weeks_to_goal = max(1, (target_date - start_date).days // 7)
    phase_structure = _determine_phase_structure(goal_type, weeks_to_goal)
 
    mesocycles: List[MesocyclePlan] = []
    notes: List[str] = []
 
    if weeks_to_goal < 6:
        notes.append(
            "Rövid felkészülési idő (<6 hét): GPP fázis kihagyva vagy minimálisra "
            "csökkentve, sérülésveszély-kockázat emelkedhet hirtelen terhelésnövekedés esetén."
        )