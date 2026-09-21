"""Keep OpenRouter charges separate from BYOK upstream inference estimates."""


def effective_cost(usage):
    router = usage.get("cost")
    if not isinstance(router, (int, float)):
        return None
    if usage.get("is_byok"):
        upstream = (usage.get("cost_details") or {}).get("upstream_inference_cost")
        if not isinstance(upstream, (int, float)):
            return None
        return router + upstream
    return router
