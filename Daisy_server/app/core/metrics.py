from typing import Dict, List, Union


def bucket_label(duration_ms: int, thresholds_ms: List[int]) -> str:
    for t in thresholds_ms:
        if duration_ms <= t:
            return f"le_{t}"
    return f"gt_{thresholds_ms[-1]}" if thresholds_ms else "gt_0"


def hist_percentiles(
    hist: Dict[str, int],
    thresholds_ms: List[int],
    percentiles: List[float],
) -> Dict[str, Union[int, str, None]]:
    total = sum(int(v) for v in hist.values()) if hist else 0
    if total <= 0:
        return {f"p{int(p*100)}_ms": None for p in percentiles}

    ordered = []
    for t in thresholds_ms:
        ordered.append((t, int(hist.get(f"le_{t}", 0))))
    gt_label = f"gt_{thresholds_ms[-1]}" if thresholds_ms else "gt_0"
    gt_count = int(hist.get(gt_label, 0))

    results: Dict[str, Union[int, str, None]] = {}
    for p in percentiles:
        target = p * total
        cum = 0
        value: Union[int, str, None] = None
        for upper, c in ordered:
            cum += c
            if cum >= target:
                value = upper
                break
        if value is None:
            value = f">{thresholds_ms[-1]}" if thresholds_ms and gt_count > 0 else (thresholds_ms[-1] if thresholds_ms else None)
        results[f"p{int(p*100)}_ms"] = value

    return results


def estimate_tokens(text: str, chars_per_token: int) -> int:
    if not text:
        return 0
    n = max(1, int(chars_per_token))
    return (len(text) + n - 1) // n


ROUTER_HIST_THRESHOLDS_MS = [50, 100, 200, 500, 1000]
E2E_HIST_THRESHOLDS_MS = [500, 1000, 3000, 5000, 10000, 20000]
