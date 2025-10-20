"""    ."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal


UTC = timezone.utc


@dataclass
class DistributionStats:
    """   ."""
    total_assignments: int
    avg_time_to_assign: float
    avg_round_number: float
    avg_candidates: float
    
    #   preferred 
    preferred_used_pct: float
    
    #  
    escalated_to_logist_pct: float
    escalated_to_admin_pct: float
    
    #   
    round_1_pct: float
    round_2_pct: float
    round_3_plus_pct: float
    
    #    
    fast_assign_pct: float  # < 2 
    medium_assign_pct: float  # 2-5 
    slow_assign_pct: float  # > 5 


@dataclass
class CityPerformance:
    """   ."""
    city_id: int
    city_name: str
    total_assignments: int
    avg_time_to_assign: float
    escalation_rate: float


@dataclass
class MasterPerformance:
    """   ."""
    master_id: int
    master_name: str
    total_assignments: int
    from_preferred: int
    from_auto: int
    from_manual: int
    avg_round_received: float


class DistributionMetricsService:
    """     ."""
    
    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory
    
    async def get_stats(
        self,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        city_id: Optional[int] = None,
    ) -> DistributionStats:
        """
            .
        
        Args:
            start_date:   (default:  7 )
            end_date:   (default: )
            city_id:    (optional)
        """
        if end_date is None:
            end_date = datetime.now(UTC)
        if start_date is None:
            start_date = end_date - timedelta(days=7)
        
        async with self._session_factory() as session:
            #  
            filters = [
                m.distribution_metrics.assigned_at >= start_date,
                m.distribution_metrics.assigned_at <= end_date,
            ]
            if city_id:
                filters.append(m.distribution_metrics.city_id == city_id)
            
            #  
            result = await session.execute(
                select(
                    func.count(m.distribution_metrics.id).label('total'),
                    func.avg(m.distribution_metrics.time_to_assign_seconds).label('avg_time'),
                    func.avg(m.distribution_metrics.round_number).label('avg_round'),
                    func.avg(m.distribution_metrics.candidates_count).label('avg_candidates'),
                    func.sum(
                        case((m.distribution_metrics.preferred_master_used == True, 1), else_=0)
                    ).label('preferred_count'),
                    func.sum(
                        case((m.distribution_metrics.was_escalated_to_logist == True, 1), else_=0)
                    ).label('logist_escalations'),
                    func.sum(
                        case((m.distribution_metrics.was_escalated_to_admin == True, 1), else_=0)
                    ).label('admin_escalations'),
                    #   
                    func.sum(case((m.distribution_metrics.round_number == 1, 1), else_=0)).label('round_1'),
                    func.sum(case((m.distribution_metrics.round_number == 2, 1), else_=0)).label('round_2'),
                    func.sum(case((m.distribution_metrics.round_number >= 3, 1), else_=0)).label('round_3_plus'),
                    #   
                    func.sum(
                        case((m.distribution_metrics.time_to_assign_seconds < 120, 1), else_=0)
                    ).label('fast_count'),
                    func.sum(
                        case((and_(
                            m.distribution_metrics.time_to_assign_seconds >= 120,
                            m.distribution_metrics.time_to_assign_seconds <= 300
                        ), 1), else_=0)
                    ).label('medium_count'),
                    func.sum(
                        case((m.distribution_metrics.time_to_assign_seconds > 300, 1), else_=0)
                    ).label('slow_count'),
                ).where(and_(*filters))
            )
            row = result.first()
            
            if not row or row.total == 0:
                return DistributionStats(
                    total_assignments=0,
                    avg_time_to_assign=0.0,
                    avg_round_number=0.0,
                    avg_candidates=0.0,
                    preferred_used_pct=0.0,
                    escalated_to_logist_pct=0.0,
                    escalated_to_admin_pct=0.0,
                    round_1_pct=0.0,
                    round_2_pct=0.0,
                    round_3_plus_pct=0.0,
                    fast_assign_pct=0.0,
                    medium_assign_pct=0.0,
                    slow_assign_pct=0.0,
                )
            
            total = row.total
            return DistributionStats(
                total_assignments=total,
                avg_time_to_assign=float(row.avg_time or 0),
                avg_round_number=float(row.avg_round or 0),
                avg_candidates=float(row.avg_candidates or 0),
                preferred_used_pct=round((row.preferred_count / total * 100) if total > 0 else 0, 2),
                escalated_to_logist_pct=round((row.logist_escalations / total * 100) if total > 0 else 0, 2),
                escalated_to_admin_pct=round((row.admin_escalations / total * 100) if total > 0 else 0, 2),
                round_1_pct=round((row.round_1 / total * 100) if total > 0 else 0, 2),
                round_2_pct=round((row.round_2 / total * 100) if total > 0 else 0, 2),
                round_3_plus_pct=round((row.round_3_plus / total * 100) if total > 0 else 0, 2),
                fast_assign_pct=round((row.fast_count / total * 100) if total > 0 else 0, 2),
                medium_assign_pct=round((row.medium_count / total * 100) if total > 0 else 0, 2),
                slow_assign_pct=round((row.slow_count / total * 100) if total > 0 else 0, 2),
            )
    
    async def get_city_performance(
        self,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
    ) -> List[CityPerformance]:
        """   ."""
        if end_date is None:
            end_date = datetime.now(UTC)
        if start_date is None:
            start_date = end_date - timedelta(days=7)
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    m.distribution_metrics.city_id,
                    m.cities.name.label('city_name'),
                    func.count(m.distribution_metrics.id).label('total'),
                    func.avg(m.distribution_metrics.time_to_assign_seconds).label('avg_time'),
                    func.sum(
                        case((
                            (m.distribution_metrics.was_escalated_to_logist == True) |
                            (m.distribution_metrics.was_escalated_to_admin == True),
                            1
                        ), else_=0)
                    ).label('escalations'),
                )
                .join(m.cities, m.cities.id == m.distribution_metrics.city_id)
                .where(
                    and_(
                        m.distribution_metrics.assigned_at >= start_date,
                        m.distribution_metrics.assigned_at <= end_date,
                    )
                )
                .group_by(m.distribution_metrics.city_id, m.cities.name)
                .order_by(func.count(m.distribution_metrics.id).desc())
                .limit(limit)
            )
            
            cities = []
            for row in result:
                total = row.total or 0
                cities.append(CityPerformance(
                    city_id=row.city_id,
                    city_name=row.city_name,
                    total_assignments=total,
                    avg_time_to_assign=float(row.avg_time or 0),
                    escalation_rate=round((row.escalations / total * 100) if total > 0 else 0, 2),
                ))
            return cities
    
    async def get_master_performance(
        self,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        master_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[MasterPerformance]:
        """   ."""
        if end_date is None:
            end_date = datetime.now(UTC)
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        async with self._session_factory() as session:
            filters = [
                m.distribution_metrics.assigned_at >= start_date,
                m.distribution_metrics.assigned_at <= end_date,
            ]
            if master_id:
                filters.append(m.distribution_metrics.master_id == master_id)
            
            result = await session.execute(
                select(
                    m.distribution_metrics.master_id,
                    m.masters.full_name.label('master_name'),
                    func.count(m.distribution_metrics.id).label('total'),
                    func.sum(
                        case((m.distribution_metrics.preferred_master_used == True, 1), else_=0)
                    ).label('from_preferred'),
                    func.sum(
                        case((
                            m.distribution_metrics.metadata_json['assigned_via'].astext == 'master_bot',
                            1
                        ), else_=0)
                    ).label('from_auto'),
                    func.sum(
                        case((
                            m.distribution_metrics.metadata_json['assigned_via'].astext == 'admin_manual',
                            1
                        ), else_=0)
                    ).label('from_manual'),
                    func.avg(m.distribution_metrics.round_number).label('avg_round'),
                )
                .join(m.masters, m.masters.id == m.distribution_metrics.master_id)
                .where(and_(*filters))
                .group_by(m.distribution_metrics.master_id, m.masters.full_name)
                .order_by(func.count(m.distribution_metrics.id).desc())
                .limit(limit)
            )
            
            masters = []
            for row in result:
                masters.append(MasterPerformance(
                    master_id=row.master_id,
                    master_name=row.master_name or f"Master {row.master_id}",
                    total_assignments=row.total or 0,
                    from_preferred=row.from_preferred or 0,
                    from_auto=row.from_auto or 0,
                    from_manual=row.from_manual or 0,
                    avg_round_received=round(float(row.avg_round or 0), 2),
                ))
            return masters
    
    async def get_hourly_distribution(
        self,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[int, int]:
        """     ."""
        if end_date is None:
            end_date = datetime.now(UTC)
        if start_date is None:
            start_date = end_date - timedelta(days=7)
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    func.extract('hour', m.distribution_metrics.assigned_at).label('hour'),
                    func.count(m.distribution_metrics.id).label('count'),
                )
                .where(
                    and_(
                        m.distribution_metrics.assigned_at >= start_date,
                        m.distribution_metrics.assigned_at <= end_date,
                    )
                )
                .group_by(func.extract('hour', m.distribution_metrics.assigned_at))
                .order_by('hour')
            )
            
            return {int(row.hour): row.count for row in result}

    async def record_assignment(
        self,
        *,
        order_id: int,
        master_id: int,
        round_number: int,
        candidates_count: int,
        time_to_assign_seconds: Optional[int],
        preferred_master_used: bool,
        was_escalated_to_logist: bool,
        was_escalated_to_admin: bool,
        city_id: int,
        district_id: Optional[int],
        category: m.OrderCategory,
        order_type: m.OrderType,
        metadata_json: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """
        Записывает метрику назначения заказа мастеру.
        
        Args:
            order_id: ID заказа
            master_id: ID мастера
            round_number: Номер раунда распределения
            candidates_count: Количество кандидатов
            time_to_assign_seconds: Время до назначения (секунды)
            preferred_master_used: Использован ли preferred_master
            was_escalated_to_logist: Была ли эскалация логисту
            was_escalated_to_admin: Была ли эскалация админу
            city_id: ID города
            district_id: ID района (optional)
            category: Категория заказа
            order_type: Тип заказа
            metadata_json: Дополнительные метаданные
            session: Опциональная сессия (если None - создаётся новая)
        """
        from sqlalchemy import insert
        
        # Если передана сессия - используем её, иначе создаём свою
        if session is not None:
            await session.execute(
                insert(m.distribution_metrics).values(
                    order_id=order_id,
                    master_id=master_id,
                    assigned_at=datetime.now(UTC),
                    round_number=round_number,
                    candidates_count=candidates_count,
                    time_to_assign_seconds=time_to_assign_seconds,
                    preferred_master_used=preferred_master_used,
                    was_escalated_to_logist=was_escalated_to_logist,
                    was_escalated_to_admin=was_escalated_to_admin,
                    city_id=city_id,
                    district_id=district_id,
                    category=category.value if hasattr(category, 'value') else str(category),
                    order_type=order_type.value if hasattr(order_type, 'value') else str(order_type),
                    metadata_json=metadata_json or {},
                )
            )
            # НЕ делаем commit - это ответственность вызывающего кода
        else:
            async with self._session_factory() as new_session:
                await new_session.execute(
                    insert(m.distribution_metrics).values(
                        order_id=order_id,
                        master_id=master_id,
                        assigned_at=datetime.now(UTC),
                        round_number=round_number,
                        candidates_count=candidates_count,
                        time_to_assign_seconds=time_to_assign_seconds,
                        preferred_master_used=preferred_master_used,
                        was_escalated_to_logist=was_escalated_to_logist,
                        was_escalated_to_admin=was_escalated_to_admin,
                        city_id=city_id,
                        district_id=district_id,
                        category=category.value if hasattr(category, 'value') else str(category),
                        order_type=order_type.value if hasattr(order_type, 'value') else str(order_type),
                        metadata_json=metadata_json or {},
                    )
                )
                await new_session.commit()
