from app.router import heuristic_route

def test_simple_prompt_routes_easy():
    assert heuristic_route("What is an API?")["tier"] == "easy"

def test_explanation_routes_medium():
    assert heuristic_route("Explain the difference between REST and GraphQL")["tier"] == "medium"

def test_architecture_routes_hard():
    assert heuristic_route("Design a production architecture for a multi-tenant API")["tier"] == "hard"

def test_long_prompt_routes_hard():
    prompt = "Please review this detailed request. " * 40
    assert heuristic_route(prompt)["tier"] == "hard"
