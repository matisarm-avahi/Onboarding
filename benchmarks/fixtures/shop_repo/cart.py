def total(items):
    """items: list of (name, unit_price, quantity). Returns the cart total."""
    return round(sum(price * qty for _, price, qty in items), 2)
