def run_once(state, token, operation):
    """Only an explicit new token may invoke a run. Routine UI rerenders cannot."""
    if state.get("executed_token") != token:
        # Mark first: a rerun during a request must not duplicate network work.
        state["executed_token"] = token
        state["result"] = operation()
    return state.get("result")
