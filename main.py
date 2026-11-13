Rehab Sport App - Backend API
FastAPI alkalmazás: auth, athletes, injury-episodes, assessments,
pain-points, protocol criteria engine és recommendation log kezelés.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

---------------------------------------------------------------------------
KONFIGURÁCIÓ
---------------------------------------------------------------------------

SECRET_KEY = "CHANGE_THIS_TO_A_REAL_SECRET_IN_PRODUCTION"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 nap

DATABASE_URL = "postgresql://user:password@localhost:5432/rehab_sport_app"
Railway / egyéb produkciós deploy esetén környezeti változóból érdemes olvasni:
import os
DATABASE_URL = os.environ.get("DATABASE_URL", DATABASE_URL)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

app = FastAPI(title="Rehab Sport App API", version="0.1.0")


---------------------------------------------------------------------------
DB MODELLEK
---------------------------------------------------------------------------

class User(Base):
tablename = "users"

id = Column(Integer, primary_key=True, index=True)
email = Column(String, unique=True, index=True, nullable=False)
hashed_password = Column(String, nullable=False)
full_name = Column(String, nullable=True)
role = Column(String, nullable=False, default="athlete") # "athlete" | "coach" | "admin"
is_active = Column(Boolean, default=True)
created_at = Column(DateTime, default=datetime.utcnow)

athlete_profile = relationship("Athlete", back_populates="user", uselist=False)
coached_athletes = relationship("Athlete", back_populates="coach", foreign_keys="Athlete.coach_id")


class Athlete(Base):
tablename = "athletes"

id = Column(Integer, primary_key=True, index=True)
user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
coach_id = Column(Integer, ForeignKey("users.id"), nullable=True)

sport = Column(String, nullable=True)
date_of_birth = Column(DateTime, nullable=True)
height_cm = Column(Float, nullable=True)
weight_kg = Column(Float, nullable=True)
dominant_side = Column(String, nullable=True) # "left" | "right"

created_at = Column(DateTime, default=datetime.utcnow)

user = relationship("User", back_populates="athlete_profile", foreign_keys=[user_id])
coach = relationship("User", back_populates="coached_athletes", foreign_keys=[coach_id])
injury_episodes = relationship("InjuryEpisode", back_populates="athlete", cascade="all, delete-orphan")


class InjuryEpisode(Base):
tablename = "injury_episodes"

id = Column(Integer, primary_key=True, index=True)
athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)

injury_type = Column(String, nullable=False) # pl. "ACL_rupture", "hamstring_strain"
body_region = Column(String, nullable=True)
side = Column(String, nullable=True) # "left" | "right" | "bilateral"
date_of_injury = Column(DateTime, nullable=True)
mechanism = Column(Text, nullable=True)
status = Column(String, nullable=False, default="active") # "active" | "resolved"

created_at = Column(DateTime, default=datetime.utcnow)

athlete = relationship("Athlete", back_populates="injury_episodes")
assessments = relationship("Assessment", back_populates="injury_episode", cascade="all, delete-orphan")
pain_points = relationship("PainPoint", back_populates="injury_episode", cascade="all, delete-orphan")
recommendation_logs = relationship("RecommendationLog", back_populates="injury_episode", cascade="all, delete-orphan")


class Assessment(Base):
tablename = "assessments"

id = Column(Integer, primary_key=True, index=True)
injury_episode_id = Column(Integer, ForeignKey("injury_episodes.id"), nullable=False)
created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

assessment_date = Column(DateTime, default=datetime.utcnow)
pain_score = Column(Float, nullable=True) # 0-10 VAS
strength_symmetry_pct = Column(Float, nullable=True) # pl. 0-100%
rom_degrees = Column(Float, nullable=True)
functional_test_result = Column(String, nullable=True)
notes = Column(Text, nullable=True)

injury_episode = relationship("InjuryEpisode", back_populates="assessments")
pain_points = relationship("PainPoint", back_populates="assessment", cascade="all, delete-orphan")


class PainPoint(Base):
tablename = "pain_points"

id = Column(Integer, primary_key=True, index=True)
assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True)
injury_episode_id = Column(Integer, ForeignKey("injury_episodes.id"), nullable=True)

x_coord = Column(Float, nullable=False) # relatív koordináta a test-sziluetten (0-1)
y_coord = Column(Float, nullable=False)
view = Column(String, nullable=False, default="front") # "front" | "back"
pain_intensity = Column(Float, nullable=True) # 0-10
note = Column(Text, nullable=True)

