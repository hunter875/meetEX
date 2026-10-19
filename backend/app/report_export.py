"""Markdown presentation of immutable report/evidence snapshots."""

import json
from . import meeting_memory
from .service import SECTIONS


def markdown_report(report, language="vi"):
    p = report["payload"]
    lines = [
        f"# Meet Copilot · Report v{report['version']}",
        f"Mode: {report['mode']} · Draft/reviewed: {report['reviewed_at'] or 'draft'}",
        p["summary_en" if language == "en" else "summary_vi"],
        "Summary evidence: " + ", ".join(p.get("summary_segment_ids", [])),
    ]
    headings = dict(
        requirements="Yêu cầu",
        decisions="Quyết định đã xác nhận",
        action_items="Action items",
        open_questions="Câu hỏi bỏ ngỏ",
        ai_proposals="Đề xuất phương án (AI/user edit)",
    )
    for section in SECTIONS:
        lines += ["", f"## {headings[section]}"]
        for item in p[section]:
            lines.append(
                "- "
                + (item.get("text_en") or item["text"] if language == "en" else item["text"])
                + f" [{item['origin']}; {item['confirmation']}]"
            )
            if section == "action_items":
                lines.append(
                    f"  Owner: {item['owner'] or 'Chưa xác nhận'}; Due: {item['normalized_due'] or item['raw_due_text'] or 'Chưa xác nhận'}; Status: {item['status']}"
                )
            lines.append("  Evidence: " + ", ".join(item["evidence_segment_ids"]))
    if report.get("memory_snapshot"):
        lines += ["", "## Bộ nhớ tại thời điểm tạo báo cáo (tách khỏi chỉnh sửa của bạn)"]
        for item in report["memory_snapshot"]:
            label = "Hiện hành" if meeting_memory.current(item) else "Lịch sử"
            lines.append(
                f"- [{label}; {item['kind']}; {item['status']}; {item['origin']}; v{item['version']}] "
                + item["text"]
            )
            lines.append(
                f"  Owner: {item.get('owner') or 'Chưa xác nhận'}; Due raw: {item.get('raw_due_text') or '—'}; normalized: {item.get('normalized_due') or '—'}; rule: {item.get('due_rule')}"
            )
            lines.append(
                "  Evidence revisions: "
                + ", ".join(f"{e['segment_id']}@r{e['revision']}" for e in item["evidence"])
            )
            if item["relations"]:
                lines.append("  Relations: " + json.dumps(item["relations"], ensure_ascii=False))
    if report.get("historical_payload"):
        lines += ["", "## Lịch sử đã tách khỏi trạng thái hiện hành"]
        for section in SECTIONS:
            for item in report["historical_payload"][section]:
                lines.append(
                    "- [history; "
                    + item["origin"]
                    + "] "
                    + item["text"]
                    + " · Evidence: "
                    + ", ".join(item["evidence_segment_ids"])
                )
    if report.get("edit_provenance"):
        lines += [
            "",
            "User edit provenance: " + json.dumps(report["edit_provenance"], ensure_ascii=False),
        ]
    if report.get("evidence_changed"):
        lines += ["", "WARNING: Evidence/memory changed since this immutable report snapshot."]
    lines += ["", "## Cảnh báo"] + ["- " + w for w in p["capture_warnings"]]
    return "\n".join(lines)
