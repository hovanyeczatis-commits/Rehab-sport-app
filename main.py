from datetime import datetime, timedelta
from typing import Optional, List

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
    criteria_json = Column(Text, nullable=False)  # strukturált küszöbértékek
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

class RecommendationDecision(BaseModel):
    decision: str  # "accepted" vagy "rejected"
    decision_note: Optional[str] = None

# --- Health check ---
@app.get("/health")
def health_check():
    return {"status": "ok", "time": datetime.utcnow()}

# --- Auth végpontok ---
@app.post("/auth/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ez az email cím már regisztrálva van")
    if user_in.role not in ("coach", "athlete"):
        raise HTTPException(status_code=400, detail="A szerepkör csak 'coach' vagy 'athlete' lehet")
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role=user_in.role,
        full_name=user_in.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if user.role == "athlete":
        athlete = Athlete(user_id=user.id)
        db.add(athlete)
        db.commit()

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Hibás email vagy jelszó")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/auth/me")
def read_current_user(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
           }
    # --- Athlete végpontok ---
@app.get("/athletes/me", response_model=AthleteOut)
def get_my_athlete_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "athlete":
        raise HTTPException(status_code=403, detail="Csak sportoló szerepkörnek elérhető")
    athlete = db.query(Athlete).filter(Athlete.user_id == current_user.id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Sportoló profil nem található")
    return athlete

@app.get("/athletes", response_model=List[AthleteOut])
def list_athletes(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "coach":
        raise HTTPException(status_code=403, detail="Csak edző szerepkörnek elérhető")
    athletes = db.query(Athlete).filter(Athlete.coach_id == current_user.id).all()
    return athletes

@app.get("/athletes/{athlete_id}", response_model=AthleteOut)
def get_athlete(athlete_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Sportoló nem található")
    if current_user.role == "athlete" and athlete.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultság")
    if current_user.role == "coach" and athlete.coach_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultság")
    return athlete


# --- Injury episode végpontok ---
class InjuryEpisodeCreate(BaseModel):
    athlete_id: int
    diagnosis: str
    injury_date: datetime

class InjuryEpisodeOut(BaseModel):
    id: int
    athlete_id: int
    diagnosis: str
    injury_date: datetime
    status: str
    class Config:
        from_attributes = True

@app.post("/injury-episodes", response_model=InjuryEpisodeOut)
def create_injury_episode(data: InjuryEpisodeCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "coach":
        raise HTTPException(status_code=403, detail="Csak edző hozhat létre sérülési epizódot")
    episode = InjuryEpisode(
        athlete_id=data.athlete_id,
        diagnosis=data.diagnosis,
        injury_date=data.injury_date,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    return episode

@app.get("/injury-episodes/{athlete_id}", response_model=List[InjuryEpisodeOut])
def list_injury_episodes(athlete_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    episodes = db.query(InjuryEpisode).filter(InjuryEpisode.athlete_id == athlete_id).all()
    return episodes


# --- Assessment végpontok ---
@app.post("/assessments", response_model=AssessmentOut)
def create_assessment(data: AssessmentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assessment = Assessment(
        injury_episode_id=data.injury_episode_id,
        metric_name=data.metric_name,
        metric_value=data.metric_value,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    # Automatikus kritérium-kiértékelés futtatása az új assessment alapján
    run_criteria_engine(assessment, db)

    return assessment

@app.get("/assessments/{injury_episode_id}", response_model=List[AssessmentOut])
def list_assessments(injury_episode_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assessments = db.query(Assessment).filter(Assessment.injury_episode_id == injury_episode_id).all()
    return assessments
