"""Timed synthetic HTTP/WS/Provider-adapter soak, isolated from personal data.

Default plan: 60 minutes, one caption/2 seconds, recycle every 60 turns,
RSS <=768 MiB and temporary DB/WAL <=256 MiB. No browser or real model here.
"""

import argparse
import asyncio
import ctypes
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def rss_bytes():
    if os.name != "nt":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError("RSS measurement failed")
    return counters.WorkingSetSize


def main():
    from app.config import Config
    from app.llm import demo_report
    from app.main import create_app
    from app.storage import now, uid

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/soak-phase5.json")
    args = parser.parse_args()
    started = time.monotonic()
    output = dict(
        plan=dict(
            seconds=args.seconds,
            interval=args.interval,
            rss_limit_mib=768,
            disk_limit_mib=256,
            recycle_turns=60,
        ),
        environment=dict(os=platform.platform(), python=platform.python_version()),
        started_at=datetime.now(timezone.utc).isoformat(),
        paid_calls=0,
        browser="NOT TESTED by this harness",
        samples=[],
        active_samples=[],
        request_outcomes={},
        request_error_codes={},
        source_hashes={
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_text("utf8").encode()).hexdigest()
            for p in sorted((ROOT / "backend/app").glob("*.py"))
        },
        captions=0,
        reconnects=0,
        reports=0,
        report_maps=0,
        suggestions=0,
        provider_attempts=0,
        provider_faults={},
        errors=[],
        status="RUNNING",
    )
    attempts = 0

    async def controlled(request):
        nonlocal attempts
        attempts += 1
        wire = json.loads(json.loads(request.content)["messages"][1]["content"])
        if wire.get("task", "").startswith("report"):
            payload = demo_report(wire["segments"]).model_dump()
            output["report_maps"] += 1
        else:
            # Controlled transport exercises real retry, auth and timeout paths, never network.
            if attempts % 37 == 0:
                output["provider_faults"]["401"] = output["provider_faults"].get("401", 0) + 1
                return httpx.Response(401)
            if attempts % 13 == 0:
                output["provider_faults"]["429"] = output["provider_faults"].get("429", 0) + 1
                return httpx.Response(429)
            if attempts % 11 == 0:
                output["provider_faults"]["slow_timeout"] = (
                    output["provider_faults"].get("slow_timeout", 0) + 1
                )
                await asyncio.sleep(0.5)
            payload = dict(
                input_revision=wire["transcript_revision"],
                intent="question",
                meaning_vi="Cần làm rõ.",
                findings=[],
                reply_en="Could you clarify the next step?",
                reply_vi="Bạn làm rõ bước tiếp theo được không?",
                clarification_en="",
                evidence_status="missing",
                uncertainties=[],
                supporting_segment_ids=[wire["segments"][-1]["id"]],
            )
        return httpx.Response(
            200,
            content="data: "
            + json.dumps({"choices": [{"delta": {"content": json.dumps(payload)}}]})
            + "\n\ndata: [DONE]\n\n",
        )

    def save():
        output["elapsed_s"] = round(time.monotonic() - started, 3)
        output["provider_attempts"] = attempts
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2), encoding="utf8")

    ack_ms = []
    with tempfile.TemporaryDirectory(prefix="meet soak synthetic ") as temporary:
        directory = Path(temporary)
        config = Config(
            directory,
            "FAKE_SOAK_PAIRING",
            ("chrome-extension://" + "a" * 32,),
            api_key="FAKE_SOAK_PROVIDER",
        )
        application = create_app(config)
        try:
            with TestClient(
                application,
                base_url="http://127.0.0.1:8765",
                headers={"Authorization": "Bearer " + config.token},
            ) as client:
                application.state.provider.transport = httpx.MockTransport(controlled)
                store = application.state.store
                store.set_settings(dict(auto_mode=False, live_timeout_s=0.3, report_timeout_s=2))

                def call(path, method="GET", body=None):
                    response = client.request(method, path, json=body)
                    if not response.is_success:
                        raise RuntimeError(
                            f"HTTP {response.status_code} at operation {method} {path.split('/')[3]}"
                        )
                    return response.json()

                while time.monotonic() - started < args.seconds:
                    project = call(
                        "/api/v1/projects",
                        "POST",
                        dict(name="SYNTHETIC SOAK", description="", glossary={}),
                    )
                    source = call(
                        f"/api/v1/projects/{project['id']}/sources",
                        "POST",
                        dict(
                            kind="text",
                            title="Synthetic notes",
                            pasted_text="Discussion needs clarification.",
                        ),
                    )
                    call(f"/api/v1/sources/{source['source_id']}/reindex", "POST")
                    call(
                        f"/api/v1/projects/{project['id']}/search",
                        "POST",
                        dict(query="clarification"),
                    )
                    meeting = call(
                        "/api/v1/meetings",
                        "POST",
                        dict(
                            project_id=project["id"],
                            title="SYNTHETIC",
                            timezone="UTC",
                            persistence_mode="local",
                            demo=False,
                            meeting_key="/soak",
                        ),
                    )
                    mid = meeting["id"]
                    turns = 0
                    while turns < 60 and time.monotonic() - started < args.seconds:
                        with client.websocket_connect(
                            "/api/v1/events",
                            headers={"Origin": config.origins[0], "Host": "127.0.0.1:8765"},
                        ) as ws:
                            ws.send_json(dict(type="auth", protocol_version=1, token=config.token))
                            assert ws.receive_json()["type"] == "auth.ok"
                            ws.send_json(
                                dict(
                                    type="session.bind",
                                    protocol_version=1,
                                    session_id=mid,
                                    payload=dict(tab_id=1, document_id="soak", meeting_key="/soak"),
                                )
                            )
                            assert ws.receive_json()["type"] == "session.snapshot"
                            output["reconnects"] += 1
                            # Reconnect each 10 turns; no Chrome panel is simulated by this loop.
                            for _ in range(10):
                                if turns >= 60 or time.monotonic() - started >= args.seconds:
                                    break
                                event = dict(
                                    type="caption.upsert",
                                    protocol_version=1,
                                    event_id=uid(),
                                    capture_epoch="soak",
                                    segment_id=uid(),
                                    revision=1,
                                    seq=turns + 1,
                                    speaker_label="Client",
                                    text="Could you clarify the next step? "
                                    + "Background discussion remains open. " * 17,
                                    observed_at=now(),
                                    stable=True,
                                    adapter_version="synthetic-soak",
                                )
                                before = time.perf_counter()
                                ws.send_json(
                                    dict(
                                        type="caption.upsert",
                                        protocol_version=1,
                                        session_id=mid,
                                        payload=event,
                                    )
                                )
                                while True:
                                    envelope = ws.receive_json()
                                    if envelope["type"] == "caption.ack":
                                        assert (
                                            envelope["event_id"] == event["event_id"]
                                            and envelope["applied"]
                                        )
                                        break
                                ack_ms.append((time.perf_counter() - before) * 1000)
                                turns += 1
                                output["captions"] += 1
                                if turns % 7 == 0:
                                    call(
                                        f"/api/v1/meetings/{mid}/suggest",
                                        "POST",
                                        dict(action="suggest"),
                                    )
                                    output["suggestions"] += 1
                                    service = application.state.service
                                    output["active_samples"].append(
                                        dict(
                                            elapsed_s=round(time.monotonic() - started, 2),
                                            rss_bytes=rss_bytes(),
                                            active=len(service.active),
                                            queued=len(service.queued),
                                            tasks=len(service.tasks),
                                            auto_timers=len(service.auto_timers),
                                            listeners=len(service.listeners),
                                            query_cache=len(application.state.retrieval._cache),
                                            query_inflight=len(
                                                application.state.retrieval._inflight
                                            ),
                                        )
                                    )
                                    assert len(service.active) <= 1 and len(service.queued) <= 1
                                time.sleep(
                                    min(
                                        args.interval,
                                        max(0, args.seconds - (time.monotonic() - started)),
                                    )
                                )
                    call(
                        f"/api/v1/meetings/{mid}/control",
                        "POST",
                        dict(action="end", idempotency_key=uid()),
                    )
                    snapshot = call(f"/api/v1/meetings/{mid}")
                    outcomes = Counter(output["request_outcomes"])
                    outcomes.update(r["status"] for r in snapshot["requests"])
                    output["request_outcomes"] = dict(outcomes)
                    errors = Counter(output["request_error_codes"])
                    errors.update(
                        r["error"]["code"] for r in snapshot["requests"] if r.get("error")
                    )
                    output["request_error_codes"] = dict(errors)
                    job = call(
                        f"/api/v1/meetings/{mid}/reports",
                        "POST",
                        dict(transcript_revision=snapshot["transcript_revision"]),
                    )
                    for _ in range(100):
                        status = call(f"/api/v1/jobs/{job['id']}")
                        if status["status"] in ("ready", "error"):
                            break
                        time.sleep(0.05)
                    assert status["status"] == "ready", status.get("error")
                    output["reports"] += 1
                    report = call(f"/api/v1/reports/{status['report_id']}")
                    edited = call(
                        f"/api/v1/reports/{report['id']}",
                        "PATCH",
                        dict(
                            expected_version=report["version"],
                            payload={**report["payload"], "summary_vi": "SYNTHETIC user edit"},
                            reviewed=True,
                        ),
                    )
                    assert edited["version"] == 2 and edited["user_edits"]
                    assert client.get(
                        f"/api/v1/reports/{edited['id']}/export?format=json"
                    ).is_success
                    call(f"/api/v1/projects/{project['id']}", "DELETE")
                    assert not store.meetings() and not store.projects()
                    service = application.state.service
                    sample = dict(
                        elapsed_s=round(time.monotonic() - started, 2),
                        rss_bytes=rss_bytes(),
                        disk_bytes=sum(
                            p.stat().st_size for p in directory.glob("copilot.sqlite3*")
                        ),
                        tasks=len(service.tasks),
                        listeners=len(service.listeners),
                        report_jobs=len(service.report_jobs),
                        query_cache=len(application.state.retrieval._cache),
                        vector_cache=len(application.state.retrieval._vectors),
                        ack_buffer=len(application.state.store.memory_update_timings),
                        captions=output["captions"],
                    )
                    output["samples"].append(sample)
                    assert (
                        sample["rss_bytes"] <= 768 * 1024 * 1024
                        and sample["disk_bytes"] <= 256 * 1024 * 1024
                    )
                    assert (
                        sample["report_jobs"] == 0
                        and sample["query_cache"] == 0
                        and sample["vector_cache"] == 0
                    )
                    save()
            output["shutdown"] = "PASS"
            metrics = application.state.provider.metrics
            output["provider_outcomes"] = dict(Counter(r["status"] for r in metrics))
            output["unknown_usage_attempts"] = sum(r.get("usage") is None for r in metrics)
            output["request_error_fraction"] = sum(
                v for k, v in output["request_outcomes"].items() if k == "error"
            ) / max(1, sum(output["request_outcomes"].values()))
            output["status"] = "PASS" if output["elapsed_s"] >= args.seconds else "SHORT"
        except Exception as error:
            output["status"] = "FAIL"
            output["errors"].append(dict(type=type(error).__name__, message=str(error)[:200]))
        finally:
            output["ack"] = dict(
                n=len(ack_ms),
                median_ms=statistics.median(ack_ms) if ack_ms else None,
                p95_ms=sorted(ack_ms)[int(0.95 * (len(ack_ms) - 1))] if ack_ms else None,
            )
            save()
    print(json.dumps({k: v for k, v in output.items() if k not in ("samples", "errors")}))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
