def process_document_job(db: Session, document_id: uuid.UUID, job_id: uuid.UUID | None = None, worker_name: str | None = None) -> Document:
    """Run the full ingestion pipeline and persist durable job status.

    Heavy lifting lives in ``app.rag.ingestion.pipeline.IngestionPipeline``
    (validation -> parsing -> normalization -> metadata -> dedupe/version ->
    chunking -> real embeddings -> Qdrant -> lexical rows -> version record).
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise ValueError("Document not found")

    job: Optional[IngestionJob] = db.get(IngestionJob, job_id) if job_id else None
    if job is None:
        job = (
            db.query(IngestionJob)
            .filter(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .first()
        )
    if job is None:
        job = create_ingestion_job(db, doc, attempt=(doc.retry_count or 0) + 1)

    job_id = job.id
    now = datetime.now(timezone.utc)
    job.status = IngestionJobStatus.running
    job.started_at = job.started_at or now
    job.worker = worker_name or job.worker
    doc.status = DocumentStatus.processing
    doc.error_message = None
    db.commit()

    try:
        from app.rag.config import RagConfig
        from app.rag.ingestion.pipeline import IngestionPipeline

        outcome = IngestionPipeline(RagConfig.from_settings()).run(db, doc)
        doc.doc_metadata = metadata_to_json(outcome.metadata)
        doc.status = DocumentStatus.completed
        doc.error_message = None
        job.status = IngestionJobStatus.succeeded
        job.error_message = None
        job.error_details = None
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(doc)
        return doc
    except Exception as e:  # noqa: BLE001
        db.rollback()
        doc = db.get(Document, document_id)
        job = db.get(IngestionJob, job_id)
        if doc is None or job is None:
            raise
        attempt = job.attempt or 1
        max_attempts = job.max_attempts or settings.ingestion_max_retries
        doc.retry_count = max(0, attempt - 1)
        doc.error_message = str(e)[:1000]
        job.error_message = str(e)[:1000]
        job.error_details = _error_details(e)
        job.finished_at = datetime.now(timezone.utc)
        if attempt < max_attempts:
            job.status = IngestionJobStatus.retrying
            doc.status = DocumentStatus.pending
        else:
            job.status = IngestionJobStatus.failed
            doc.status = DocumentStatus.failed
        db.commit()
        raise
