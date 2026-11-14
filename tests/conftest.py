import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings  # noqa: E402
from core.state import DocumentRegistry  # noqa: E402
from orchestration.adapters import Services  # noqa: E402
from orchestration.supervisor import SupervisorGraph  # noqa: E402
from orchestration.workflow import _Runtime  # noqa: E402

CONTRACT_V1 = """EMPLOYMENT AGREEMENT
This Employment Agreement is entered into on 1 January 2026 between Acme Corp Ltd (the "Employer") and Jane Doe (the "Employee").

1. Position
The Employee shall serve as Software Engineer and shall report to the CTO.

2. Compensation
The Employer shall pay the Employee a monthly salary of 5,000 USD on the last day of each month.

8. Termination
Either party may terminate this Agreement by giving 30 days written notice to the other party.

9. Confidentiality
The Employee must keep all Confidential Information secret during and after employment.

10. Non-Compete
The Employee shall not work for a competitor for 24 months after termination.
"""

CONTRACT_V2 = CONTRACT_V1.replace("5,000 USD", "5,500 USD").replace("30 days", "60 days") + """
11. Indemnification
The Employee shall indemnify the Employer against all losses.
"""


def make_docx(path: Path, text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    d.save(str(path))
    return path.read_bytes()


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(upload_dir=tmp_path / "uploads", processed_dir=tmp_path / "processed",
                        vector_db_dir=tmp_path / "vdb", reports_dir=tmp_path / "reports", max_upload_mb=1)
    settings.ensure_dirs()
    registry = DocumentRegistry(settings.processed_dir)
    services = Services(prefer_real=False)
    rt = _Runtime()
    rt.settings, rt.registry, rt.services = settings, registry, services
    rt.graph = SupervisorGraph(services, registry, settings)
    return rt


@pytest.fixture
def docx_bytes(tmp_path):
    return make_docx(tmp_path / "v1.docx", CONTRACT_V1), make_docx(tmp_path / "v2.docx", CONTRACT_V2)
