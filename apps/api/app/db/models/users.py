import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at, uuid_pk


class UserRole(str, enum.Enum):
    citizen = "citizen"
    osi_chair = "osi_chair"
    management_co = "management_co"
    developer = "developer"
    lawyer = "lawyer"
    admin = "admin"


class Lang(str, enum.Enum):
    kk = "kk"
    ru = "ru"


user_role_enum = Enum(UserRole, name="user_role")
lang_enum = Enum(Lang, name="ui_lang")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(user_role_enum, default=UserRole.citizen, server_default="citizen")
    preferred_lang: Mapped[Lang] = mapped_column(lang_enum, default=Lang.ru, server_default="ru")
    city: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Building(Base):
    """Объект кондоминиума (многоквартирный дом)."""

    __tablename__ = "buildings"
    __table_args__ = (
        CheckConstraint("management_form IN ('OSI','PT','direct','KSK_legacy')", name="management_form"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    management_form: Mapped[str | None] = mapped_column(Text)
    osi_bin: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class Premise(Base):
    """Квартира, нежилое помещение, парковочное место или кладовка (каждое = один голос, ст. 42 п. 7 ЗЖО)."""

    __tablename__ = "premises"
    __table_args__ = (
        UniqueConstraint("building_id", "number", "kind"),
        CheckConstraint("kind IN ('apartment','non_residential','parking','storage')", name="kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    building_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE")
    )
    number: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    owner_name: Mapped[str | None] = mapped_column(Text)
