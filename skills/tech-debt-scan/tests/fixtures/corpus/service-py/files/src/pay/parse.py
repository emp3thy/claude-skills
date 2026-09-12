"""CSV statement adapter."""


def parse_csv(text):
    return [row.split(",") for row in text.splitlines()]
