"""
mesocycle_engine.py
Hét-szintű (microcycle) progressziót generál egy adott Phase-en belül,
a meglévő periodization_engine.py WeeklyPlan logikájára építve.
 
Alapok:
- NSCA (Bompa/Haff): mesociklus 2-6 hét, tipikusan 4 hét, utolsó hét deload.
- EXOS / gyakorlati konszenzus: 3:1 vagy 4:1 terhelés:deload arány,
  deload = volumen -30-50%, intenzitás fenntartva vagy enyhén csökkentve.
"""
 
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import copy
 
from periodization_engine import (
    WeeklyPlan,
    Phase,
    StrengthModel,
    generate_weekly_plan,  # feltételezett meglévő függvény neve
)
 
 
class LoadPattern(Enum):
    ASCENDING = "ascending"      # 3:1 vagy 4:1, lineáris emelés
    STEP = "step"                # DUP-szerű, blokkonta ugrás
    WAVE = "wave"                # hullámzó (pl. 2 fel, 1 vissza, 1 fel)
 
 
@dataclass
class MicrocyclePlan:
    week_number: int
    is_deload: bool
    weekly_plan: WeeklyPlan
    volume_multiplier: float
    intensity_multiplier: float
    notes: List[str] = field(default_factory=list)
 
 
@dataclass
class MesocyclePlan:
    phase: Phase
    strength_model: StrengthModel
    duration_weeks: int
    deload_ratio: int           # pl. 4 -> minden 4. hét deload
    microcycles: List[MicrocyclePlan] = field(default_factory=list)
 
 
# ---------------------------------------------------------------------------
# Szabályok: fázis -> javasolt mesociklus-hossz és deload-arány
# NSCA/EXOS alapján: minél közelebb a versenyhez (Peak), annál rövidebb
# a blokk és gyakoribb/finomabb a deload.
# ---------------------------------------------------------------------------
PHASE_DURATION_RULES = {
    Phase.GPP:        {"duration_weeks": 4, "deload_ratio": 4},  # 3:1
    Phase.BUILD:      {"duration_weeks": 4, "deload_ratio": 4},  # 3:1
    Phase.PEAK:       {"duration_weeks": 3, "deload_ratio": 3},  # 2:1 - óvatosabb
    Phase.TRANSITION: {"duration_weeks": 2, "deload_ratio": None},  # nincs deload, maga a fázis regeneráció
}
 
DELOAD_VOLUME_REDUCTION = 0.4       # -40% volumen deload héten (30-50% tartomány középértéke)
DELOAD_INTENSITY_REDUCTION = 0.1    # intenzitás enyhe csökkentése (vagy fenntartás, modell függő)
 
 
def _progression_curve(week_in_block: int, total_build_weeks: int, pattern: LoadPattern) -> float:
    """
    Visszaad egy 0 és 1 közötti szorzót, amely a volumen/intenzitás
    progresszióját reprezentálja a deload előtti heteken belül.
    week_in_block: 1-alapú index a build hetek között (deload nélkül számolva)
    """
    if total_build_weeks <= 1:
        return 1.0
 
    fraction = (week_in_block - 1) / (total_build_weeks - 1)  # 0.0 .. 1.0
 
    if pattern == LoadPattern.ASCENDING:
        # lineáris emelés: 0.85 -> 1.0 tartományban mozgatjuk a bázisértékhez képest
        return 0.85 + 0.15 * fraction
 
    elif pattern == LoadPattern.STEP:
        # DUP-szerű: minden hét "ugrik" egy diszkrét szintet
        steps = [0.85, 0.92, 1.0, 1.05]
        idx = min(week_in_block - 1, len(steps) - 1)
        return steps[idx]
 
    elif pattern == LoadPattern.WAVE:
        # hullámzó: 2 hét fel, 1 hét vissza mintázat
        wave_pattern = [0.90, 1.0, 0.95, 1.05]
        idx = (week_in_block - 1) % len(wave_pattern)
        return wave_pattern[idx]
 
    return 1.0
 
 
def _apply_multiplier_to_plan(base_plan: WeeklyPlan, volume_mult: float,
                                intensity_mult: float) -> WeeklyPlan:
    """
    A base WeeklyPlan-t módosítja a megadott szorzókkal.
    Feltételezzük, hogy a WeeklyPlan tartalmaz strength_intensity_range-t
    és valamilyen volumen-reprezentációt (pl. strength_sessions_per_week
    vagy egy explicit volume mezőt - itt az intenzitás tartományt toljuk el,
    és egy volume_adjustment jegyzetet adunk hozzá, mivel a session-szám
    egész szám és nem skálázható folytonosan).
    """
    plan = copy.deepcopy(base_plan)
 
    low, high = plan.strength_intensity_range
    plan.strength_intensity_range = (
        round(low * intensity_mult, 3),
        round(high * intensity_mult, 3),
    )
 
    plan.notes = list(plan.notes) if plan.notes else []
    plan.notes.append(
        f"Volumen-szorzó: {volume_mult:.2f} | Intenzitás-szorzó: {intensity_mult:.2f}"
    )
 
    return plan
 
 
