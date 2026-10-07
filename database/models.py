"""
SQLite persistence for leads using SQLAlchemy.
"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, Boolean, Float
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.db"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(320), index=True)
    phone = Column(String(50), index=True)
    name = Column(String(200))
    title = Column(String(200))
    company = Column(String(300), index=True)
    website = Column(String(300))
    source_url = Column(String(500))
    source_type = Column(String(50), default="website")
    confidence = Column(String(20), default="medium")
    notes = Column(Text)
    status = Column(String(50), default="new")  # new, contacted, qualified, unsubscribed, invalid
    scraped_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_verified = Column(Boolean, default=False)
    score = Column(Float, default=0.0)  # simple lead score placeholder

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "phone": self.phone,
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "website": self.website,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "notes": self.notes,
            "status": self.status,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_verified": self.is_verified,
            "score": self.score,
        }


def get_engine(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(db_path: Path = DB_PATH) -> None:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)


def get_session(db_path: Path = DB_PATH) -> Session:
    engine = get_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _prepare_for_db(contact_dict: dict) -> dict:
    """Convert ISO strings back to datetime and drop unknown keys."""
    allowed = {c.name for c in Lead.__table__.columns}
    data = {k: v for k, v in contact_dict.items() if k in allowed and v is not None}
    for dt_field in ("scraped_at", "updated_at"):
        if dt_field in data and isinstance(data[dt_field], str):
            try:
                data[dt_field] = datetime.fromisoformat(data[dt_field].replace("Z", "+00:00"))
            except ValueError:
                data.pop(dt_field, None)
    return data


def upsert_lead(session: Session, contact_dict: dict) -> Lead:
    """Insert or update by email (preferred) or phone."""
    data = _prepare_for_db(contact_dict)
    email = data.get("email")
    phone = data.get("phone")

    existing = None
    if email:
        existing = session.query(Lead).filter(Lead.email == email).first()
    if not existing and phone:
        existing = session.query(Lead).filter(Lead.phone == phone).first()

    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
        session.commit()
        return existing

    lead = Lead(**data)
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def bulk_upsert(session: Session, contacts: List[dict]) -> int:
    count = 0
    for c in contacts:
        upsert_lead(session, c)
        count += 1
    return count


def get_all_leads(session: Session, status: Optional[str] = None) -> List[Lead]:
    q = session.query(Lead)
    if status:
        q = q.filter(Lead.status == status)
    return q.order_by(Lead.scraped_at.desc()).all()


def delete_lead(session: Session, lead_id: int) -> bool:
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        session.delete(lead)
        session.commit()
        return True
    return False
