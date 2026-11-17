from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from pydantic import BaseModel
from datetime import date
from typing import Optional, List
import os

# ---------------------------------------------------------
# 1. ADATBÁZIS KAPCSOLAT
# ---------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./rehab.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------
# 2. ADATBÁZIS MODELLEK (TÁBLÁK)
# ---------------------------------------------------------

class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    sport = Column(String)
    birth_date = Column(Date)
    sex = Column(String)
    height_cm = Column(Float)
    weight_kg = Column(Float)

    injuries = relationship("InjuryHistory", back_populates="athlete")
    sessions = relationship("TrainingSession", back_populates="athlete")
    wellness_logs = relationship("WellnessLog", back_populates="athlete")
    rtp_progress = relationship("RTPProgress", back_populates="athlete")
    risk_flags = relationship("RiskFlag", back_populates="athlete")


class InjuryHistory(Base):
    __tablename__ = "injury_history"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    injury_type = Column(String)
    body_part = Column(String)
    date_occurred = Column(Date)
    severity = Column(String)
    notes = Column(Text)

    athlete = relationship("Athlete", back_populates="injuries")


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    session_date = Column(Date)
    session_type = Column(String)
    duration_min = Column(Float)
    rpe = Column(Float)  # Rating of Perceived Exertion (0-10)
    load_au = Column(Float)  # sRPE = duration * RPE

    athlete = relationship("Athlete", back_populates="sessions")


class WellnessLog(Base):
    __tablename__ = "wellness_logs"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    log_date = Column(Date)
    sleep_quality = Column(Float)
    fatigue = Column(Float)
    soreness = Column(Float)
    stress = Column(Float)
    mood = Column(Float)

    athlete = relationship("Athlete", back_populates="wellness_logs")


class LoadMetric(Base):
    __tablename__ = "load_metrics"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    metric_date = Column(Date)
    acute_load = Column(Float)      # 7 napos átlag
    chronic_load = Column(Float)    # 28 napos átlag
    acwr = Column(Float)            # Acute:Chronic Workload Ratio


class BiomechanicalTest(Base):
    __tablename__ = "biomechanical_tests"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    test_date = Column(Date)
    test_name = Column(String)
    limb_symmetry_index = Column(Float)
    result_value = Column(Float)
    notes = Column(Text)


class RTPProtocol(Base):
    __tablename__ = "rtp_protocols"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    injury_type = Column(String)
    phase_number = Column(Integer)
    phase_name = Column(String)
    criteria = Column(Text)
    description = Column(Text)


class RTPProgress(Base):
    __tablename__ = "rtp_progress"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    protocol_id = Column(Integer, ForeignKey("rtp_protocols.id"))
    current_phase = Column(Integer)
    start_date = Column(Date)
    status = Column(String)  # pl. "in_progress", "completed", "regressed"
    notes = Column(Text)

    athlete = relationship("Athlete", back_populates="rtp_progress")


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"))
    flag_date = Column(Date)
    risk_type = Column(String)
    risk_level = Column(String)  # low / moderate / high
    source_metric = Column(String)
    recommendation = Column(Text)

    athlete = relationship("Athlete", back_populates="risk_flags")


Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------
# 3. PYDANTIC SÉMÁK (API bemenet/kimenet)
# ---------------------------------------------------------

class AthleteCreate(BaseModel):
    name: str
    sport: Optional[str] = None
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None


class AthleteOut(AthleteCreate):
    id: int

    class Config:
        from_attributes = True


class TrainingSessionCreate(BaseModel):
    athlete_id: int
    session_date: date
    session_type: Optional[str] = None
    duration_min: float
    rpe: float


class TrainingSessionOut(TrainingSessionCreate):
    id: int
    load_au: float

    class Config:
        from_attributes = True


class WellnessLogCreate(BaseModel):
    athlete_id: int
    log_date: date
    sleep_quality: float
    fatigue: float
    soreness: float
    stress: float
    mood: float


class WellnessLogOut(WellnessLogCreate):
    id: int

    class Config:
        from_attributes = True


class RiskFlagOut(BaseModel):
    id: int
    athlete_id: int
    flag_date: date
    risk_type: str
    risk_level: str
    source_metric: str
    recommendation: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# 4. FASTAPI ALKALMAZÁS
# ---------------------------------------------------------

app = FastAPI(title="Rehab & RTP Edzéstámogató Rendszer")


@app.get("/")
def root():
    return {"status": "ok", "message": "Rehab-sport-app API fut"}


# --- SPORTOLÓK ---

@app.post("/athletes", response_model=AthleteOut)
def create_athlete(athlete: AthleteCreate, db: Session = Depends(get_db)):
    db_athlete = Athlete(**athlete.dict())
    db.add(db_athlete)
    db.commit()
    db.refresh(db_athlete)
    return db_athlete


@app.get("/athletes", response_model=List[AthleteOut])
def list_athletes(db: Session = Depends(get_db)):
    return db.query(Athlete).all()


@app.get("/athletes/{athlete_id}", response_model=AthleteOut)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Sportoló nem található")
    return athlete


# --- EDZÉS (TERHELÉS) NAPLÓZÁS ---

@app.post("/training-sessions", response_model=TrainingSessionOut)
def create_training_session(session_in: TrainingSessionCreate, db: Session = Depends(get_db)):
    load_au = session_in.duration_min * session_in.rpe
    db_session = TrainingSession(**session_in.dict(), load_au=load_au)
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    # terhelés rögzítése után automatikusan frissítjük az ACWR-t és kockázatot
    update_load_metrics(db_session.athlete_id, db)

    return db_session


@app.get("/athletes/{athlete_id}/training-sessions", response_model=List[TrainingSessionOut])
def list_training_sessions(athlete_id: int, db: Session = Depends(get_db)):
    return db.query(TrainingSession).filter(TrainingSession.athlete_id == athlete_id).all()


# --- WELLNESS NAPLÓ ---

@app.post("/wellness-logs", response_model=WellnessLogOut)
def create_wellness_log(log_in: WellnessLogCreate, db: Session = Depends(get_db)):
    db_log = WellnessLog(**log_in.dict())
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


@app.get("/athletes/{athlete_id}/wellness-logs", response_model=List[WellnessLogOut])
def list_wellness_logs(athlete_id: int, db: Session = Depends(get_db)):
    return db.query(WellnessLog).filter(WellnessLog.athlete_id == athlete_id).all()


# ---------------------------------------------------------
# 5. TERHELÉS → KOCKÁZATBECSLÉS LOGIKA (AMS-réteg)
# ---------------------------------------------------------

def update_load_metrics(athlete_id: int, db: Session):
    """
    Kiszámolja az akut (7 napos) és krónikus (28 napos) terhelést,
    az ACWR-t, és ha szükséges, kockázati jelzést (risk_flag) hoz létre.
    """
    sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.athlete_id == athlete_id)
        .order_by(TrainingSession.session_date.desc())
        .all()
    )

    if not sessions:
        return

    latest_date = sessions[0].session_date

    acute_loads = [
        s.load_au for s in sessions
        if (latest_date - s.session_date).days <= 7
    ]
    chronic_loads = [
        s.load_au for s in sessions
        if (latest_date - s.session_date).days <= 28
    ]

    