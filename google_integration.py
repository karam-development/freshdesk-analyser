"""Google Workspace integration: Drive, Sheets, Docs, Slides.

Uses a service-account JSON key stored in the database (settings table).
All exports are created inside a user-configured shared Drive folder.
"""

import io
import json
import logging
import os
import re
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations",
]


# ── Credential helpers ──────────────────────────────────────────────────────

def _get_credentials(sa_json: str):
    """Build credentials from service-account JSON string."""
    info = json.loads(sa_json)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def _drive_service(creds):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _sheets_service(creds):
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _docs_service(creds):
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def _slides_service(creds):
    return build("slides", "v1", credentials=creds, cache_discovery=False)


# ── Connection test ─────────────────────────────────────────────────────────

def test_connection(sa_json: str, folder_id: str = "") -> dict:
    """Validate service-account key and optionally check folder access.
    Returns {"ok": True/False, "email": ..., "folder_name": ..., "error": ...}
    """
    try:
        creds = _get_credentials(sa_json)
        drive = _drive_service(creds)
        # Verify the key works by listing a single file
        about = drive.about().get(fields="user").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")
        result = {"ok": True, "email": email, "folder_name": "", "error": ""}

        if folder_id:
            try:
                meta = drive.files().get(fileId=folder_id, fields="name,mimeType").execute()
                result["folder_name"] = meta.get("name", "")
                if meta.get("mimeType") != "application/vnd.google-apps.folder":
                    result["ok"] = False
                    result["error"] = f"ID '{folder_id}' is not a folder (type: {meta.get('mimeType')})"
            except Exception as e:
                result["ok"] = False
                result["error"] = f"Cannot access folder: {e}"
        return result
    except Exception as e:
        return {"ok": False, "email": "", "folder_name": "", "error": str(e)}


# ── Google Sheets export ────────────────────────────────────────────────────

