from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refund import RefundRequest


class RefundRequestRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> RefundRequest | None:
        result = await self.db.execute(
            select(RefundRequest).where(
                RefundRequest.idempotency_key
                == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def get_by_request_no(
        self,
        request_no: str,
    ) -> RefundRequest | None:
        result = await self.db.execute(
            select(RefundRequest).where(
                RefundRequest.request_no == request_no
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_order_id(
        self,
        order_id: int,
    ) -> RefundRequest | None:
        result = await self.db.execute(
            select(RefundRequest)
            .where(
                RefundRequest.order_id == order_id,
                RefundRequest.status.in_(
                    ("PENDING", "PROCESSING")
                ),
            )
            .order_by(RefundRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        order_id: int,
        reason: str,
        amount: float,
        idempotency_key: str,
    ) -> tuple[RefundRequest, bool]:
        existing = await self.get_by_idempotency_key(
            idempotency_key
        )

        if existing is not None:
            return existing, False

        # 第二道业务幂等：即使从另一个工单生成了不同的请求键，
        # 同一订单也不能同时存在多条有效退款申请。
        existing = await self.get_active_by_order_id(order_id)
        if existing is not None:
            return existing, False

        refund = RefundRequest(
            request_no=f"RF-{uuid4().hex[:16].upper()}",
            order_id=order_id,
            idempotency_key=idempotency_key,
            active_order_key=f"order:{order_id}",
            status="PENDING",
            reason=reason,
            amount=amount,
        )
        self.db.add(refund)

        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_by_idempotency_key(
                idempotency_key
            )

            if existing is None:
                # 另一个并发请求可能使用了不同的幂等键，但命中了
                # active_order_key 的订单级唯一约束。
                existing = await self.get_active_by_order_id(order_id)

            if existing is None:
                raise

            return existing, False

        await self.db.refresh(refund)
        return refund, True
