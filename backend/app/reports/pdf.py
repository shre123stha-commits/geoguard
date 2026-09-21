"""Detection report PDF (task 7.1; appflow Flow E; design §14: print document, white background).

Pure ReportLab. Fonts: Inter/Inter Tight/JetBrains Mono TTFs are embedded when found under
`FONT_DIRS`; otherwise Helvetica/Courier. The report never uses the words "violation" or
"illegal" — it is a screening document and says so.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This document is a satellite screening aid, not a finding. Sentinel imagery has 10 m pixels; "
    "the minimum reliable detection size is about 400 m². Verify on the ground before acting."
)

FONT_DIRS = (
    Path(__file__).resolve().parents[3] / "frontend" / "node_modules" / "@fontsource",
    Path("/usr/share/fonts/truetype"),
)
_FONTS = {"body": "Helvetica", "bold": "Helvetica-Bold", "mono": "Courier"}
_registered = False


def _register_fonts() -> dict[str, str]:
    """Best-effort TTF registration; falls back to core fonts silently."""
    global _registered
    if _registered:
        return _FONTS
    _registered = True
    wanted = {
        "body": ("inter/files/inter-latin-400-normal.ttf", "Inter"),
        "bold": ("inter-tight/files/inter-tight-latin-600-normal.ttf", "InterTight-SemiBold"),
        "mono": ("jetbrains-mono/files/jetbrains-mono-latin-400-normal.ttf", "JetBrainsMono"),
    }
    for key, (rel, name) in wanted.items():
        for root in FONT_DIRS:
            p = root / rel
            if p.is_file():
                try:
                    pdfmetrics.registerFont(TTFont(name, str(p)))
                    _FONTS[key] = name
                except Exception as exc:  # noqa: BLE001 - font problems must not break reports
                    logger.warning("font %s not usable: %s", p, exc)
                break
    return _FONTS


@dataclass
class ReportData:
    detection_id: str
    parcel_name: str
    parcel_category: str
    confidence: str
    score: float
    status: str
    area_m2: float
    centroid_lon: float
    centroid_lat: float
    sources: list[str]
    baseline: tuple[str, str]
    current: tuple[str, str]
    algorithm_version: str
    detected_at: datetime
    metrics: dict[str, float | None]
    history: list[tuple[datetime, str, str, str | None, str | None]]  # at, from, to, by, note
    evidence: dict[str, Path] = field(default_factory=dict)  # kind -> png path
    generated_by: str = ""
    app_url: str = ""
    priority: str = "normal"  # Phase 9 zone context
    zone_lines: list[str] = field(default_factory=list)  # "92 % inside X (source, date)"


def _fmt(v: float | None, nd: int, unit: str = "") -> str:
    return "—" if v is None else f"{v:.{nd}f}{unit}"


def build_report(data: ReportData, generated_at: datetime) -> bytes:
    f = _register_fonts()
    ink = colors.HexColor("#141210")
    soft = colors.HexColor("#5c5852")
    hair = colors.HexColor("#d9d4cb")

    h1 = ParagraphStyle("h1", fontName=f["bold"], fontSize=20, leading=24, textColor=ink)
    h2 = ParagraphStyle(
        "h2", fontName=f["bold"], fontSize=11.5, leading=14, textColor=ink, spaceBefore=6
    )
    body = ParagraphStyle("body", fontName=f["body"], fontSize=9.5, leading=13, textColor=ink)
    small = ParagraphStyle("small", fontName=f["body"], fontSize=8, leading=11, textColor=soft)
    mono = ParagraphStyle("mono", fontName=f["mono"], fontSize=8, leading=11, textColor=soft)
    eyebrow = ParagraphStyle(
        "eyebrow", fontName=f["mono"], fontSize=7.5, leading=10, textColor=soft, alignment=TA_LEFT
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"GeoGuard-EO detection report {data.detection_id[:8]}",
        author="GeoGuard-EO",
    )
    width = A4[0] - doc.leftMargin - doc.rightMargin

    def footer(canvas, _doc) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont(f["mono"], 7)
        canvas.setFillColor(soft)
        canvas.drawString(
            doc.leftMargin,
            10 * mm,
            f"GeoGuard-EO · detection {data.detection_id} · generated "
            f"{generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        )
        canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"page {_doc.page}")
        canvas.restoreState()

    story: list = []  # type: ignore[type-arg]
    story.append(Paragraph("GEOGUARD-EO · SATELLITE SCREENING REPORT", eyebrow))
    story.append(Spacer(1, 3))
    story.append(Paragraph(f"{data.area_m2:,.0f} m² of likely new built-up surface", h1))
    story.append(
        Paragraph(
            f"{data.parcel_name} · {data.parcel_category.replace('_', ' ')} · "
            f"confidence <b>{data.confidence}</b> (score {data.score:.2f}) · status "
            f"<b>{data.status.replace('_', ' ')}</b>",
            body,
        )
    )
    story.append(Spacer(1, 8))

    # key facts table
    rows = [
        ["Detection ID", data.detection_id],
        ["Centre (lat, lon)", f"{data.centroid_lat:.5f}, {data.centroid_lon:.5f}"],
        ["Area", f"{data.area_m2:,.0f} m²"],
        ["Sources", " + ".join(data.sources) or "—"],
        ["Baseline period", f"{data.baseline[0]} → {data.baseline[1]}"],
        ["Current period", f"{data.current[0]} → {data.current[1]}"],
        ["Detected", data.detected_at.strftime("%Y-%m-%d %H:%M UTC")],
        ["Algorithm", data.algorithm_version],
    ]
    if data.zone_lines:
        rows.insert(3, ["Priority", data.priority])
        rows.insert(4, ["Zone context", "<br/>".join(data.zone_lines)])
    t = Table(
        [[Paragraph(a, small), Paragraph(b, body)] for a, b in rows],
        colWidths=[38 * mm, width - 38 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, hair),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    # evidence images
    imgs = [(k, p) for k, p in data.evidence.items() if p.is_file()]
    if imgs:
        story.append(Paragraph("Evidence", h2))
        story.append(
            Paragraph(
                "False-colour composites (shortwave infrared, near infrared, red): vegetation "
                "appears green, bare soil and roofs pink to white, water dark. The change map "
                "brightens where the built-up index rose between the two periods.",
                small,
            )
        )
        story.append(Spacer(1, 4))
        cell_w = (width - 8 * mm) / 3
        labels = {"before_rgb": "BEFORE", "after_rgb": "AFTER", "change_map": "CHANGE MAP"}
        cells, caps = [], []
        for kind, p in imgs[:3]:
            cells.append(Image(str(p), width=cell_w, height=cell_w))
            caps.append(Paragraph(labels.get(kind, kind.upper()), eyebrow))
        it = Table([cells, caps], colWidths=[cell_w] * len(cells), hAlign="LEFT")
        it.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("TOPPADDING", (0, 1), (-1, 1), 2),
                ]
            )
        )
        story.append(KeepTogether(it))
        story.append(Spacer(1, 10))

    # metrics
    story.append(Paragraph("Measurements", h2))
    m = data.metrics
    mrows = [
        ["Optical ΔBUI (built-up index rise)", _fmt(m.get("d_bui_mean"), 2)],
        ["Optical ΔNDVI (vegetation loss)", _fmt(m.get("d_ndvi_mean"), 2)],
        ["Radar Δσ° VV", _fmt(m.get("d_sigma_vv_mean_db"), 1, " dB")],
        [
            "Radar overlap with optical region",
            "—" if m.get("sar_overlap") is None else f"{(m['sar_overlap'] or 0) * 100:.0f} %",
        ],
    ]
    mt = Table(
        [[Paragraph(a, body), Paragraph(b, mono)] for a, b in mrows],
        colWidths=[width - 40 * mm, 40 * mm],
    )
    mt.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, hair),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(mt)
    story.append(Spacer(1, 10))

    # review history
    story.append(Paragraph("Review history", h2))
    if data.history:
        hrows = [
            [
                Paragraph(at.strftime("%Y-%m-%d %H:%M"), mono),
                Paragraph(f"{fr.replace('_', ' ')} → <b>{to.replace('_', ' ')}</b>", body),
                Paragraph(by or "—", small),
                Paragraph(note or "", small),
            ]
            for at, fr, to, by, note in data.history
        ]
        ht = Table(hrows, colWidths=[28 * mm, 42 * mm, 30 * mm, width - 100 * mm])
        ht.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, hair),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(ht)
    else:
        story.append(Paragraph("Not reviewed yet.", small))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Important", h2))
    story.append(Paragraph(DISCLAIMER, body))
    if data.generated_by:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Generated by {data.generated_by}.", small))
    if data.app_url:
        story.append(Paragraph(f"Online record: {data.app_url}", mono))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