created_at = Column(DateTime, default=datetime.utcnow)

assessment = relationship("Assessment", back_populates="pain_points")
injury_episode = relationship("InjuryEpisode", back_populates="pain_points")


class ProtocolRule(Base):
tablename = "protocol_rules"

id = Column(Integer, primary_key=True, index=True)
injury_type = Column(String, nullable=False, index=True)
rule_name = Column(String, nullable=False)
description = Column(Text, nullable=True)

# Egyszerűsített, egyelőre szabadszöveges/JSON-szerű kritérium tárolás.
# Később ezt konkrét mezőkre bontjuk (pl. metric_name, operator, threshold_value).
criteria_definition = Column(Text, nullable=True)

recommended_action = Column(Text, nullable=False)
is_active = Column(Boolean, default=True)
created_at = Column(DateTime, default=datetime.utcnow)


class RecommendationLog(Base):
tablename = "recommendation_logs"

id = Column(Integer, primary_key=True, index=True)
injury_episode_id = Column(Integer, ForeignKey("injury_episodes.id"), nullable=False)
protocol_rule_id = Column(Integer, ForeignKey("protocol_rules.id"), nullable=True)
assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True)

generated_at = Column(DateTime, default=datetime.utcnow)
recommendation_text = Column(Text, nullable=False)
status = Column(String, nullable=False, default="pending") # "pending" | "accepted" | "rejected"

decided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
decided_at = Column(DateTime, nullable=True)
decision_note = Column(Text, nullable=True)

injury_episode = relationship("InjuryEpisode", back_populates="recommendation_logs")


---------------------------------------------------------------------------
PYDANTIC SÉMÁK
---------------------------------------------------------------------------

class Token(BaseModel):
access_token: str
token_type: str


class TokenData(BaseModel):
user_id: Optional[int] = None


class UserCreate(BaseModel):
email: str
password: str
full_name: Optional[str] = None
role: str = "athlete"


class UserOut(BaseModel):
id: int
email: str
full_name: Optional[str]
role: str
is_active: bool

class Config:
orm_mode = True


class AthleteCreate(BaseModel):
sport: Optional[str] = None
date_of_birth: Optional[datetime] = None
height_cm: Optional[float] = None
weight_kg: Optional[float] = None
dominant_side: Optional[str] = None
coach_id: Optional[int] = None


class AthleteUpdate(BaseModel):
sport: Optional[str] = None
date_of_birth: Optional[datetime] = None
height_cm: Optional[float] = None
weight_kg: Optional[float] = None
dominant_side: Optional[str] = None
coach_id: Optional[int] = None


class AthleteOut(BaseModel):
id: int
user_id: int
coach_id: Optional[int]
sport: Optional[str]
date_of_birth: Optional[datetime]
height_cm: Optional[float]
weight_kg: Optional[float]
dominant_side: Optional[str]
created_at: datetime

class Config:
orm_mode = True


class InjuryEpisodeCreate(BaseModel):
injury_type: str
body_region: Optional[str] = None
side: Optional[str] = None
date_of_injury: Optional[datetime] = None
mechanism: Optional[str] = None


class InjuryEpisodeUpdate(BaseModel):
injury_type: Optional[str] = None
body_region: Optional[str] = None
side: Optional[str] = None
date_of_injury: Optional[datetime] = None
mechanism: Optional[str] = None
status: Optional[str] = None


class InjuryEpisodeOut(BaseModel):
id: int
athlete_id: int
injury_type: str
body_region: Optional[str]
side: Optional[str]
date_of_injury: Optional[datetime]
mechanism: Optional[str]
status: str
created_at: datetime

class Config:
orm_mode = True


class PainPointCreate(BaseModel):
x_coord: float
y_coord: float
view: str = "front"
pain_intensity: Optional[float] = None
note: Optional[str] = None
assessment_id: Optional[int] = None


class PainPointOut(BaseModel):
id: int
assessment_id: Optional[int]
injury_episode_id: Optional[int]
x_coord: float
y_coord: float
view: str
pain_intensity: Optional[float]
note: Optional[str]
created_at: datetime

class Config:
orm_mode = True