def export_report_to_sheets(sa_json: str, folder_id: str, data: dict, sections: list) -> str:
    """Create a Google Sheet with reporting data. Returns the sheet URL."""
    creds = _get_credentials(sa_json)
    sheets = _sheets_service(creds)
    drive = _drive_service(creds)

    today = datetime.now().strftime("%Y-%m-%d")
    title = f"BSO LUX Report — {today}"

    # Create spreadsheet
    spreadsheet = sheets.spreadsheets().create(body={
        "properties": {"title": title},
        "sheets": []
    }).execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]

    # Move to folder
    if folder_id:
        drive.files().update(
            fileId=spreadsheet_id,
            addParents=folder_id,
            removeParents="root",
            fields="id,parents"
        ).execute()

    sheet_requests = []
    sheet_data = []
    sheet_index = 0

    def add_sheet(name, rows):
        nonlocal sheet_index
        if sheet_index == 0:
            # Rename default Sheet1
            sheet_requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": 0, "title": name},
                    "fields": "title"
                }
            })
            sid = 0
        else:
            sid = sheet_index
            sheet_requests.append({
                "addSheet": {"properties": {"sheetId": sid, "title": name}}
            })
        sheet_data.append({"range": f"'{name}'!A1", "values": rows})
        sheet_index += 1

    # ── KPI Summary ──
    if "kpi_cards" in sections:
        add_sheet("KPI Summary", [
            ["Metric", "Value"],
            ["Total Tickets", data["total"]],
            ["Open / In Progress", data["open_count"]],
            ["Resolved / Closed", data["resolved_count"]],
            ["Avg Resolution (days)", data["avg_resolution_days"]],
            ["Avg RICE Score", data["avg_rice"]],
            ["Avg First Response (h)", data["avg_first_response_hours"]],
            ["SLA Resolution %", data["sla_resolution_pct"]],
            ["First Response SLA %", data["sla_response_pct"]],
            ["Tickets This Week", data["tickets_this_week"]],
        ])

    # ── Distribution sheets ──
    dist_map = {
        "status_chart": ("Status Distribution", "status_dist", "status"),
        "classification_chart": ("Classification", "class_dist", "classification"),
        "risk_chart": ("Risk Levels", "risk_dist", "risk_level"),
        "po_decisions": ("PO Decisions", "po_dist", "po_decision"),
    }
    for sec_key, (name, data_key, col_key) in dist_map.items():
        if sec_key in sections and data.get(data_key):
            rows = [[col_key.replace("_", " ").title(), "Count"]]
            for item in data[data_key]:
                rows.append([item.get(col_key, "N/A"), item.get("count", 0)])
            add_sheet(name, rows)

    # ── Bucket distributions ──
    bucket_map = {
        "resolution_time": ("Resolution Time", "res_buckets"),
        "first_response": ("First Response", "first_response_buckets"),
        "rice_chart": ("RICE Buckets", "rice_buckets"),
    }
    for sec_key, (name, data_key) in bucket_map.items():
        if sec_key in sections and data.get(data_key):
            rows = [["Bucket", "Count"]]
            for bucket, count in data[data_key].items():
                rows.append([bucket, count])
            add_sheet(name, rows)

    # ── Templates / Workflows ──
    if "templates" in sections and data.get("template_breakdown"):
        rows = [["Template", "Count"]]
        for t in data["template_breakdown"]:
            rows.append([t[0], t[1]])
        add_sheet("Templates", rows)

    if "workflows" in sections and data.get("workflow_breakdown"):
        rows = [["Workflow", "Count"]]
        for w in data["workflow_breakdown"]:
            rows.append([w[0], w[1]])
        add_sheet("Workflows", rows)

    # ── Timeline ──
    if "timeline" in sections and data.get("monthly"):
        rows = [["Month", "Count"]]
        for m in data["monthly"]:
            rows.append([m["month"], m["count"]])
        add_sheet("Timeline", rows)

    # ── Client Breakdown ──
    if "client_breakdown" in sections and data.get("client_breakdown"):
        total = data["total"] or 1
        rows = [["Rank", "Client", "Tickets", "Share %"]]
        for i, (name, count) in enumerate(data["client_breakdown"]):
            rows.append([i + 1, name, count, round(100 * count / total, 1)])
        add_sheet("Clients", rows)

    # ── SLA Compliance ──
    if "sla_compliance" in sections:
        add_sheet("SLA Compliance", [
            ["SLA Target", "Threshold", "Actual", "Status"],
            ["Resolution within 7 days", "80%", f"{data['sla_resolution_pct']}%",
             "PASS" if data["sla_resolution_pct"] >= 80 else "FAIL"],
            ["First response within 24h", "80%", f"{data['sla_response_pct']}%",
             "PASS" if data["sla_response_pct"] >= 80 else "FAIL"],
        ])

    # Apply batch
    if sheet_requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": sheet_requests}
        ).execute()

    if sheet_data:
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": sheet_data}
        ).execute()

    # ── Bold headers + auto-resize ──
    format_requests = []
    for i in range(sheet_index):
        sid = 0 if i == 0 else i
        format_requests.append({
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.314, "green": 0.275, "blue": 0.898, "alpha": 1},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)"
            }
        })
        format_requests.append({
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 10}
            }
        })

    if format_requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": format_requests}
        ).execute()

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def export_tickets_to_sheets(sa_json: str, folder_id: str, tickets: list) -> str:
    """Create a Google Sheet with all ticket data. Returns the sheet URL."""
    creds = _get_credentials(sa_json)
    sheets = _sheets_service(creds)
    drive = _drive_service(creds)

    today = datetime.now().strftime("%Y-%m-%d")
    title = f"BSO LUX Tickets — {today}"

    spreadsheet = sheets.spreadsheets().create(body={
        "properties": {"title": title},
        "sheets": [{"properties": {"title": "Tickets"}}]
    }).execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]

    if folder_id:
        drive.files().update(
            fileId=spreadsheet_id, addParents=folder_id, removeParents="root", fields="id,parents"
        ).execute()

    headers = ["ID", "Subject", "Requester", "Client", "Status", "Classification",
               "Risk Level", "RICE Score", "PO Decision", "Template", "Workflow",
               "Created At", "Resolved At", "SLA Resolution (h)", "SLA First Response (h)"]

    rows = [headers]
    for t in tickets:
        rows.append([
            t.get("freshdesk_id", ""), t.get("subject", ""), t.get("requester_name", ""),
            t.get("requester_email", "").split("@")[1].split(".")[0] if "@" in t.get("requester_email", "") else "",
            t.get("status", ""), t.get("classification", ""), t.get("risk_level", ""),
            t.get("rice_score", ""), t.get("po_decision", ""),
            t.get("template_name", ""), t.get("workflow_name", ""),
            t.get("created_at", ""), t.get("resolved_at", ""),
            t.get("sla_resolution_hours", ""), t.get("sla_first_response_hours", ""),
        ])

    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Tickets!A1",
        valueInputOption="USER_ENTERED", body={"values": rows}
    ).execute()

    # Format header
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [
            {
                "repeatCell": {
                    "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.314, "green": 0.275, "blue": 0.898},
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }},
                    "fields": "userEnteredFormat(textFormat,backgroundColor)"
                }
            },
            {"autoResizeDimensions": {
                "dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 15}
            }},
            {"setBasicFilter": {
                "filter": {"range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": len(rows),
                                     "startColumnIndex": 0, "endColumnIndex": 15}}
            }},
        ]}
    ).execute()

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


