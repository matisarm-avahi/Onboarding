from cart import total


def test_total():
    assert total([("a", 2.5, 2), ("b", 1.0, 1)]) == 6.0
