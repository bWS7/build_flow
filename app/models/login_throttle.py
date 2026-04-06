from datetime import datetime

from app import db


class LoginThrottle(db.Model):
    __tablename__ = 'login_throttles'

    id = db.Column(db.Integer, primary_key=True)
    throttle_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    ip_address = db.Column(db.String(64), nullable=False, index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    window_started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_attempt_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<LoginThrottle {self.throttle_key}>'