# ── Google Docs export ──────────────────────────────────────────────────────

def export_analysis_to_docs(sa_json: str, folder_id: str, ticket: dict) -> str:
    """Create a Google Doc with the full ticket analysis. Returns the doc URL."""
    creds = _get_credentials(sa_json)
    docs = _docs_service(creds)
    drive = _drive_service(creds)

    subject = ticket.get("subject", "Ticket")[:80]
    fid = ticket.get("freshdesk_id", "")
    title = f"Analysis — #{fid} — {subject}"

    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    if folder_id:
        drive.files().update(
            fileId=doc_id, addParents=folder_id, removeParents="root", fields="id,parents"
        ).execute()

    # Build document content as batch requests
    requests = []
    idx = 1  # cursor position

    def insert_text(text, bold=False, font_size=None, color=None):
        nonlocal idx
        requests.append({"insertText": {"location": {"index": idx}, "text": text}})
        end = idx + len(text)
        style = {}
        if bold:
            style["bold"] = True
        if font_size:
            style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
        if color:
            r, g, b = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
            style["foregroundColor"] = {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}
        if style:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": idx, "endIndex": end},
                    "textStyle": style,
                    "fields": ",".join(style.keys())
                }
            })
        idx = end

    def insert_heading(text, level=1):
        nonlocal idx
        requests.append({"insertText": {"location": {"index": idx}, "text": text + "\n"}})
        end = idx + len(text) + 1
        heading = "HEADING_1" if level == 1 else "HEADING_2" if level == 2 else "HEADING_3"
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": idx, "endIndex": end},
                "paragraphStyle": {"namedStyleType": heading},
                "fields": "namedStyleType"
            }
        })
        idx = end

    def insert_para(text):
        nonlocal idx
        requests.append({"insertText": {"location": {"index": idx}, "text": text + "\n"}})
        idx += len(text) + 1

    # ── Title area ──
    insert_heading(f"Ticket #{fid} — {subject}", 1)
    insert_para("")

    # ── Metadata table ──
    meta_lines = [
        f"Requester: {ticket.get('requester_name', 'N/A')} ({ticket.get('requester_email', '')})",
        f"Status: {ticket.get('status', 'N/A')}",
        f"Classification: {ticket.get('classification', 'N/A')}",
        f"Risk Level: {ticket.get('risk_level', 'N/A')}",
        f"RICE Score: {ticket.get('rice_score', 'N/A')}",
        f"PO Decision: {ticket.get('po_decision', 'N/A')}",
        f"Template: {ticket.get('template_name', 'N/A')}",
        f"Workflow: {ticket.get('workflow_name', 'N/A')}",
        f"Created: {ticket.get('created_at', '')}",
        f"Resolved: {ticket.get('resolved_at', 'N/A')}",
    ]
    insert_heading("Ticket Details", 2)
    for line in meta_lines:
        insert_para(line)
    insert_para("")

    # ── AI Analysis ──
    analysis = ticket.get("analysis_text", "") or ticket.get("analysis", "")
    if analysis:
        insert_heading("AI Analysis", 2)
        # Split analysis into paragraphs
        for para in analysis.split("\n"):
            if para.strip():
                insert_para(para.strip())
        insert_para("")

    # ── Summary ──
    summary = ticket.get("summary", "")
    if summary:
        insert_heading("Summary", 2)
        insert_para(summary)
        insert_para("")

    # ── Draft Response ──
    for lang_suffix, lang_name in [("_fr", "French"), ("_en", "English")]:
        draft = ticket.get(f"draft_response{lang_suffix}", "")
        if draft:
            insert_heading(f"Draft Response ({lang_name})", 2)
            for para in draft.split("\n"):
                if para.strip():
                    insert_para(para.strip())
            insert_para("")

    # ── RICE Breakdown ──
    rice = ticket.get("rice_score", 0)
    if rice:
        insert_heading("RICE Score Breakdown", 2)
        insert_para(f"Overall RICE Score: {rice}")
        rice_details = ticket.get("rice_details", "")
        if rice_details:
            for line in rice_details.split("\n"):
                if line.strip():
                    insert_para(line.strip())

    # Execute batch
    if requests:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

    return f"https://docs.google.com/document/d/{doc_id}/edit"


