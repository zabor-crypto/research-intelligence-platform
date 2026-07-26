"""Storage layer: schema creation, dedup, run tracking."""

from __future__ import annotations

from research_intel.collectors.base import RawSourceRecord, content_checksum
from research_intel.storage import repositories as repo
from research_intel.storage.db import session_scope
from research_intel.storage.migrations import SCHEMA_VERSION, migrate


def _record(**overrides) -> RawSourceRecord:
    base = {
        "source_type": "manual",
        "external_id": "/tmp/a.md",
        "title": "A paper",
        "url": "file:///tmp/a.md",
        "doi": "10.1/abc",
        "checksum": content_checksum("hello"),
    }
    base.update(overrides)
    return RawSourceRecord(**base)


def test_migrate_is_idempotent(engine):
    assert migrate(engine) == SCHEMA_VERSION
    assert migrate(engine) == SCHEMA_VERSION


def test_source_dedup_by_external_id_doi_url_checksum(engine):
    with session_scope(engine) as session:
        _, created = repo.upsert_source(session, _record())
        assert created
        # exact duplicate
        _, created = repo.upsert_source(session, _record())
        assert not created
        # same DOI, different id/url/checksum
        _, created = repo.upsert_source(
            session, _record(external_id="x", url="http://x", checksum=content_checksum("x"))
        )
        assert not created
        # same URL only
        _, created = repo.upsert_source(
            session, _record(external_id="y", doi=None, checksum=content_checksum("y"))
        )
        assert not created
        # same checksum only
        _, created = repo.upsert_source(
            session, _record(external_id="z", doi=None, url="http://z")
        )
        assert not created
        # genuinely new
        _, created = repo.upsert_source(
            session,
            _record(external_id="new", doi="10.2/new", url="http://new",
                    checksum=content_checksum("new")),
        )
        assert created
        assert len(repo.list_sources(session)) == 2


def test_document_dedup_by_content_hash(engine):
    with session_scope(engine) as session:
        source, _ = repo.upsert_source(session, _record())
        _, created = repo.add_document(session, source, kind="fulltext", content_hash="h1")
        assert created
        _, created = repo.add_document(session, source, kind="fulltext", content_hash="h1")
        assert not created


def test_ingestion_run_lifecycle(engine):
    with session_scope(engine) as session:
        run = repo.start_run(session, collector="arxiv", query="q")
        repo.finish_run(session, run, num_found=5, num_new=3)
        assert run.status == "done"
        assert run.num_new == 3
        failed = repo.start_run(session, collector="arxiv", query="q2")
        repo.finish_run(session, failed, 0, 0, error="boom")
        assert failed.status == "failed"
