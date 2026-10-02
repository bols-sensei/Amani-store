"""Stockage des documents PDF sur disque local (adaptateur remplaçable).

Structure : {STORAGE_PATH}/documents/{year}/{month}/{filename}.pdf
Le protocole `DocumentStorage` permettra de brancher S3/OSS plus tard sans
toucher aux services.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class DocumentStorage(Protocol):
    """Contrat de stockage documentaire (disque local aujourd'hui, S3 demain)."""

    def save(self, content: bytes, subpath: str) -> str: ...
    def read(self, url: str) -> bytes: ...


class LocalDocumentStorage:
    """Implémentation disque local (STORAGE_PATH)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.STORAGE_PATH)

    def save(self, content: bytes, subpath: str) -> str:
        """Écrit le fichier et retourne l'URL relative /media/... servie par FastAPI."""
        target = (self.root / "documents" / subpath).resolve()
        base = (self.root / "documents").resolve()
        if not str(target).startswith(str(base)):
            raise ValueError("Chemin document hors racine de stockage")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return f"/media/documents/{subpath}"

    def read(self, url: str) -> bytes:
        """Relit un fichier depuis son URL /media/... (chemin relatif sécurisé)."""
        rel = url.removeprefix("/media/")
        target = (self.root / rel).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError("Chemin document hors racine de stockage")
        return target.read_bytes()


_storage = LocalDocumentStorage()


def get_storage() -> LocalDocumentStorage:
    """Accès à l'adaptateur courant (singleton ; à remplacer via settings plus tard)."""
    return _storage


def build_document_path(kind: str, filename: str, when: datetime | None = None) -> str:
    """Construit {kind}/{YYYY}/{MM}/{filename} (UTC)."""
    now = when or datetime.now(timezone.utc)
    return f"{kind}/{now.year:04d}/{now.month:02d}/{filename}"


def generate_qr_code(text: str) -> str | None:
    """QR PNG en base64 data-URI si `qrcode` est installé, sinon None.

    Le QR encode l'URL publique de vérification du document.
    """
    try:
        import base64
        import io

        import qrcode  # type: ignore[import-untyped]
    except ImportError:
        return None
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
