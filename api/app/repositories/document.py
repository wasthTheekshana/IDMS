import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        org_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        r2_key: str,
    ) -> Document:
        doc = Document(
            id=uuid.uuid4(),
            org_id=org_id,
            uploaded_by=uploaded_by,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            r2_key=r2_key,
        )
        self._s.add(doc)
        await self._s.flush()
        return doc

    async def get_by_id(
        self, doc_id: uuid.UUID, org_id: uuid.UUID | None = None
    ) -> Document | None:
        q = select(Document).where(Document.id == doc_id)
        if org_id:
            q = q.where(Document.org_id == org_id)
        result = await self._s.execute(q)
        return result.scalar_one_or_none()

    async def list_for_org(self, org_id: uuid.UUID) -> Sequence[Document]:
        result = await self._s.execute(
            select(Document)
            .where(Document.org_id == org_id)
            .order_by(Document.created_at.desc())
        )
        return result.scalars().all()

    async def set_status(
        self,
        doc_id: uuid.UUID,
        status: DocumentStatus,
        *,
        page_count: int | None = None,
        extracted_text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status.value}
        if page_count is not None:
            values["page_count"] = page_count
        if extracted_text is not None:
            values["extracted_text"] = extracted_text
        if error_message is not None:
            values["error_message"] = error_message
        await self._s.execute(
            update(Document).where(Document.id == doc_id).values(**values)
        )
        await self._s.flush()