class AssessmentCreate(BaseModel):
assessment_date: Optional[datetime] = None
pain_score: Optional[float] = None
strength_symmetry_pct: Optional[float] = None
rom_degrees: Optional[float] = None
functional_test_result: Optional[str] = None
notes: Optional[str] = None
pain_points: Optional[List[PainPointCreate]] = None


class AssessmentUpdate(BaseModel):
assessment_date: Optional[datetime] = None
pain_score: Optional[float] = None
strength_symmetry_pct: Optional[float] = None
rom_degrees: Optional[float] = None
functional_test_result: Optional[str] = None
notes: Optional[str] = None


class AssessmentOut(BaseModel):
id: int
injury_episode_id: int
created_by_id: int
assessment_date: datetime
pain_score: Optional[float]
strength_symmetry_pct: Optional[float]
rom_degrees: Optional[float]
functional_test_result: Optional[str]
notes: Optional[str]
pain_points: List[PainPointOut] = []

class Config:
orm_mode = True


class RecommendationLogOut(BaseModel):
id: int
injury_episode_id: int
protocol_rule_id: Optional[int]
assessment_id: Optional[int]
generated_at: datetime
recommendation_text: str
status: str
decided_by_id: Optional[int]
decided_at: Optional[datetime]
decision_note: Optional[str]

class Config:
orm_mode = True


class RecommendationDecision(BaseModel):
status: str # "accepted" | "rejected"
decision_note: Optional[str] = None


---------------------------------------------------------------------------
DB DEPENDENCY
---------------------------------------------------------------------------

def get_db():
db = SessionLocal()
try:
yield db
finally:
db.close()


---------------------------------------------------------------------------
AUTH SEGÉDFÜGGVÉNYEK
---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
to_encode = data.copy()
expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
to_encode.update({"exp": expire})
return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
user = db.query(User).filter(User.email == email).first()
if not user or not verify_password(password, user.hashed_password):
return None
return user


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
credentials_exception = HTTPException(
status_code=status.HTTP_401_UNAUTHORIZED,
detail="Érvénytelen hitelesítő adatok",
headers={"WWW-Authenticate": "Bearer"},
)
try:
payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
user_id: int = payload.get("sub")
if user_id is None:
raise credentials_exception
except JWTError:
raise credentials_exception

user = db.query(User).filter(User.id == int(user_id)).first()
if user is None:
raise credentials_exception
return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
if not current_user.is_active:
raise HTTPException(status_code=400, detail="Inaktív felhasználó")
return current_user


def require_coach_or_admin(current_user: User = Depends(get_current_active_user)) -> User:
if current_user.role not in ("coach", "admin"):
raise HTTPException(status_code=403, detail="Nincs jogosultság ehhez a művelethez")
return current_user


---------------------------------------------------------------------------
AUTH VÉGPONTOK
---------------------------------------------------------------------------

@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
existing = db.query(User).filter(User.email == user_in.email).first()
if existing:
raise HTTPException(status_code=400, detail="Ez az email cím már regisztrálva van")

user = User(
email=user_in.email,
hashed_password=get_password_hash(user_in.password),
full_name=user_in.full_name,
role=user_in.role,
)
db.add(user)
db.commit()
db.refresh(user)

if user.role == "athlete":
athlete = Athlete(user_id=user.id)
db.add(athlete)
db.commit()

return user


@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
user = authenticate_user(db, form_data.username, form_data.password)
if not user:
raise HTTPException(
status_code=status.HTTP_401_UNAUTHORIZED,
detail="Hibás email vagy jelszó",
headers={"WWW-Authenticate": "Bearer"},
)
access_token = create_access_token(data={"sub": str(user.id)})
return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_active_user)):
return current_user


---------------------------------------------------------------------------
ATHLETES VÉGPONTOK
---------------------------------------------------------------------------

def get_athlete_or_404(athlete_id: int, db: Session) -> Athlete:
athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
if not athlete:
raise HTTPException(status_code=404, detail="Sportoló nem található")
return athlete


def check_athlete_access(athlete: Athlete, current_user: User):
"""Csak maga a sportoló, a hozzárendelt coach, vagy admin férhet hozzá."""
if current_user.role == "admin":
return
if athlete.user_id == current_user.id:
return
if athlete.coach_id == current_user.id:
return
raise HTTPException(status_code=403, detail="Nincs jogosultság ehhez a sportolóhoz")


