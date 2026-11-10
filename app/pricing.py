from app.config import PRICES

def estimate_cost(tier: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICES.get(tier, PRICES["medium"])
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
