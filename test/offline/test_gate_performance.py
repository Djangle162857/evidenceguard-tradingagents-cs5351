import hashlib
import json
import os
import platform
import statistics
import time

from test_gate_review import NOW, _config, _market_record

from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger
from evidenceguard.gate import validate_artifact

MAX_ENCODED_BYTES = 1048576
SYNTHETIC_RECORDS = 25
SYNTHETIC_CLAIMS = 100
WARMUP_RUNS = 5
SAMPLE_RUNS = 100
P95_LIMIT_MS = 250.0


def measure_gate():
    manifest = create_manifest(_config(), now=NOW)
    ledger = EvidenceLedger(manifest)

    for i in range(SYNTHETIC_RECORDS):
        record = _market_record(content=f"SYNTHETIC market fact {i}")
        record["source_uri"] = f"https://example.test/synthetic/{i}"
        ledger.add(record)

    entries = list(ledger.entries)

    claims = []
    for i in range(SYNTHETIC_CLAIMS):
        evidence_item = entries[i % SYNTHETIC_RECORDS]
        claims.append(
            {
                "claim_id": "cl-" + hashlib.sha256(f"synthetic claim {i}".encode()).hexdigest(),
                "kind": "fact",
                "text": f"Synthetic fact {i}",
                "evidence_ids": [evidence_item.evidence_id],
                "parent_claim_ids": [],
                "uncertainty": "Synthetic only",
            }
        )

    artifact = {
        "schema_version": "1.0",
        "run_id": manifest.run_id,
        "revision": 1,
        "manifest": manifest.to_dict(),
        "evidence": [e.to_dict() for e in entries],
        "claims": claims,
        "report": " ".join(f"[{claim['claim_id']}]" for claim in claims),
        "rating": "Hold",
        "limitations": ["Synthetic benchmark only"],
        "policy_version": "1.0",
        "execution_status": "completed",
        "validation_status": "pending",
        "review_status": "pending",
        "publication_status": "draft",
        "gate_results": {"passed": False, "violations": []},
        "measurement": {},
    }

    encoded = json.dumps(
        artifact,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_bytes = len(encoded)
    assert encoded_bytes <= MAX_ENCODED_BYTES, (
        f"encoded artifact {encoded_bytes} bytes exceeds {MAX_ENCODED_BYTES}"
    )
    assert len(claims) == SYNTHETIC_CLAIMS
    assert len(entries) == SYNTHETIC_RECORDS

    for _ in range(WARMUP_RUNS):
        validate_artifact(artifact, manifest=manifest, ledger=ledger, claims=claims)

    latencies_ms = []
    for _ in range(SAMPLE_RUNS):
        start = time.perf_counter_ns()
        result = validate_artifact(artifact, manifest=manifest, ledger=ledger, claims=claims)
        elapsed_ns = time.perf_counter_ns() - start
        assert result.passed is True, result
        latencies_ms.append(elapsed_ns / 1_000_000.0)

    assert len(latencies_ms) == SAMPLE_RUNS
    ordered = sorted(latencies_ms)
    return {
        "warmup_runs": WARMUP_RUNS,
        "sample_runs": SAMPLE_RUNS,
        "claim_count": SYNTHETIC_CLAIMS,
        "evidence_count": SYNTHETIC_RECORDS,
        "encoded_bytes": encoded_bytes,
        "latencies_ms": latencies_ms,
        "p50_ms": statistics.median(latencies_ms),
        "p95_ms": ordered[94],
        "max_ms": ordered[-1],
        "environment": {
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "system": platform.system(),
            "logical_cpu_count": os.cpu_count(),
        },
        "purpose": "preparatory_synthetic_only",
    }


def test_gate_p95_under_limit():
    result = measure_gate()
    print(json.dumps(result, indent=2, sort_keys=True))
    assert result["p95_ms"] <= P95_LIMIT_MS, (
        f"gate p95 {result['p95_ms']:.3f}ms exceeds {P95_LIMIT_MS}ms"
    )


if __name__ == "__main__":
    result = measure_gate()
    print(json.dumps(result, indent=2, sort_keys=True))
