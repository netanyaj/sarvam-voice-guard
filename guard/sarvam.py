"""Small Sarvam API client shared by the guard modules.

Reads SARVAM_API_KEY from the environment, or from ../.env. The key is only ever sent as a header.
"""
import os

import requests

BASE = "https://api.sarvam.ai"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_DIR = os.path.join(HERE, ".cache")


class SarvamError(RuntimeError):
    pass


def api_key():
    key = os.environ.get("SARVAM_API_KEY")
    if key:
        return key
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        with open(env) as f:
            for line in f:
                if line.strip().startswith("SARVAM_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SarvamError("SARVAM_API_KEY not found in the environment or .env")


def _check(r):
    if r.status_code != 200:
        try:
            body = r.json()
        except ValueError:
            body = r.text[:500]
        raise SarvamError(f"HTTP {r.status_code} from {r.url}: {body}")
    return r.json()


def post_json(path, body, timeout=60):
    r = requests.post(BASE + path, headers={"api-subscription-key": api_key()}, json=body, timeout=timeout)
    return _check(r)


def post_multipart(path, data, files, timeout=120):
    r = requests.post(BASE + path, headers={"api-subscription-key": api_key()}, data=data, files=files,
                      timeout=timeout)
    return _check(r)
