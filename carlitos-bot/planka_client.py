"""Planka REST API client with auto-renewing authentication."""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import PLANKA_URL, PLANKA_EMAIL, PLANKA_PASSWORD, PROJECT_COLUMNS

logger = logging.getLogger(__name__)


class PlankaError(Exception):
    """Raised when a Planka API call fails."""


class PlankaClient:
    """Synchronous client for the Planka kanban API."""

    def __init__(self) -> None:
        self._token: str = ""
        self._base = PLANKA_URL
        # Cached structure: {project_name: {id, boards: [{id, lists: [{id, name}]}]}}
        self._cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login(self) -> str:
        """Obtain a fresh JWT token."""
        resp = requests.post(
            f"{self._base}/api/access-tokens",
            json={"emailOrUsername": PLANKA_EMAIL, "password": PLANKA_PASSWORD},
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json().get("item")
        if not token:
            raise PlankaError("No se pudo obtener token de Planka.")
        self._token = token
        logger.info("Planka: token obtenido/renovado.")
        return token

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Make an API request with automatic token renewal on 401."""
        url = f"{self._base}{path}"
        kwargs.setdefault("timeout", 15)

        resp = requests.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code == 401:
            logger.info("Planka: 401 — renovando token…")
            self._login()
            resp = requests.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code >= 400:
            raise PlankaError(
                f"Planka API error {resp.status_code}: {resp.text[:300]}"
            )
        if resp.status_code == 204:
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # Projects / structure
    # ------------------------------------------------------------------

    def refresh_cache(self) -> None:
        """Load all projects, boards, lists and cards into the cache."""
        projects_resp = self._request("GET", "/api/projects")
        items = projects_resp.get("items", [])

        cache: dict[str, Any] = {}
        for proj in items:
            proj_name: str = proj["name"]
            if proj_name not in PROJECT_COLUMNS:
                continue

            detail = self._request("GET", f"/api/projects/{proj['id']}")
            included = detail.get("included", {})

            boards = included.get("boards", [])
            lists = included.get("lists", [])
            cards = included.get("cards", [])

            # Build board → lists mapping
            board_map: dict[str, list[dict[str, Any]]] = {}
            for lst in lists:
                bid = lst["boardId"]
                board_map.setdefault(bid, []).append(lst)

            # Build list → cards mapping
            list_card_map: dict[str, list[dict[str, Any]]] = {}
            for card in cards:
                lid = card["listId"]
                list_card_map.setdefault(lid, []).append(card)

            cache[proj_name] = {
                "id": proj["id"],
                "boards": [
                    {
                        "id": b["id"],
                        "name": b.get("name", ""),
                        "lists": [
                            {
                                "id": l["id"],
                                "name": l["name"],
                                "cards": list_card_map.get(l["id"], []),
                            }
                            for l in board_map.get(b["id"], [])
                        ],
                    }
                    for b in boards
                ],
            }

        self._cache = cache
        logger.info("Planka: cache actualizado (%d proyectos).", len(cache))

    def _ensure_cache(self) -> None:
        if not self._cache:
            self.refresh_cache()

    def get_project_names(self) -> list[str]:
        self._ensure_cache()
        return list(self._cache.keys())

    def get_project(self, name: str) -> dict[str, Any] | None:
        self._ensure_cache()
        return self._cache.get(name)

    def find_list_id(self, project_name: str, list_name: str) -> str | None:
        """Return the list ID for a given project + list name."""
        proj = self.get_project(project_name)
        if not proj:
            return None
        for board in proj["boards"]:
            for lst in board["lists"]:
                if lst["name"] == list_name:
                    return lst["id"]
        return None

    def find_card_by_id(self, card_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """Find a card across all cached projects. Returns (card, project_name)."""
        self._ensure_cache()
        for proj_name, proj in self._cache.items():
            for board in proj["boards"]:
                for lst in board["lists"]:
                    for card in lst["cards"]:
                        if str(card["id"]) == str(card_id):
                            return card, proj_name
        return None, None

    def find_list_name_for_card(self, card_id: str) -> str | None:
        """Return the list name that contains a given card."""
        self._ensure_cache()
        for proj in self._cache.values():
            for board in proj["boards"]:
                for lst in board["lists"]:
                    for card in lst["cards"]:
                        if str(card["id"]) == str(card_id):
                            return lst["name"]
        return None

    # ------------------------------------------------------------------
    # Card operations
    # ------------------------------------------------------------------

    def create_card(
        self,
        list_id: str,
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new card in the given list."""
        payload: dict[str, Any] = {"name": name, "position": 65535}
        if description:
            payload["description"] = description
        data = self._request("POST", f"/api/lists/{list_id}/cards", json=payload)
        # Invalidate cache so next listing is fresh
        self._cache.clear()
        return data.get("item", data)

    def update_card(self, card_id: str, **fields: Any) -> dict[str, Any]:
        """Patch a card (e.g. move it by setting listId)."""
        data = self._request("PATCH", f"/api/cards/{card_id}", json=fields)
        self._cache.clear()
        return data.get("item", data)

    def delete_card(self, card_id: str) -> None:
        self._request("DELETE", f"/api/cards/{card_id}")
        self._cache.clear()

    def add_comment(self, card_id: str, text: str) -> dict[str, Any]:
        data = self._request(
            "POST", f"/api/cards/{card_id}/comment-actions", json={"text": text}
        )
        return data.get("item", data)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_cards_for_project(self, project_name: str) -> list[dict[str, Any]]:
        """Return all cards for a project with their list name attached."""
        self._ensure_cache()
        proj = self._cache.get(project_name)
        if not proj:
            return []
        results: list[dict[str, Any]] = []
        for board in proj["boards"]:
            for lst in board["lists"]:
                for card in lst["cards"]:
                    results.append({**card, "_listName": lst["name"]})
        return results

    def get_all_active_cards(self) -> list[dict[str, Any]]:
        """Return cards in 'Por hacer' / 'En progreso' across non-backlog projects."""
        self.refresh_cache()
        results: list[dict[str, Any]] = []
        for proj_name, proj in self._cache.items():
            if proj_name == "G-VIBE-C Ideas (Backlog)":
                continue
            for board in proj["boards"]:
                for lst in board["lists"]:
                    if lst["name"] in ("Por hacer", "En progreso"):
                        for card in lst["cards"]:
                            results.append(
                                {**card, "_listName": lst["name"], "_project": proj_name}
                            )
        return results
