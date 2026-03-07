import secrets
import string
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum, ForeignKey, Date, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base
import enum

class SpeedMode(enum.Enum):
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), onupdate=func.now())
    free_solves_today = Column(Integer, default=0)
    free_autos_today = Column(Integer, default=0)
    last_reset_date = Column(Date, nullable=True)
    default_max_attempts = Column(Integer, default=1)
    default_speed = Column(Enum(SpeedMode), default=SpeedMode.MEDIUM)
    referral_code = Column(String(20), unique=True, nullable=False)
    referred_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    referred_by = relationship("User", remote_side=[id], backref="referrals")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.referral_code:
            self.referral_code = ''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(8))