# ── Google Slides export ────────────────────────────────────────────────────

def export_report_to_slides(sa_json: str, folder_id: str, data: dict, sections: list) -> str:
    """Create a Google Slides presentation with report data. Returns the slides URL."""
    creds = _get_credentials(sa_json)
    slides = _slides_service(creds)
    drive = _drive_service(creds)

    today = datetime.now().strftime("%B %d, %Y")
    title = f"BSO LUX — Support Analytics Report"

    pres = slides.presentations().create(body={"title": title}).execute()
    pres_id = pres["presentationId"]

    if folder_id:
        drive.files().update(
            fileId=pres_id, addParents=folder_id, removeParents="root", fields="id,parents"
        ).execute()

    requests = []

    # Colors
    PRIMARY = {"red": 0.314, "green": 0.275, "blue": 0.898}
    DARK = {"red": 0.118, "green": 0.161, "blue": 0.231}
    WHITE = {"red": 1, "green": 1, "blue": 1}
    ACCENT = {"red": 0.063, "green": 0.725, "blue": 0.506}  # green

    # ── Delete default blank slide ──
    default_slides = pres.get("slides", [])
    if default_slides:
        requests.append({"deleteObject": {"objectId": default_slides[0]["objectId"]}})

    slide_num = 0

    def create_slide(layout="BLANK"):
        nonlocal slide_num
        oid = f"slide_{slide_num}"
        requests.append({"createSlide": {
            "objectId": oid,
            "slideLayoutReference": {"predefinedLayout": layout},
            "insertionIndex": slide_num,
        }})
        slide_num += 1
        return oid

    def add_textbox(slide_id, text, left, top, width, height,
                    font_size=14, bold=False, color=None, alignment="START", box_id=None):
        oid = box_id or f"tb_{slide_num}_{left}_{top}"
        requests.append({"createShape": {
            "objectId": oid,
            "shapeType": "TEXT_BOX",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": width, "unit": "EMU"},
                    "height": {"magnitude": height, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1, "translateX": left, "translateY": top, "unit": "EMU"
                }
            }
        }})
        requests.append({"insertText": {"objectId": oid, "text": text, "insertionIndex": 0}})
        style = {"fontSize": {"magnitude": font_size, "unit": "PT"}, "bold": bold}
        if color:
            style["foregroundColor"] = {"opaqueColor": {"rgbColor": color}}
        requests.append({"updateTextStyle": {
            "objectId": oid,
            "style": style,
            "fields": "fontSize,bold,foregroundColor",
        }})
        requests.append({"updateParagraphStyle": {
            "objectId": oid,
            "style": {"alignment": alignment},
            "fields": "alignment",
        }})
        return oid

    def add_rect(slide_id, left, top, width, height, fill_color, rect_id=None):
        oid = rect_id or f"rect_{slide_num}_{left}_{top}"
        requests.append({"createShape": {
            "objectId": oid,
            "shapeType": "RECTANGLE",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": width, "unit": "EMU"},
                    "height": {"magnitude": height, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1, "translateX": left, "translateY": top, "unit": "EMU"
                }
            }
        }})
        requests.append({"updateShapeProperties": {
            "objectId": oid,
            "shapeProperties": {
                "shapeBackgroundFill": {
                    "solidFill": {"color": {"rgbColor": fill_color}}
                },
                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": fill_color}}}}
            },
            "fields": "shapeBackgroundFill,outline"
        }})
        return oid

    EMU = 914400  # 1 inch in EMU
    SLIDE_W = int(10 * EMU)
    SLIDE_H = int(5.625 * EMU)

    # ── Slide 1: Title ──
    s = create_slide()
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, DARK, rect_id="title_bg")
    add_rect(s, 0, int(4.3 * EMU), SLIDE_W, int(0.08 * EMU), PRIMARY, rect_id="title_accent")
    add_textbox(s, "BSO LUX", int(0.8 * EMU), int(1.2 * EMU), int(8.4 * EMU), int(0.8 * EMU),
                font_size=40, bold=True, color=WHITE, box_id="title_main")
    add_textbox(s, "Support Analytics Report", int(0.8 * EMU), int(2.0 * EMU), int(8.4 * EMU), int(0.6 * EMU),
                font_size=24, color=PRIMARY, box_id="title_sub")
    add_textbox(s, today, int(0.8 * EMU), int(3.0 * EMU), int(8.4 * EMU), int(0.4 * EMU),
                font_size=14, color=WHITE, box_id="title_date")

    # ── Slide 2: KPI Cards ──
    if "kpi_cards" in sections:
        s = create_slide()
        add_textbox(s, "Key Performance Indicators", int(0.5 * EMU), int(0.3 * EMU),
                    int(9 * EMU), int(0.6 * EMU), font_size=24, bold=True, color=DARK, box_id="kpi_title")

        kpis = [
            ("Total Tickets", str(data["total"])),
            ("Open", str(data["open_count"])),
            ("Resolved", str(data["resolved_count"])),
            ("Avg Resolution", f"{data['avg_resolution_days']}d"),
            ("Avg RICE", str(data["avg_rice"])),
            ("Avg 1st Response", f"{data['avg_first_response_hours']}h"),
            ("SLA Resolution", f"{data['sla_resolution_pct']}%"),
            ("SLA Response", f"{data['sla_response_pct']}%"),
            ("This Week", str(data["tickets_this_week"])),
        ]

        cols = 3
        card_w = int(2.7 * EMU)
        card_h = int(1.2 * EMU)
        gap = int(0.3 * EMU)
        start_x = int(0.5 * EMU)
        start_y = int(1.2 * EMU)

        for i, (label, value) in enumerate(kpis):
            col = i % cols
            row = i // cols
            x = start_x + col * (card_w + gap)
            y = start_y + row * (card_h + gap)
            cid = f"kpi_card_{i}"
            add_rect(s, x, y, card_w, card_h, {"red": 0.97, "green": 0.97, "blue": 0.98}, rect_id=cid)
            add_rect(s, x, y, int(0.06 * EMU), card_h, PRIMARY, rect_id=f"kpi_bar_{i}")
            add_textbox(s, value, x + int(0.2 * EMU), y + int(0.15 * EMU), card_w - int(0.3 * EMU),
                        int(0.6 * EMU), font_size=28, bold=True, color=DARK, box_id=f"kpi_val_{i}")
            add_textbox(s, label, x + int(0.2 * EMU), y + int(0.7 * EMU), card_w - int(0.3 * EMU),
                        int(0.4 * EMU), font_size=11, color={"red": 0.4, "green": 0.45, "blue": 0.55},
                        box_id=f"kpi_lbl_{i}")

    # ── Distribution slides ──
    dist_sections = {
        "status_chart": ("Ticket Status Distribution", "status_dist", "status"),
        "classification_chart": ("Classification Breakdown", "class_dist", "classification"),
        "risk_chart": ("Risk Level Distribution", "risk_dist", "risk_level"),
        "po_decisions": ("PO Decisions", "po_dist", "po_decision"),
    }

    for sec_key, (slide_title, data_key, col_key) in dist_sections.items():
        if sec_key in sections and data.get(data_key):
            s = create_slide()
            add_textbox(s, slide_title, int(0.5 * EMU), int(0.3 * EMU),
                        int(9 * EMU), int(0.6 * EMU), font_size=24, bold=True, color=DARK,
                        box_id=f"dist_title_{sec_key}")

            items = data[data_key]
            total_count = sum(it.get("count", 0) for it in items) or 1
            y_pos = int(1.3 * EMU)
            for j, item in enumerate(items[:8]):
                name = item.get(col_key, "N/A") or "N/A"
                count = item.get("count", 0)
                pct = round(100 * count / total_count, 1)
                bar_width = max(int(6 * EMU * count / total_count), int(0.3 * EMU))

                add_textbox(s, f"{name}", int(0.5 * EMU), y_pos,
                            int(3 * EMU), int(0.4 * EMU), font_size=12, color=DARK,
                            box_id=f"dist_lbl_{sec_key}_{j}")
                add_rect(s, int(3.8 * EMU), y_pos + int(0.05 * EMU), bar_width, int(0.3 * EMU),
                         PRIMARY, rect_id=f"dist_bar_{sec_key}_{j}")
                add_textbox(s, f"{count} ({pct}%)", int(3.8 * EMU) + bar_width + int(0.1 * EMU), y_pos,
                            int(2 * EMU), int(0.4 * EMU), font_size=11, color=DARK,
                            box_id=f"dist_val_{sec_key}_{j}")
                y_pos += int(0.5 * EMU)

    # ── SLA Compliance slide ──
    if "sla_compliance" in sections:
        s = create_slide()
        add_textbox(s, "SLA Compliance", int(0.5 * EMU), int(0.3 * EMU),
                    int(9 * EMU), int(0.6 * EMU), font_size=24, bold=True, color=DARK, box_id="sla_title")

        res_pass = data["sla_resolution_pct"] >= 80
        resp_pass = data["sla_response_pct"] >= 80

        for i, (label, pct, passed) in enumerate([
            ("Resolution within 7 days", data["sla_resolution_pct"], res_pass),
            ("First response within 24h", data["sla_response_pct"], resp_pass),
        ]):
            x = int(0.8 * EMU) + i * int(4.5 * EMU)
            fill = ACCENT if passed else {"red": 0.937, "green": 0.267, "blue": 0.267}
            add_rect(s, x, int(1.5 * EMU), int(3.8 * EMU), int(2.8 * EMU), fill, rect_id=f"sla_card_{i}")
            add_textbox(s, f"{pct}%", x + int(0.3 * EMU), int(1.8 * EMU),
                        int(3.2 * EMU), int(1.2 * EMU), font_size=48, bold=True, color=WHITE,
                        alignment="CENTER", box_id=f"sla_pct_{i}")
            add_textbox(s, label, x + int(0.3 * EMU), int(3.2 * EMU),
                        int(3.2 * EMU), int(0.6 * EMU), font_size=14, color=WHITE,
                        alignment="CENTER", box_id=f"sla_lbl_{i}")
            status_text = "PASS ✓" if passed else "NEEDS IMPROVEMENT"
            add_textbox(s, status_text, x + int(0.3 * EMU), int(3.8 * EMU),
                        int(3.2 * EMU), int(0.4 * EMU), font_size=12, bold=True, color=WHITE,
                        alignment="CENTER", box_id=f"sla_status_{i}")

    # ── Thank you slide ──
    s = create_slide()
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, DARK, rect_id="end_bg")
    add_textbox(s, "Thank You", int(1 * EMU), int(1.8 * EMU), int(8 * EMU), int(1 * EMU),
                font_size=40, bold=True, color=WHITE, alignment="CENTER", box_id="end_title")
    add_textbox(s, f"BSO Luxembourg — Support Analytics\n{today}",
                int(1 * EMU), int(3.0 * EMU), int(8 * EMU), int(0.8 * EMU),
                font_size=16, color=PRIMARY, alignment="CENTER", box_id="end_sub")

    # Execute all requests
    if requests:
        slides.presentations().batchUpdate(presentationId=pres_id, body={"requests": requests}).execute()

    return f"https://docs.google.com/presentation/d/{pres_id}/edit"


