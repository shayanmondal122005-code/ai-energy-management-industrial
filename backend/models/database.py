"""SQLAlchemy ORM models — mirror the Supabase schema exactly."""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Double, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.core.database import Base


def _uuid():
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(Text, nullable=False)
    plan       = Column(String(20), nullable=False, default="starter")
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    facilities = relationship("Facility", back_populates="tenant", lazy="selectin")
    users      = relationship("User", back_populates="tenant", lazy="selectin")


class Facility(Base):
    __tablename__ = "facilities"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name         = Column(Text, nullable=False)
    city         = Column(Text, nullable=False, default="Kolkata")
    lat          = Column(Double, nullable=False, default=22.57)
    lon          = Column(Double, nullable=False, default=88.36)
    state_tariff = Column(Text, nullable=False, default="West Bengal - CESC")
    battery_kwh  = Column(Double, nullable=False, default=500)
    solar_kw     = Column(Double, nullable=False, default=200)
    avg_load_kw  = Column(Double, nullable=False, default=300)
    timezone     = Column(Text, nullable=False, default="Asia/Kolkata")
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant       = relationship("Tenant", back_populates="facilities")
    grid_state   = relationship("GridState", back_populates="facility", uselist=False)
    load_configs = relationship("LoadConfig", back_populates="facility", order_by="LoadConfig.priority")


class User(Base):
    __tablename__ = "users"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id     = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email         = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text)
    role          = Column(String(20), nullable=False, default="viewer")
    whatsapp      = Column(Text)
    full_name     = Column(Text)
    is_active     = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="users")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    key_hash    = Column(Text, nullable=False, unique=True)
    label       = Column(Text, nullable=False)
    is_active   = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True))
    created_by  = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Reading(Base):
    __tablename__ = "readings"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    timestamp   = Column(DateTime(timezone=True), nullable=False)
    load_kw     = Column(Double, nullable=False)
    solar_kw    = Column(Double, nullable=False, default=0)
    battery_soc = Column(Double, nullable=False, default=0)
    battery_temp = Column(Double)
    grid_kw     = Column(Double, default=0)
    net_kw      = Column(Double, default=0)
    source      = Column(String(20), nullable=False, default="unknown")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id      = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    tenant_id        = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    severity         = Column(String(20), nullable=False)
    type             = Column(Text, nullable=False)
    message          = Column(Text, nullable=False)
    value            = Column(Double)
    threshold        = Column(Double)
    whatsapp_sent    = Column(Boolean, nullable=False, default=False)
    whatsapp_sent_at = Column(DateTime(timezone=True))
    acknowledged_at  = Column(DateTime(timezone=True))
    acknowledged_by  = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class ControlCommand(Base):
    __tablename__ = "control_commands"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id  = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    type         = Column(String(30), nullable=False)
    target       = Column(Text)
    value        = Column(Double)
    reason       = Column(Text, nullable=False)
    priority     = Column(String(20), nullable=False, default="normal")
    confirmed    = Column(Boolean, nullable=False, default=False)
    confirmed_at = Column(DateTime(timezone=True))
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    executed     = Column(Boolean, nullable=False, default=False)
    executed_at  = Column(DateTime(timezone=True))
    result       = Column(String(20))
    error_message = Column(Text)
    issued_by    = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    issued_by_ip = Column(INET)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    expires_at   = Column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"))
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"))
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    event       = Column(Text, nullable=False)
    data        = Column(JSONB)
    ip_address  = Column(INET)
    user_agent  = Column(Text)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class GridState(Base):
    __tablename__ = "grid_state"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id       = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, unique=True)
    mode              = Column(String(20), nullable=False, default="GRID_CONNECTED")
    main_breaker      = Column(Boolean, nullable=False, default=True)
    battery_command   = Column(String(20), nullable=False, default="HOLD")
    grid_voltage_v    = Column(Double)
    grid_frequency_hz = Column(Double)
    last_mode_change  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    facility = relationship("Facility", back_populates="grid_state")


class LoadConfig(Base):
    __tablename__ = "load_configs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id  = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    load_id      = Column(Text, nullable=False)
    name         = Column(Text, nullable=False)
    priority     = Column(Integer, nullable=False)
    rated_kw     = Column(Double, nullable=False)
    contactor_id = Column(Text)
    is_on        = Column(Boolean, nullable=False, default=True)
    shed_order   = Column(Integer)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    facility = relationship("Facility", back_populates="load_configs")
    __table_args__ = (UniqueConstraint("facility_id", "load_id"),)


class Report(Base):
    __tablename__ = "reports"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id  = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    type         = Column(String(20), nullable=False, default="weekly")
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end   = Column(DateTime(timezone=True), nullable=False)
    file_url     = Column(Text)
    status       = Column(String(20), nullable=False, default="pending")
    generated_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
