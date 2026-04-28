from __future__ import annotations

from pathlib import Path

from db import add_product_image, delete_product_images, upsert_product
from services.image_search import collect_candidate_images, download_candidate_images


def ingest_and_collect(product_payload: dict, limit: int = 10) -> dict:
    product_id = upsert_product(product_payload)
    delete_product_images(product_id)

    candidates = collect_candidate_images(product_payload)
    downloaded = download_candidate_images(product_id, candidates, limit=limit)

    for position, image in enumerate(downloaded, start=1):
        add_product_image(
            {
                "product_id": product_id,
                "source": image.source,
                "source_url": image.source_url,
                "local_path": image.local_path,
                "position": position,
                "mime_type": image.mime_type,
                "file_ext": image.file_ext,
                "width_px": image.width_px,
                "height_px": image.height_px,
                "file_size_bytes": image.file_size_bytes,
                "status": image.status,
            }
        )

    return {
        "product_id": product_id,
        "candidate_count": len(candidates),
        "downloaded_count": len(downloaded),
        "product_dir": str(Path(image.local_path).parent) if downloaded else "",
    }
