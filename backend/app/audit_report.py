"""PDF rendering for stored GridSentinel incident audit records."""

from __future__ import annotations

from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.audit_store import IncidentRecord


def _display(value: object) -> str:
    if value is None:
        return "Not recorded"
    text = str(value).strip()
    return text if text else "Not recorded"


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_display(value)).replace("\n", "<br/>") , style)


def build_incident_report(record: IncidentRecord) -> bytes:
    """Render a formal report using only values present in *record*."""

    output = BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#172435"),
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )
    subtitle = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#53647F"),
        alignment=TA_CENTER,
        spaceAfter=7 * mm,
    )
    section = ParagraphStyle(
        "ReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#172435"),
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#26354A"),
    )
    label = ParagraphStyle(
        "ReportLabel",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#53647F"),
    )
    footer = ParagraphStyle(
        "ReportFooter",
        parent=body,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#68758A"),
        alignment=TA_CENTER,
    )

    metadata = [
        [_paragraph("Incident ID", label), _paragraph(record.id, body)],
        [_paragraph("UTC timestamp", label), _paragraph(record.timestamp, body)],
        [_paragraph("Simulation time", label), _paragraph(record.sim_time, body)],
        [_paragraph("Affected RTU", label), _paragraph(record.rtu_id, body)],
        [_paragraph("Affected asset / bus", label), _paragraph(record.asset_name, body)],
        [_paragraph("Verdict", label), _paragraph(record.verdict, body)],
        [_paragraph("Subtype", label), _paragraph(record.subtype, body)],
        [_paragraph("Confidence", label), _paragraph(
            f"{record.confidence * 100:.1f}%" if record.confidence is not None else None,
            body,
        )],
    ]

    evidence = [
        [_paragraph("Network / Modbus evidence", label), _paragraph(record.network_evidence, body)],
        [_paragraph("Physics / power-flow evidence", label), _paragraph(record.physics_evidence, body)],
        [_paragraph("Conclusion", label), _paragraph(record.conclusion, body)],
    ]

    story = [
        Paragraph("GridSentinel Incident Report", title),
        Paragraph("CEA-2026 operational reference · advisory incident record", subtitle),
        Paragraph("Incident metadata", section),
        Table(
            metadata,
            colWidths=[47 * mm, 123 * mm],
            repeatRows=0,
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E9EEF4")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9AAEC8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C7D1DE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
        Paragraph("Explainable evidence", section),
        Table(
            evidence,
            colWidths=[55 * mm, 115 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E9EEF4")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9AAEC8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C7D1DE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]),
        ),
        Paragraph("Operator record", section),
        Table([
            [_paragraph("Recommended action", label), _paragraph(record.recommended_action, body)],
            [_paragraph("Incident description", label), _paragraph(record.formatted_alert, body)],
        ], colWidths=[47 * mm, 123 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E9EEF4")),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9AAEC8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C7D1DE")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])),
        Spacer(1, 12 * mm),
        Paragraph(
            "This is an advisory-system-generated report and not an official CSIRT-Power filing.",
            footer,
        ),
    ]

    def draw_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#C7D1DE"))
        canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#68758A"))
        canvas.drawCentredString(105 * mm, 10 * mm, f"GridSentinel · Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"GridSentinel Incident Report {record.id}",
        author="GridSentinel advisory system",
    )
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return output.getvalue()