# ── Google Drive KB (Knowledge Base) ────────────────────────────────────────

def list_drive_kb_files(sa_json: str, folder_id: str, max_results: int = 50) -> list:
    """List files in a Drive folder that can be used as knowledge base.
    Returns [{"id": ..., "name": ..., "mimeType": ..., "modifiedTime": ...}, ...]
    """
    creds = _get_credentials(sa_json)
    drive = _drive_service(creds)

    supported_types = [
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]

    query = f"'{folder_id}' in parents and trashed=false"
    results = drive.files().list(
        q=query,
        fields="files(id,name,mimeType,modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=max_results,
    ).execute()

    files = results.get("files", [])
    return [f for f in files if f.get("mimeType") in supported_types]


def read_drive_file_content(sa_json: str, file_id: str, mime_type: str) -> str:
    """Read text content from a Drive file. Supports Google Docs, Sheets, plain text, etc."""
    creds = _get_credentials(sa_json)
    drive = _drive_service(creds)

    try:
        if mime_type == "application/vnd.google-apps.document":
            content = drive.files().export(fileId=file_id, mimeType="text/plain").execute()
            return content.decode("utf-8") if isinstance(content, bytes) else content

        elif mime_type == "application/vnd.google-apps.spreadsheet":
            content = drive.files().export(fileId=file_id, mimeType="text/csv").execute()
            return content.decode("utf-8") if isinstance(content, bytes) else content

        elif mime_type in ("text/plain", "text/csv"):
            content = drive.files().get_media(fileId=file_id).execute()
            return content.decode("utf-8") if isinstance(content, bytes) else content

        elif mime_type == "application/pdf":
            # For PDFs, we can't extract text via Drive API directly
            return f"[PDF file — content extraction not supported via Drive API. File ID: {file_id}]"

        else:
            return f"[Unsupported file type: {mime_type}]"
    except Exception as e:
        log.error(f"Error reading Drive file {file_id}: {e}")
        return f"[Error reading file: {e}]"


