from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select

from customer_service.bootstrap.config import Settings
from customer_service.infrastructure.database import Database, TenantRecord, UserRecord


@dataclass(frozen=True)
class Identity:
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: str


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings
        self._passwords = PasswordHash.recommended()
        self._dummy_hash = self._passwords.hash("invalid-password")

    def validate_configuration(self) -> None:
        if not self._settings.auth_enabled:
            return
        if len(self._settings.auth_jwt_secret) < 32:
            raise ValueError("AUTH_JWT_SECRET must contain at least 32 characters")
        if not self._settings.auth_bootstrap_admin_email:
            raise ValueError("AUTH_BOOTSTRAP_ADMIN_EMAIL is required")
        if len(self._settings.auth_bootstrap_admin_password) < 8:
            raise ValueError("AUTH_BOOTSTRAP_ADMIN_PASSWORD must contain at least 8 characters")

    def ensure_bootstrap_admin(self) -> None:
        if not self._settings.auth_enabled:
            return
        self.validate_configuration()
        email = self._settings.auth_bootstrap_admin_email.lower().strip()
        with self._database.session_factory.begin() as session:
            if session.scalar(select(UserRecord.id).where(UserRecord.email == email)):
                return
            if session.get(TenantRecord, "demo-company") is None:
                session.add(TenantRecord(
                    id="demo-company", name=self._settings.auth_bootstrap_tenant_name,
                    status="active", created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                ))
            session.add(UserRecord(
                id=str(uuid4()), tenant_id="demo-company", email=email,
                password_hash=self._passwords.hash(self._settings.auth_bootstrap_admin_password),
                display_name=self._settings.auth_bootstrap_admin_name, role="owner",
                status="active", created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            ))

    def authenticate(self, email: str, password: str) -> Identity | None:
        with self._database.session_factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.email == email.lower().strip()))
            if user is None:
                self._passwords.verify(password, self._dummy_hash)
                return None
            if user.status != "active" or not self._passwords.verify(password, user.password_hash):
                return None
            return Identity(user.id, user.tenant_id, user.email, user.display_name, user.role)

    def create_token(self, identity: Identity) -> str:
        expires = datetime.now(UTC) + timedelta(minutes=self._settings.auth_access_token_minutes)
        return jwt.encode({
            "sub": identity.user_id, "tenant_id": identity.tenant_id,
            "email": identity.email, "name": identity.display_name,
            "role": identity.role, "exp": expires,
        }, self._settings.auth_jwt_secret, algorithm="HS256")

    def decode_token(self, token: str | None) -> Identity | None:
        if not token:
            return None
        try:
            data = jwt.decode(token, self._settings.auth_jwt_secret, algorithms=["HS256"])
            return Identity(data["sub"], data["tenant_id"], data["email"], data["name"], data["role"])
        except (InvalidTokenError, KeyError):
            return None

    def list_users(self, tenant_id: str) -> list[UserRecord]:
        with self._database.session_factory() as session:
            return list(session.scalars(
                select(UserRecord).where(UserRecord.tenant_id == tenant_id)
                .order_by(UserRecord.created_at)
            ).all())

    def create_user(
        self, tenant_id: str, email: str, password: str,
        display_name: str, role: str,
    ) -> UserRecord:
        normalized = email.lower().strip()
        with self._database.session_factory.begin() as session:
            if session.scalar(select(UserRecord.id).where(UserRecord.email == normalized)):
                raise ValueError("该邮箱已存在")
            record = UserRecord(
                id=str(uuid4()), tenant_id=tenant_id, email=normalized,
                password_hash=self._passwords.hash(password), display_name=display_name,
                role=role, status="active",
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            session.add(record)
        return record

    def update_user(
        self, tenant_id: str, user_id: str, role: str | None, status: str | None
    ) -> UserRecord | None:
        with self._database.session_factory.begin() as session:
            record = session.scalar(select(UserRecord).where(
                UserRecord.id == user_id, UserRecord.tenant_id == tenant_id
            ))
            if record is None:
                return None
            if role is not None:
                record.role = role
            if status is not None:
                record.status = status
            session.flush()
            return record
