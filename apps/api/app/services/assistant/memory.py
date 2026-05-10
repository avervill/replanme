"""Persistent planning memory for user scheduling preferences."""

from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.energy_profile import EnergyProfile
from app.models.planning_memory import PlanningMemory
from app.models.user import User
from app.schemas.assistant import (
    MemoryResponse,
    UserPlanningMemory,
    UserPlanningMemoryUpdate,
)


class PlanningMemoryService:
    async def get_memory(self, db: AsyncSession, user: User) -> MemoryResponse:
        result = await db.execute(
            select(PlanningMemory).where(PlanningMemory.user_id == user.id)
        )
        stored = result.scalar_one_or_none()
        if stored is not None:
            return MemoryResponse(
                memory=UserPlanningMemory.model_validate(stored.memory),
                source="stored",
            )

        seeded = await self._default_memory(db, user)
        return MemoryResponse(memory=seeded, source="default")

    async def update_memory(
        self,
        db: AsyncSession,
        user: User,
        update: UserPlanningMemoryUpdate,
    ) -> MemoryResponse:
        current = await self.get_memory(db, user)
        merged = current.memory.model_copy(
            update=update.model_dump(exclude_none=True),
        )

        result = await db.execute(
            select(PlanningMemory).where(PlanningMemory.user_id == user.id)
        )
        stored = result.scalar_one_or_none()
        if stored is None:
            stored = PlanningMemory(user_id=user.id, memory=merged.model_dump(mode="json"))
        else:
            stored.memory = merged.model_dump(mode="json")

        db.add(stored)
        await db.commit()
        await db.refresh(stored)
        return MemoryResponse(memory=merged, source="updated")

    async def apply_writebacks(
        self,
        db: AsyncSession,
        user: User,
        updates: list[UserPlanningMemoryUpdate],
    ) -> MemoryResponse:
        current = await self.get_memory(db, user)
        merged = current.memory
        for update in updates:
            merged = merged.model_copy(update=update.model_dump(exclude_none=True))
        return await self.update_memory(
            db,
            user,
            UserPlanningMemoryUpdate.model_validate(
                merged.model_dump(mode="json"),
            ),
        )

    async def _default_memory(self, db: AsyncSession, user: User) -> UserPlanningMemory:
        focus_windows = []
        high_energy_windows = []
        medium_energy_windows = []
        low_energy_windows = []

        result = await db.execute(
            select(EnergyProfile).where(EnergyProfile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if profile is not None:
            high_energy_windows.append(
                {
                    "start": profile.peak_start,
                    "end": profile.peak_end,
                    "label": "Peak focus",
                }
            )
            low_energy_windows.append(
                {
                    "start": profile.slump_start,
                    "end": profile.slump_end,
                    "label": "Low energy",
                }
            )
            focus_windows.append(
                {
                    "start": profile.peak_start,
                    "end": profile.peak_end,
                    "label": "Preferred deep work",
                }
            )
            medium_energy_windows.append(
                {
                    "start": time(hour=12),
                    "end": profile.slump_start,
                    "label": "Meetings and admin",
                }
            )

        notes = ["Respect recovery time between cognitively heavy sessions."]
        return UserPlanningMemory(
            focus_windows=focus_windows,
            high_energy_windows=high_energy_windows,
            medium_energy_windows=medium_energy_windows,
            low_energy_windows=low_energy_windows,
            scheduling_preferences=[
                "Protect sleep boundaries.",
                "Avoid stacking intense tasks without a break.",
            ],
            notes=notes,
        )

