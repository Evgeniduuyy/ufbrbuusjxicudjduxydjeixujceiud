from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.sql import func
import enum
from .base import Base

class AnswerSource(enum.Enum):
    DATABASE = "db"
    AI = "ai"
    USER = "user"

class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True)
    task_url_hash = Column(String(64), index=True, nullable=False)
    question_hash = Column(String(64), index=True, nullable=False)
    question_text = Column(Text, nullable=True)
    answer_json = Column(Text, nullable=False)
    source = Column(Enum(AnswerSource), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
