"""JSON statement adapter."""
import json


def parse_json(text):
    return json.loads(text)