def generate_mesocycle(
    phase: Phase,
    strength_model: StrengthModel,
    endurance_inputs: dict,
    strength_inputs: dict,
    pattern: LoadPattern = LoadPattern.ASCENDING,
    duration_weeks: Optional[int] = None,
    deload_ratio: Optional[int] = None,
) -> MesocyclePlan:
    """
    Egy adott fázishoz legenerálja a teljes mesociklust, hétről hétre
    bontva, a megfelelő progresszióval és deload-logikával.
 
    Paraméterek:
        phase: a makrociklus aktuális fázisa (GPP, BUILD, PEAK, TRANSITION)
        strength_model: a meglévő motor StrengthModel enumja
        endurance_inputs / strength_inputs: a generate_weekly_plan()
            számára szükséges bemenetek (változatlanul továbbadva)
        pattern: terhelés-progresszió mintázata a build heteken belül
        duration_weeks / deload_ratio: felülírható az alapértelmezett
            fázis-szabályokhoz képest
    """
    rules = PHASE_DURATION_RULES[phase]
    total_weeks = duration_weeks or rules["duration_weeks"]
    ratio = deload_ratio if deload_ratio is not None else rules["deload_ratio"]
 
    base_plan = generate_weekly_plan(
        phase=phase,
        strength_model=strength_model,
        endurance_inputs=endurance_inputs,
        strength_inputs=strength_inputs,
    )
 
    microcycles: List[MicrocyclePlan] = []
 
    if ratio is None:
        # Transition fázis: nincs klasszikus deload-logika, minden hét
        # alacsony terhelésű regenerációs hét.
        for week in range(1, total_weeks + 1):
            reduced_plan = _apply_multiplier_to_plan(base_plan, 0.5, 0.85)
            microcycles.append(MicrocyclePlan(
                week_number=week,
                is_deload=False,
                weekly_plan=reduced_plan,
                volume_multiplier=0.5,
                intensity_multiplier=0.85,
                notes=["Transition fázis: aktív regeneráció, nincs progresszió."],
            ))
        return MesocyclePlan(
            phase=phase,
            strength_model=strength_model,
            duration_weeks=total_weeks,
            deload_ratio=ratio,
            microcycles=microcycles,
        )
 
    build_weeks_per_block = ratio - 1  # pl. ratio=4 -> 3 build hét + 1 deload
    week_counter = 0
    block_week_counter = 0
 
    while week_counter < total_weeks:
        week_counter += 1
        block_week_counter += 1
 
        is_deload = (block_week_counter == ratio)
 
        if is_deload:
            volume_mult = 1.0 - DELOAD_VOLUME_REDUCTION
            intensity_mult = 1.0 - DELOAD_INTENSITY_REDUCTION
            note = (
                f"Deload hét ({ratio}:1 arány): volumen -{DELOAD_VOLUME_REDUCTION*100:.0f}%, "
                f"intenzitás -{DELOAD_INTENSITY_REDUCTION*100:.0f}% (NSCA/EXOS konszenzus)."
            )
            block_week_counter = 0  # új blokk kezdődik
        else:
            progression = _progression_curve(block_week_counter, build_weeks_per_block, pattern)
            volume_mult = progression
            intensity_mult = progression
            note = f"Build hét {block_week_counter}/{build_weeks_per_block} ({pattern.value} progresszió)."
 
        adjusted_plan = _apply_multiplier_to_plan(base_plan, volume_mult, intensity_mult)
 
        microcycles.append(MicrocyclePlan(
            week_number=week_counter,
            is_deload=is_deload,
            weekly_plan=adjusted_plan,
            volume_multiplier=round(volume_mult, 3),
            intensity_multiplier=round(intensity_mult, 3),
            notes=[note],
        ))
 
    return MesocyclePlan(
        phase=phase,
        strength_model=strength_model,
        duration_weeks=total_weeks,
        deload_ratio=ratio,
        microcycles=microcycles,
    )
 
 
# ---------------------------------------------------------------------------
# Gyors manuális teszt
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    example_endurance_inputs = {"weekly_hours": 8, "discipline": "running"}
    example_strength_inputs = {"experience_level": "intermediate"}
 
    meso = generate_mesocycle(
        phase=Phase.BUILD,
        strength_model=StrengthModel.LINEAR,
        endurance_inputs=example_endurance_inputs,
        strength_inputs=example_strength_inputs,
        pattern=LoadPattern.ASCENDING,
    )
 
    print(f"Fázis: {meso.phase}, hossz: {meso.duration_weeks} hét, deload arány: {meso.deload_ratio}:1\n")
    for mc in meso.microcycles:
        tag = "DELOAD" if mc.is_deload else "BUILD"
        print