"""Public trust endpoints: reproducible-build proof and append-only audit log."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

REPOSITORY_URL = "https://github.com/cryptorugmuncher/walletpress"


@router.get(
    "/trust/build",
    tags=["trust"],
    summary="Trust Build",
    description="Reproducible build verification. Returns source commit hash and Docker image metadata for build reproducibility verification.",
)
async def trust_build():
    """Source commit + build recipe so anyone can rebuild and compare image SHAs."""
    from core.proof import get_source_tree_hash

    commit = get_source_tree_hash()
    has_commit = commit != "unknown"
    return {
        "service": "WalletPress",
        "source_repository": REPOSITORY_URL,
        "source_commit": commit,
        "source_commit_url": f"{REPOSITORY_URL}/commit/{commit}" if has_commit else "",
        "build_method": "Docker multi-stage build (see Dockerfile)",
        "build_command": "docker build -t walletpress .",
        "verify_command": "docker pull walletpress && docker inspect walletpress --format '{{.Id}}' | cut -d: -f2",
        "reproducible": True,
        "note": "Build from source, compare the image SHA. If they match, the binary matches the code.",
    }


@router.get(
    "/trust/audit",
    tags=["trust"],
    summary="Trust Audit",
    description="Public audit log. Returns recent immutable audit entries proving operational transparency.",
)
async def trust_audit():
    """Recent entries from the append-only audit log."""
    from core.audit import get_audit

    audit = get_audit()
    stats = audit.stats()
    return {
        "service": "WalletPress Audit Log",
        "total_entries": stats.get("total_entries", 0),
        "file_size_bytes": stats.get("file_size", 0),
        "append_only": True,
        "immutable": True,
        "recent_entries": audit.query(limit=50),
        "note": "Audit log is append-only. Entries cannot be modified or deleted.",
    }
