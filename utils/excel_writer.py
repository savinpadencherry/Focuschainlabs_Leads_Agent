import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment


COLUMNS = [
    "Rank", "Company", "Website", "Location", "Industry",
    "Total Score", "Fit Score", "Trigger Score",
    "Reachability Score", "Recency Score",
    "Primary Signal", "Pain Point", "Score Reasoning",
    "Contact Name", "Contact Title", "Email", "LinkedIn URL",
    "Opening Line", "Source", "Date Found", "Status"
]


def write_leads_to_excel(leads: list, output_path: str) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"

    # Header row
    header_fill = PatternFill("solid", fgColor="1a1a2e")
    header_font = Font(bold=True, color="FFFFFF", size=11)

    for col_idx, col_name in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 22

    # Sort leads by total_score descending
    leads_sorted = sorted(
        leads, key=lambda x: x.get("total_score", 0), reverse=True
    )

    for rank, lead in enumerate(leads_sorted, 1):
        row = rank + 1
        score = lead.get("total_score", 0)

        # Row background colour by score
        if score >= 80:
            fill = PatternFill("solid", fgColor="e8f5e9")  # green
        elif score >= 60:
            fill = PatternFill("solid", fgColor="fff9e6")  # yellow
        else:
            fill = None

        values = [
            rank,
            lead.get("company_name", ""),
            lead.get("website", ""),
            lead.get("locations", ["Bangalore"])[0] if isinstance(
                lead.get("locations"), list) else "Bangalore",
            lead.get("vertical", ""),
            score,
            lead.get("fit_score", ""),
            lead.get("trigger_score", ""),
            lead.get("reachability_score", ""),
            lead.get("intent_recency_score", ""),
            lead.get("primary_signal", ""),
            lead.get("pain_point", ""),
            lead.get("score_reasoning", ""),
            lead.get("contact_name", ""),
            lead.get("contact_title", ""),
            lead.get("email", ""),
            lead.get("linkedin_url", ""),
            lead.get("opening_line", ""),
            lead.get("source", ""),
            lead.get("date_found", ""),
            "New"
        ]

        for col_idx, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col_idx, value=value)
            if fill:
                cell.fill = fill

    # Auto-fit column widths (capped at 60)
    for col in ws.columns:
        max_len = max(
            (len(str(cell.value)) for cell in col if cell.value), default=10
        )
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)
    print(f"  Saved: {output_path}")
    return output_path
