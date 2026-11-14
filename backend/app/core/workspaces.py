"""Provision the separate India workspace account without changing existing users."""
from sqlalchemy.orm import Session
from ..db.models import User
from .security import hash_password


def ensure_india_account(db: Session):
    account = db.query(User).filter(User.username == 'admin_1').first()
    if account is None:
        account = User(
            username='admin_1',
            email='admin_1@aqualens.ai',
            hashed_password=hash_password('India123'),
            role='viewer',
            is_active=True,
        )
        db.add(account)
        db.commit()
    return account
