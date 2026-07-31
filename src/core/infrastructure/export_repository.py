from core.infrastructure.db.export_models import XmpExportRecord
from core.infrastructure.db.repository import SqlAlchemyRepository


class XmpExportRecordRepository(SqlAlchemyRepository[XmpExportRecord]):
    model = XmpExportRecord
