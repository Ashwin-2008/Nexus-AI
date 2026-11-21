"""Connected intelligence services for email, documents, and report exports."""
from __future__ import annotations

import csv
import difflib
import io
import json
import re
import uuid
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.connector import DataSource
from app.models.document import Document
from app.services.connectors import ConnectorContext, ConnectorError, get_connector, parse_config
from app.services.credentials import decrypt_credentials
from app.services.ingestion_service import load_document_bytes
from app.services.processing import FileExtractor, ProcessingContext, TextNormalizer
from app.services.storage import get_storage_backend


def _email_context(db: Session, organization_id: uuid.UUID, source_id: uuid.UUID) -> ConnectorContext:
    source = db.get(DataSource, source_id)
    if source is None or source.organization_id != organization_id or source.type != "email":
        raise ConnectorError("Email source not found or not permitted")
    return ConnectorContext(
        config=parse_config(source.config),
        credentials=decrypt_credentials(source.credentials_encrypted),
    )


def search_email(
    db: Session,
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    query: str,
    max_items: int = 20,
) -> dict[str, Any]:
    context = _email_context(db, organization_id, source_id)
    connector = get_connector("email")
    connector.validate(context)
    items = connector.fetch(context, max_items=max_items)
    needle = query.casefold().strip()
    matches = [
        {
            "external_id": item.external_id,
            "subject": item.title,
            "body": item.text or "",
            "uri": item.uri,
            "metadata": item.metadata,
        }
        for item in items
        if not needle or needle in f"{item.title}\n{item.text or ''}".casefold()
    ]
    return {"source_id": str(source_id), "query": query, "count": len(matches), "messages": matches}


def send_email(
    db: Session,
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    context = _email_context(db, organization_id, source_id)
    if not recipients or any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address) for address in recipients):
        raise ConnectorError("Every email recipient must be a valid address")
    if not subject.strip() or not body.strip():
        raise ConnectorError("Email subject and body are required")
    host = str(context.config.get("smtp_host") or context.config.get("host") or "")
    port = int(context.config.get("smtp_port", 465))
    username = str(context.credentials.get("username") or "")
    password = str(context.credentials.get("password") or "")
    sender = str(context.config.get("from_address") or username)
    if not host or not username or not password or not sender:
        raise ConnectorError("SMTP host, sender, username, and password are required")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    for attachment in attachments or []:
        key = attachment.get("storage_key", "")
        filename = attachment.get("filename", "")
        if not key.startswith(f"orgs/{organization_id}/") or not filename:
            raise ConnectorError("Attachment is not authorized for this organization")
        data = get_storage_backend().get_bytes(key)
        message.add_attachment(data, maintype="application", subtype="octet-stream", filename=filename)
    try:
        if bool(context.config.get("smtp_ssl", True)):
            with smtplib.SMTP_SSL(host, port, timeout=20) as client:
                client.login(username, password)
                client.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as client:
                client.starttls()
                client.login(username, password)
                client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise ConnectorError(f"SMTP delivery failed: {exc}") from exc
    return {"status": "sent", "recipients": recipients, "subject": subject}


def extract_document(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any]:
    document = db.get(Document, document_id)
    if document is None or document.organization_id != organization_id:
        raise ValueError("Document not found")
    content = load_document_bytes(document.storage_path, document.storage_backend)
    extracted = FileExtractor().extract(
        content,
        ProcessingContext(
            document_id=str(document.id),
            organization_id=str(organization_id),
            filename=document.filename,
            content_type=document.content_type,
            storage_path=document.storage_path,
            storage_backend=document.storage_backend,
        ),
    )
    extracted = TextNormalizer().normalize(extracted)
    text = extracted.text
    dates = sorted(set(re.findall(r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b", text)))
    entities = sorted(set(re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}(?:\s+[A-Z][A-Za-z0-9&.-]{2,})*\b", text)))
    obligations = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if re.search(r"\b(shall|must|required to|will|agrees to|obligation)\b", sentence, re.IGNORECASE)
    ][:50]
    return {
        "document_id": str(document.id),
        "filename": document.filename,
        "text": text,
        "metadata": extracted.metadata,
        "spans": extracted.spans,
        "warnings": extracted.warnings,
        "dates": dates,
        "entities": entities[:100],
        "obligations": obligations,
    }


def compare_documents(db: Session, organization_id: uuid.UUID, document_ids: list[uuid.UUID]) -> dict[str, Any]:
    if len(document_ids) < 2:
        raise ValueError("At least two documents are required")
    documents = [extract_document(db, organization_id, document_id) for document_id in document_ids]
    baseline = documents[0]["text"].splitlines()
    comparisons = []
    for document in documents[1:]:
        diff = list(difflib.unified_diff(baseline, document["text"].splitlines(), lineterm=""))
        comparisons.append(
            {
                "document_id": document["document_id"],
                "filename": document["filename"],
                "changed_lines": [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))][:100],
            }
        )
    return {
        "documents": [
            {
                "document_id": document["document_id"],
                "filename": document["filename"],
                "dates": document["dates"],
                "entities": document["entities"],
                "obligations": document["obligations"],
                "spans": document["spans"],
            }
            for document in documents
        ],
        "comparisons": comparisons,
        "citations": [{"document_id": document["document_id"], "filename": document["filename"]} for document in documents],
    }


def export_report(organization_id: uuid.UUID, report_id: str, report: dict[str, Any], file_format: str) -> dict[str, Any]:
    file_format = file_format.lower()
    title = str(report.get("title") or "NEXUS AI Report")
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    if file_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        if rows and isinstance(rows[0], dict):
            writer.writerow(rows[0].keys())
            writer.writerows([row.values() for row in rows])
        else:
            writer.writerow(["report", "value"])
            writer.writerow([title, json.dumps(report, ensure_ascii=False, default=str)])
        data, content_type = output.getvalue().encode(), "text/csv"
    elif file_format == "xlsx":
        import openpyxl

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Report"
        sheet.append(["report", "value"])
        sheet.append([title, json.dumps(report, ensure_ascii=False, default=str)])
        buffer = io.BytesIO()
        workbook.save(buffer)
        data, content_type = buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif file_format == "docx":
        import docx

        document = docx.Document()
        document.add_heading(title, level=1)
        document.add_paragraph(json.dumps(report, ensure_ascii=False, default=str))
        buffer = io.BytesIO()
        document.save(buffer)
        data, content_type = buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif file_format == "pdf":
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        pdf.setTitle(title)
        y = 760
        for line in json.dumps(report, ensure_ascii=False, default=str).splitlines():
            pdf.drawString(40, y, line[:110])
            y -= 14
            if y < 40:
                pdf.showPage()
                y = 760
        pdf.save()
        data, content_type = buffer.getvalue(), "application/pdf"
    else:
        raise ValueError("Supported report formats are pdf, docx, xlsx, and csv")
    key = f"orgs/{organization_id}/reports/{report_id}.{file_format}"
    stored_key = get_storage_backend().put_bytes(key, data, content_type)
    return {"report_id": report_id, "format": file_format, "storage_key": stored_key, "content_type": content_type, "size": len(data)}
