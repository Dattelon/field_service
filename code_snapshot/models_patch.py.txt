# Патч для field_service/db/models.py
# Применить изменения в указанных местах

# ============================================================================
# 1. ИСПРАВЛЕНИЕ: orders - добавить cancel_reason
# ============================================================================
# НАЙТИ в классе orders (примерно строка 550):
#     version: Mapped[int] = mapped_column(
#         Integer, nullable=False, default=1, server_default="1"
#     )  # optimistic lock
#
# ДОБАВИТЬ ПОСЛЕ:
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ============================================================================
# 2. ИСПРАВЛЕНИЕ: commissions - добавить paid_at и исправить order_id FK
# ============================================================================
# НАЙТИ в классе commissions (примерно строка 770):
#     order_id: Mapped[int] = mapped_column(
#         Integer,
#         nullable=False,
#         index=True,
#     )
#
# ЗАМЕНИТЬ НА:
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # соответствует uq_commissions__order_id в БД
        index=True,
    )

# НАЙТИ (примерно строка 775):
#     master_id: Mapped[int] = mapped_column(
#         ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True
#     )
#
# ДОБАВИТЬ ПОСЛЕ:
    
    # Legacy field, use paid_approved_at instead
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )

# НАЙТИ (примерно строка 805):
#     updated_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
#     )
#
# ДОБАВИТЬ relationship ПОСЛЕ:
    
    order: Mapped[Optional["orders"]] = relationship(
        "orders",
        foreign_keys=[order_id],
        lazy="raise_on_sql"
    )


# ============================================================================
# 3. ИСПРАВЛЕНИЕ: offers - добавить FK на master_id
# ============================================================================
# НАЙТИ в классе offers (примерно строка 740):
#     master_id: Mapped[int] = mapped_column(
#         Integer,
#         nullable=False,
#         index=True,
#     )
#
# ЗАМЕНИТЬ НА:
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

# НАЙТИ (примерно строка 755):
#     master: Mapped["masters"] = relationship(
#         "masters",
#         primaryjoin="offers.master_id == masters.id",
#         foreign_keys="offers.master_id",
#         viewonly=True,
#         lazy="raise_on_sql",
#     )
#
# ЗАМЕНИТЬ НА (убрать viewonly и упростить):
    master: Mapped["masters"] = relationship(
        "masters",
        lazy="raise_on_sql",
    )


# ============================================================================
# 4. ИСПРАВЛЕНИЕ: staff_access_codes - переименовать issued_by → created_by
# ============================================================================
# НАЙТИ в классе staff_access_codes (примерно строка 480):
#     issued_by_staff_id: Mapped[Optional[int]] = mapped_column(
#         ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
#     )
#
# ЗАМЕНИТЬ НА:
    created_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    # Backward compatibility alias
    issued_by_staff_id = synonym("created_by_staff_id")

# НАЙТИ (примерно строка 488):
#     used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
#     comment: Mapped[Optional[str]] = mapped_column(Text)
#
# ДОБАВИТЬ ПОСЛЕ:
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

# НАЙТИ relationships (примерно строка 495):
#     issued_by_staff: Mapped[Optional["staff_users"]] = relationship(
#         foreign_keys=[issued_by_staff_id]
#     )
#
# ЗАМЕНИТЬ НА:
    created_by_staff: Mapped[Optional["staff_users"]] = relationship(
        foreign_keys=[created_by_staff_id]
    )
    # Backward compatibility alias
    issued_by_staff = synonym("created_by_staff")


# ============================================================================
# 5. ДОБАВЛЕНИЕ: Индексы в geocache (если отсутствуют)
# ============================================================================
# НАЙТИ в классе geocache __table_args__ или создать, если нет:
    __table_args__ = (
        Index("ix_geocache_created_at", "created_at"),
    )


# ============================================================================
# 6. ДОБАВЛЕНИЕ: Индексы в staff_cities (если отсутствуют)
# ============================================================================
# НАЙТИ в классе staff_cities после created_at:
    __table_args__ = (
        Index("ix_staff_cities__staff_user_id", "staff_user_id"),
        Index("ix_staff_cities__city_id", "city_id"),
    )


# ============================================================================
# 7. ДОБАВЛЕНИЕ: Индексы в staff_access_code_cities (если отсутствуют)
# ============================================================================
# НАЙТИ в классе staff_access_code_cities после created_at:
    __table_args__ = (
        Index("ix_staff_code_cities__code", "access_code_id"),
        Index("ix_staff_code_cities__city", "city_id"),
    )


# ============================================================================
# 8. ПРОВЕРКА: master_invite_codes FK имя
# ============================================================================
# НАЙТИ в классе master_invite_codes:
#     issued_by_staff_id: Mapped[Optional[int]] = mapped_column(
#         ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
#     )
#
# ПРОВЕРИТЬ: В ALL_BD.md это поле называется issued_by_staff_id, 
# поэтому здесь исправление не требуется. Но добавим индекс если нет:
    __table_args__ = (
        Index(
            "ix_master_invite_codes__available",
            "code",
            unique=True,
            postgresql_where=text("used_by_master_id IS NULL AND is_revoked = false AND expires_at IS NULL")
        ),
    )


# ============================================================================
# 9. ПРОВЕРКА: master_districts и master_skills - индексы
# ============================================================================
# НАЙТИ в классе master_districts после created_at:
    __table_args__ = (
        Index("ix_master_districts__district", "district_id"),
    )

# НАЙТИ в классе master_skills после created_at:
    __table_args__ = (
        Index("ix_master_skills__skill", "skill_id"),
    )


# ============================================================================
# ФИНАЛЬНЫЙ ШАГ: Создать миграцию Alembic
# ============================================================================
# После применения всех изменений выполнить:
# 
# cd C:\ProjectF\field-service
# alembic revision --autogenerate -m "sync_models_with_db_schema"
# alembic upgrade head
