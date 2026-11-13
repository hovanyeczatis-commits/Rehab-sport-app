from datetime import datetime, timedelta
from typing import Optional, List
import json

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
import os

# --- Konfiguráció ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
SECRET_KEY = os.getenv("SECRET_KEY", "ideiglenes-fejlesztoi-kulcs-cseresd-le")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 nap

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

app = FastAPI(title="Rehab-Sport Protokoll API")


# --- Adatbázis modellek ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "coach" vagy "athlete"
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Athlete(Base):
    __tablename__ = "athletes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    coach_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sport = Column(String, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class InjuryEpisode(Base):
    __tablename__ = "injury_episodes"
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    diagnosis = Column(String, nullable=False)
    injury_date = Column(DateTime, nullable=False)
    status = Column(String, default="active")  # active / recovered
    created_at = Column(DateTime, default=datetime.utcnow)

class Assessment(Base):
    __tablename__ = "assessments"
    id = Column(Integer, primary_key=True, index=True)
    injury_episode_id = Column(Integer, ForeignKey("injury_episodes.id"), nullable=False)
    assessed_at = Column(DateTime, default=datetime.utcnow)
    metric_name = Column(String, nullable=False)
    metric_value = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

class ProtocolRule(Base):
    __tablename__ = "protocol_rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    diagnosis = Column(String, nullable=False)
    criteria_json = Column(Text, nullable=False)  # strukturált küszöbértékek, JSON string
    recommended_action = Column(Text, nullable=False)
    source_literature_id = Column(Integer, ForeignKey("literature_candidates.id"), nullable=True)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class LiteratureCandidate(Base):
    __tablename__ = "literature_candidates"
    id = Column(Integer, primary_key=True, index=True)
    pubmed_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    abstract = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    reviewed = Column(Boolean, default=False)

class ProtocolRecommendationLog(Base):
    __tablename__ = "protocol_recommendation_logs"
    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    protocol_rule_id = Column(Integer, ForeignKey("protocol_rules.id"), nullable=False)
    recommended_at = Column(DateTime, default=datetime.utcnow)
    decision = Column(String, default="pending")  # pending / accepted / rejected
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)

Base.metadata.create_all(bind=engine)


# --- DB dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Auth segédfüggvények ---
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Érvénytelen hitelesítő adatok",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


# --- Pydantic sémák ---
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str  # "coach" vagy "athlete"

class Token(BaseModel):
    access_token: str
    token_type: str

class AthleteOut(BaseModel):
    id: int
    user_id: int
    sport: Optional[str]
    class Config:
        from_attributes = True

class AssessmentCreate(BaseModel):
    injury_episode_id: int
    metric_name: str
    metric_value: Optional[float] = None
    notes: Optional[str] = None

class AssessmentOut(BaseModel):
    id: int
    injury_episode_id: int
    metric_name: str
    metric_value: Optional[float]
    assessed_at: datetime
    class Config:
        from_attributes = True

class ProtocolRecommendationLogOut(BaseModel):
    id: int
    athlete_id: int
    assessment_id: int
    protocol_rule_id: int
    recommended_at: datetime
    decision: str
    decision_note: Optional[str] = None
    class Config:
        from_attributes = True

class RecommendationDecision(BaseModel):
    decision: str  # "accepted" vagy "rejected"
    decision_note: Optional[str] = None


# --- Kritérium-alapú protokoll-javaslat motor ---

def run_criteria_engine(assessment: Assessment, db: Session):
    """
    Az újonnan rögzített assessment alapján megnézi, van-e olyan
    jóváhagyott (approved=True) ProtocolRule, amelynek kritériumai
    teljesülnek. Ha igen, létrehoz egy ProtocolRecommendationLog
    bejegyzést "pending" státusszal, amit az edzőnek jóvá kell hagynia
    vagy el kell utasítania.
    """
    episode = db.query(InjuryEpisode).filter(
        InjuryEpisode.id == assessment.injury_episode_id
    ).first()
    if not episode:
        return

    rules = db.query(ProtocolRule).filter(
        ProtocolRule.diagnosis == episode.diagnosis,
        ProtocolRule.approved == True,
    ).all()

    for rule in rules:
        if _rule_criteria_met(rule, episode, db):
            existing = db.query(ProtocolRecommendationLog).filter(
                ProtocolRecommendationLog.athlete_id == episode.athlete_id,
                ProtocolRecommendationLog.protocol_rule_id == rule.id,
                ProtocolRecommendationLog.decision == "pending",
            ).first()
            if existing:
                continue

            log_entry = ProtocolRecommendationLog(
                athlete_id=episode.athlete_id,
                assessment_id=assessment.id,
                protocol