def get_kb_context_from_drive(sa_json: str, folder_id: str, query_hint: str = "",
                              max_files: int = 10, max_chars: int = 15000) -> str:
    """Scan Drive KB folder and return concatenated text content for AI context.

    Args:
        query_hint: optional text (e.g. ticket subject) to prioritize relevant files
        max_files: max number of files to read
        max_chars: max total characters to return
    """
    files = list_drive_kb_files(sa_json, folder_id, max_results=30)
    if not files:
        return ""

    # If we have a query hint, try to prioritize files whose name matches
    if query_hint:
        hint_lower = query_hint.lower()
        hint_words = set(re.findall(r'\w+', hint_lower))

        def relevance(f):
            name_lower = f["name"].lower()
            # Count matching words
            name_words = set(re.findall(r'\w+', name_lower))
            return len(hint_words & name_words)

        files.sort(key=relevance, reverse=True)

    context_parts = []
    total_chars = 0

    for f in files[:max_files]:
        if total_chars >= max_chars:
            break
        content = read_drive_file_content(sa_json, f["id"], f["mimeType"])
        if content and not content.startswith("["):
            # Truncate individual file if needed
            remaining = max_chars - total_chars
            if len(content) > remaining:
                content = content[:remaining] + "\n... [truncated]"
            context_parts.append(f"=== {f['name']} ===\n{content}")
            total_chars += len(content)

    return "\n\n".join(context_parts)
