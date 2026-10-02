"""Service de stockage d'images — abstraction adaptateur (disque local aujourd'hui, S3 demain).

PRINCIPE : aucune route ne parle directement au filesystem. On passe par le
protocole `StorageAdapter`. Pour brancher S3/Cloudflare R2 plus tard : implémenter
le protocole et changer `get_storage()` — zéro impact sur les endpoints.

Structure disque : {STORAGE_PATH}/products/{tenant_id}/{product_id}/{uuid}.{ext}
Variants générés (Pillow) : thumb 200x200, medium 600x600, large 1200x1200.
Formats acceptés : jpg/jpeg/png/webp. Taille max : business_rule `images.max_size_mb` (5 par défaut).
"""

import asyncio
import io
import logging
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.crud.business_rule import get_rule_number
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
THUMB_SIZES: dict[str, int] = {"thumb": 200, "medium": 600, "large": 1200}


class StorageAdapter(Protocol):
    """Protocole minimal qu'un adaptateur de stockage doit respecter."""

    async def save_image(self, data: bytes, ext: str, tenant_id: str, product_id: str) -> dict[str, str]:
        """Sauvegarde l'image + variantes. Retourne {'url','thumb_url','medium_url','large_url'} (URLs publiques)."""
        ...

    async def delete_image(self, url: str) -> None:
        """Supprime l'image et ses variantes depuis une URL publique."""
        ...

    def get_image_url(self, relative_path: str) -> str:
        """Convertis un chemin relatif en URL publique servie par FastAPI."""
        ...


def _slug_to_public_url(rel_path: str) -> str:
    """Chemin relatif sous STORAGE_PATH → URL statique servie par /media."""
    return f"/media/{rel_path.lstrip('/')}"


def _process_sync(data: bytes, ext: str, base_dir: Path, stem: str) -> dict[str, str]:
    """(CPU-bound, exécuté dans un thread) Écrit l'original + thumbnails Pillow."""
    from PIL import Image

    base_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}

    original_path = base_dir / f"{stem}.{ext}"
    original_path.write_bytes(data)
    result["url"] = _slug_to_public_url(str(original_path.relative_to(STORAGE_ROOT)))

    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB") if img.mode in ("P", "CMYK", "RGBA") and ext in ("jpg", "jpeg") else img
        for variant, size in THUMB_SIZES.items():
            v = img.copy()
            v.thumbnail((size, size), Image.LANCZOS)
            out = base_dir / f"{stem}_{variant}.webp"
            v.save(out, "WEBP", quality=82)
            result[f"{variant}_url"] = _slug_to_public_url(str(out.relative_to(STORAGE_ROOT)))
    except Exception as exc:  # image non décodable → on garde juste l'original
        logger.warning("thumbnail generation failed (%s): %s", stem, exc)
        for variant in THUMB_SIZES:
            result.setdefault(f"{variant}_url", result["url"])

    return result


STORAGE_ROOT = Path(settings.STORAGE_PATH)


class LocalDiskStorage:
    """Adaptateur disque local (Oracle Cloud Free Tier)."""

    async def save_image(self, data: bytes, ext: str, tenant_id: str, product_id: str) -> dict[str, str]:
        """Sauvegarde asynchrone (thread pool) de l'image + variantes."""
        ext = ext.lower().lstrip(".")
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Format interdit : {ext}. Autorisés : {', '.join(sorted(ALLOWED_EXTENSIONS))}")
        max_mb = await self._max_size_mb()
        if len(data) > max_mb * 1024 * 1024:
            raise ValueError(f"Image trop volumineuse (max {max_mb} MB)")
        stem = uuid.uuid4().hex
        base_dir = STORAGE_ROOT / "products" / tenant_id / product_id
        return await asyncio.to_thread(_process_sync, data, ext, base_dir, stem)

    async def delete_image(self, url: str) -> None:
        """Supprime le fichier original + ses variantes (best effort)."""
        if not url.startswith("/media/"):
            return
        rel = url[len("/media/"):]
        path = STORAGE_ROOT / rel
        await asyncio.to_thread(self._delete_variant_set, path)

    @staticmethod
    def _delete_variant_set(path: Path) -> None:
        stem = path.name.rsplit(".", 1)[0]
        parent = path.parent
        for candidate in [path, *[parent / f"{stem}_{v}.webp" for v in THUMB_SIZES]]:
            try:
                candidate.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("delete_image failed %s: %s", candidate, exc)

    def get_image_url(self, relative_path: str) -> str:
        """Chemin relatif → URL publique."""
        return _slug_to_public_url(relative_path)

    @staticmethod
    async def _max_size_mb() -> int:
        """Taille max lue depuis business_rules (config-driven, jamais codée en dur)."""
        try:
            async with AsyncSessionLocal() as db:
                val = await get_rule_number(db, "images.max_size_mb", default=5)
                return int(val)
        except Exception:
            return 5


_adapter: StorageAdapter | None = None


def get_storage() -> StorageAdapter:
    """Singleton de l'adaptateur de stockage (à remplacer par S3 via config plus tard)."""
    global _adapter
    if _adapter is None:
        _adapter = LocalDiskStorage()
    return _adapter