@app.get("/athletes/me", response_model=AthleteOut)
def read_my_athlete_profile(
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
athlete = db.query(Athlete).filter(Athlete.user_id == current_user.id).first()
if not athlete:
raise HTTPException(status_code=404, detail="Nincs sportolói profil ehhez a felhasználóhoz")
return athlete


@app.get("/athletes", response_model=List[AthleteOut])
def list_athletes(
current_user: User = Depends(require_coach_or_admin),
db: Session = Depends(get_db),
):
query = db.query(Athlete)
if current_user.role == "coach":
query = query.filter(Athlete.coach_id == current_user.id)
return query.all()


@app.get("/athletes/{athlete_id}", response_model=AthleteOut)
def read_athlete(
athlete_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
athlete = get_athlete_or_404(athlete_id, db)
check_athlete_access(athlete, current_user)
return athlete


@app.put("/athletes/{athlete_id}", response_model=AthleteOut)
def update_athlete(
athlete_id: int,
athlete_in: AthleteUpdate,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
athlete = get_athlete_or_404(athlete_id, db)
check_athlete_access(athlete, current_user)

update_data = athlete_in.dict(exclude_unset=True)
for field, value in update_data.items():
setattr(athlete, field, value)

db.commit()
db.refresh(athlete)
return athlete


@app.delete("/athletes/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_athlete(
athlete_id: int,
current_user: User = Depends(require_coach_or_admin),
db: Session = Depends(get_db),
):
athlete = get_athlete_or_404(athlete_id, db)
if current_user.role == "coach" and athlete.coach_id != current_user.id:
raise HTTPException(status_code=403, detail="Nincs jogosultság")
db.delete(athlete)
db.commit()
return None


---------------------------------------------------------------------------
INJURY EPISODES VÉGPONTOK
---------------------------------------------------------------------------

def get_injury_episode_or_404(episode_id: int, db: Session) -> InjuryEpisode:
episode = db.query(InjuryEpisode).filter(InjuryEpisode.id == episode_id).first()
if not episode:
raise HTTPException(status_code=404, detail="Sérülés epizód nem található")
return episode


@app.post("/athletes/{athlete_id}/injury-episodes", response_model=InjuryEpisodeOut, status_code=status.HTTP_201_CREATED)
def create_injury_episode(
athlete_id: int,
episode_in: InjuryEpisodeCreate,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
athlete = get_athlete_or_404(athlete_id, db)
check_athlete_access(athlete, current_user)

episode = InjuryEpisode(
athlete_id=athlete_id,
injury_type=episode_in.injury_type,
body_region=episode_in.body_region,
side=episode_in.side,
date_of_injury=episode_in.date_of_injury,
mechanism=episode_in.mechanism,
status="active",
)
db.add(episode)
db.commit()
db.refresh(episode)
return episode


@app.get("/athletes/{athlete_id}/injury-episodes", response_model=List[InjuryEpisodeOut])
def list_injury_episodes(
athlete_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
athlete = get_athlete_or_404(athlete_id, db)
check_athlete_access(athlete, current_user)
return db.query(InjuryEpisode).filter(InjuryEpisode.athlete_id == athlete_id).all()


@app.get("/injury-episodes/{episode_id}", response_model=InjuryEpisodeOut)
def read_injury_episode(
episode_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
episode = get_injury_episode_or_404(episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)
return episode


@app.put("/injury-episodes/{episode_id}", response_model=InjuryEpisodeOut)
def update_injury_episode(
episode_id: int,
episode_in: InjuryEpisodeUpdate,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
episode = get_injury_episode_or_404(episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)

update_data = episode_in.dict(exclude_unset=True)
for field, value in update_data.items():
setattr(episode, field, value)

db.commit()
db.refresh(episode)
return episode


@app.delete("/injury-episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_injury_episode(
episode_id: int,
current_user: User = Depends(require_coach_or_admin),
db: Session = Depends(get_db),
):
episode = get_injury_episode_or_404(episode_id, db)
db.delete(episode)
db.commit()
return None


---------------------------------------------------------------------------
ASSESSMENTS VÉGPONTOK
---------------------------------------------------------------------------

def get_assessment_or_404(assessment_id: int, db: Session) -> Assessment:
assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
if not assessment:
raise HTTPException(status_code=404, detail="Felmérés nem található")
return assessment


@app.post(
"/injury-episodes/{episode_id}/assessments",
response_model=AssessmentOut,
status_code=status.HTTP_201_CREATED,
)
def create_assessment(
episode_id: int,
assessment_in: AssessmentCreate,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
episode = get_injury_episode_or_404(episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)

assessment = Assessment(
injury_episode_id=episode_id,
created_by_id=current_user.id,
assessment_date=assessment_in.assessment_date or datetime.utcnow(),
pain_score=assessment_in.pain_score,
strength_symmetry_pct=assessment_in.strength_symmetry_pct,
rom_degrees=assessment_in.rom_degrees,
functional_test_result=assessment_in.functional_test_result,
notes=assessment_in.notes,
)
db.add(assessment)
db.commit()
db.refresh(assessment)

# Fájdalompontok mentése, ha vannak
if assessment_in.pain_points:
for pp in assessment_in.pain_points:
pain_point = PainPoint(
assessment_id=assessment.id,
injury_episode_id=episode_id,
x_coord=pp.x_coord,
y_coord=pp.y_coord,
view=pp.view,
pain_intensity=pp.pain_intensity,
note=pp.note,
)
db.add(pain_point)
db.commit()
db.refresh(assessment)

# Kritérium-motor automatikus lefuttatása az új felmérés után
run_criteria_engine(episode_id=episode_id, assessment=assessment, db=db)

return assessment


@app.get("/injury-episodes/{episode_id}/assessments", response_model=List[AssessmentOut])
def list_assessments(
episode_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
episode = get_injury_episode_or_404(episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)
return (
db.query(Assessment)
.filter(Assessment.injury_episode_id == episode_id)
.order_by(Assessment.assessment_date.desc())
.all()
)


@app.get("/assessments/{assessment_id}", response_model=AssessmentOut)
def read_assessment(
assessment_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
assessment = get_assessment_or_404(assessment_id, db)
episode = get_injury_episode_or_404(assessment.injury_episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)
return assessment


@app.put("/assessments/{assessment_id}", response_model=AssessmentOut)
def update_assessment(
assessment_id: int,
assessment_in: AssessmentUpdate,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
assessment = get_assessment_or_404(assessment_id, db)
episode = get_injury_episode_or_404(assessment.injury_episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)

update_data = assessment_in.dict(exclude_unset=True)
for field, value in update_data.items():
setattr(assessment, field, value)

db.commit()
db.refresh(assessment)
return assessment


@app.delete("/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(
assessment_id: int,
current_user: User = Depends(require_coach_or_admin),
db: Session = Depends(get_db),
):
assessment = get_assessment_or_404(assessment_id, db)
db.delete(assessment)
db.commit()
return None


@app.post(
"/assessments/{assessment_id}/pain-points",
response_model=PainPointOut,
status_code=status.HTTP_201_CREATED,
)
def add_pain_point(
assessment_id: int,
pain_point_in: PainPointCreate,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
assessment = get_assessment_or_404(assessment_id, db)
episode = get_injury_episode_or_404(assessment.injury_episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)

pain_point = PainPoint(
assessment_id=assessment_id,
injury_episode_id=episode.id,
x_coord=pain_point_in.x_coord,
y_coord=pain_point_in.y_coord,
view=pain_point_in.view,
pain_intensity=pain_point_in.pain_intensity,
note=pain_point_in.note,
)
db.add(pain_point)
db.commit()
db.refresh(pain_point)
return pain_point


---------------------------------------------------------------------------
KRITÉRIUM-MOTOR (PLACEHOLDER LOGIKA)
---------------------------------------------------------------------------
FONTOS: Ez a rész jelenleg VÁZ / PLACEHOLDER.
A ProtocolRule konkrét mezőstruktúrája (pl. min_strength_symmetry,
max_pain_score, min_rom_degrees stb.) és a valódi RTS-küszöbértékek
még nincsenek véglegesítve. A lenti logika csak bemutatja, hogyan
kapcsolódik össze a rendszer, de a tényleges kritérium-kiértékelést
később kell pontosítani orvosi/szakmai inputok alapján.


def _rule_criteria_met(rule: "ProtocolRule", assessment: Assessment) -> bool:
"""
PLACEHOLDER: itt kellene a valódi kritérium-kiértékelésnek történnie,
pl.:
if rule.max_pain_score is not None and assessment.pain_score is not None:
if assessment.pain_score > rule.max_pain_score:
return False
if rule.min_strength_symmetry_pct is not None and assessment.strength_symmetry_pct is not None:
if assessment.strength_symmetry_pct < rule.min_strength_symmetry_pct:
return False
...
Egyelőre mindig True-t ad vissza, hogy a váz futtatható legyen.
"""
return True


def run_criteria_engine(episode_id: int, assessment: Assessment, db: Session) -> Optional[RecommendationLog]:
"""
Lefuttatja a sérüléshez tartozó aktív ProtocolRule-okat az aktuális
assessment adatain, és ha egy szabály kritériumai teljesülnek,
létrehoz egy RecommendationLog bejegyzést 'pending' státusszal.

PLACEHOLDER: a szabályok kiválasztási logikája (pl. injury_type vagy
body_region alapján szűrés) és a _rule_criteria_met tényleges tartalma
még finomítandó.
"""
episode = db.query(InjuryEpisode).filter(InjuryEpisode.id == episode_id).first()
if not episode:
return None

rules = (
db.query(ProtocolRule)
.filter(ProtocolRule.injury_type == episode.injury_type)
.filter(ProtocolRule.is_active == True)
.all()
)

created_log: Optional[RecommendationLog] = None

for rule in rules:
if _rule_criteria_met(rule, assessment):
log = RecommendationLog(
injury_episode_id=episode.id,
assessment_id=assessment.id,
protocol_rule_id=rule.id,
recommended_action=rule.recommended_action,
status="pending",
created_at=datetime.utcnow(),
)
db.add(log)
db.commit()
db.refresh(log)
created_log = log

return created_log


---------------------------------------------------------------------------
RECOMMENDATION LOG VÉGPONTOK
---------------------------------------------------------------------------

def get_recommendation_log_or_404(log_id: int, db: Session) -> RecommendationLog:
log = db.query(RecommendationLog).filter(RecommendationLog.id == log_id).first()
if not log:
raise HTTPException(status_code=404, detail="Javaslat-bejegyzés nem található")
return log


@app.get(
"/athletes/{athlete_id}/recommendations",
response_model=List[RecommendationLogOut],
)
def list_recommendations(
athlete_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
athlete = get_athlete_or_404(athlete_id, db)
check_athlete_access(athlete, current_user)

episode_ids = [
e.id
for e in db.query(InjuryEpisode.id)
.filter(InjuryEpisode.athlete_id == athlete_id)
.all()
 ]

return (
db.query(RecommendationLog)
.filter(RecommendationLog.injury_episode_id.in_(episode_ids))
.order_by(RecommendationLog.created_at.desc())
.all()
)


@app.get("/recommendations/{log_id}", response_model=RecommendationLogOut)
def read_recommendation(
log_id: int,
current_user: User = Depends(get_current_active_user),
db: Session = Depends(get_db),
):
log = get_recommendation_log_or_404(log_id, db)
episode = get_injury_episode_or_404(log.injury_episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)
return log


@app.put(
"/recommendations/{log_id}/decision",
response_model=RecommendationLogOut,
)
def decide_recommendation(
log_id: int,
decision_in: RecommendationDecisionIn,
current_user: User = Depends(require_coach_or_admin),
db: Session = Depends(get_db),
):
"""
Humán-in-the-loop döntés egy javaslatról: elfogadás / elutasítás / módosítás.
decision_in.decision értéke pl. "accepted", "rejected", "modified"
decision_in.decision_note opcionális megjegyzés.
"""
log = get_recommendation_log_or_404(log_id, db)
episode = get_injury_episode_or_404(log.injury_episode_id, db)
athlete = get_athlete_or_404(episode.athlete_id, db)
check_athlete_access(athlete, current_user)

if decision_in.decision not in ("accepted", "rejected", "modified"):
raise HTTPException(status_code=400, detail="Érvénytelen döntés érték")

log.status = decision_in.decision
log.decision_note = decision_in.decision_note
log.decided_by_id = current_user.id
log.decided_at = datetime.utcnow()

db.commit()
db.refresh(log)
return log


---------------------------------------------------------------------------
HEALTH ENDPOINT
---------------------------------------------------------------------------

@app.get("/health")
def health_check():
return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


---------------------------------------------------------------------------
APP INDÍTÁSA (lokális futtatáshoz)
---------------------------------------------------------------------------

if name == "main":
import uvicorn

uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
