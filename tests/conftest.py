import pytest

from lessons_vault import db
from lessons_vault.models import LessonIn
from lessons_vault.repository import Repository


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def repo(conn):
    return Repository(conn)


def beispiel(**overrides) -> LessonIn:
    data = dict(
        titel="Selbstauskunft vor Bankgespräch vollständig",
        situation="Erstes Finanzierungsgespräch für eine Eigentumswohnung.",
        ereignis="Die Bank konnte ohne Gehaltsnachweise kein Angebot machen, Termin musste wiederholt werden.",
        lesson="Vor jedem Bankgespräch die komplette Unterlagenliste der Bank vorab anfordern und abhaken.",
        massnahme="Checkliste Bankunterlagen im Ordner Immobilien pflegen",
        bereich="Immobilien",
        tags=["Bank", "Finanzierung"],
        schweregrad=3,
    )
    data.update(overrides)
    return LessonIn(**data)
