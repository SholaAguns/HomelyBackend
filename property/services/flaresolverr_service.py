import logging
import requests
from django.conf import settings

logger = logging.getLogger('property.services.flaresolverr')


class FlareSolverrService:

    def __init__(self):
        self.base_url = getattr(settings, 'FLARESOLVERR_URL')

    def fetch(self, url: str, session_id: str = None) -> str:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        if session_id:
            payload["session"] = session_id
        resp = requests.post(self.base_url, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != "ok":
            raise ValueError(f"FlareSolverr error: {data}")
        html = data["solution"]["response"]
        logger.debug("FlareSolverrService.fetch url=%s html_len=%d", url, len(html))
        return html

    def create_session(self) -> str:
        resp = requests.post(self.base_url, json={"cmd": "sessions.create"}, timeout=30)
        resp.raise_for_status()
        session_id = resp.json()["session"]
        logger.debug("FlareSolverrService.create_session session=%s", session_id)
        return session_id

    def destroy_session(self, session_id: str):
        try:
            requests.post(self.base_url, json={"cmd": "sessions.destroy", "session": session_id}, timeout=30)
            logger.debug("FlareSolverrService.destroy_session session=%s", session_id)
        except Exception as e:
            logger.warning("FlareSolverrService.destroy_session failed session=%s: %s", session_id, e)
