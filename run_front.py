from __future__ import annotations

import os
import json
import subprocess
import time
from flask import Flask, abort, jsonify, redirect, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "modules", "frontend")
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, "templates")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
FRONTEND_MENU_CONFIG_PATH = os.path.join(BASE_DIR, "configs", "frontend_menu.json")

FRONTEND_PAGES = (
    {
        "id": "status",
        "endpoint": "status",
        "path": "/",
        "template": "status.html",
        "label": "\uc0c1\ud0dc",
    },
    {
        "id": "position_control",
        "endpoint": "position_control",
        "path": "/position-control",
        "template": "position_control.html",
        "label": "\uc704\uce58 \uc81c\uc5b4",
    },
    {
        "id": "mode_control",
        "endpoint": "mode_control",
        "path": "/mode-control",
        "template": "mode_control.html",
        "label": "\ubaa8\ub4dc \uc81c\uc5b4",
    },
    {
        "id": "voice_control",
        "endpoint": "voice_control",
        "path": "/voice-control",
        "template": "voice_control.html",
        "label": "\uc74c\uc131 \uc81c\uc5b4",
    },
    {
        "id": "telemetry",
        "endpoint": "robot_telemetry",
        "path": "/robot-telemetry",
        "template": "telemetry.html",
        "label": "\ub85c\ubd07 \ub370\uc774\ud130",
    },
    {
        "id": "power_control",
        "endpoint": "power_control",
        "path": "/power-control",
        "template": "power_control.html",
        "label": "\uc804\uc6d0 \uc81c\uc5b4",
    },
    {
        "id": "motion",
        "endpoint": "motion",
        "path": "/motion",
        "template": "motion.html",
        "label": "\ubaa8\uc158",
    },
    {
        "id": "alarms",
        "endpoint": "alarms",
        "path": "/alarms",
        "template": "alarms.html",
        "label": "\uc54c\ub9bc \ubc0f \uae30\ub85d",
    },
)

from modules.backend.variable_manager import variable_manager

def run_cmd(cmd):
    subprocess.run(cmd, shell=True, check=False)

# run_cmd("pactl unload-module module-udev-detect")
# time.sleep(1)
# run_cmd("pactl load-module module-udev-detect")
# time.sleep(1)
# run_cmd("pulseaudio -k")
# time.sleep(1)
# run_cmd("rm -rf ~/.config/pulse")
# time.sleep(1)
# run_cmd("pulseaudio --start")

app = Flask(
    __name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR, static_url_path="/static"
)
app.config["JSON_AS_ASCII"] = False
app.config["BACKEND_BASE_URL"] = os.environ.get("BACKEND_BASE_URL", "http://localhost:3191")


def _is_frontend_page_enabled(page):
    enabled = page.get("enabled")
    if enabled is None:
        enabled = page.get("menu_enabled", page.get("page_enabled", False))
    if isinstance(enabled, str):
        return enabled.strip().lower() in {"1", "true", "yes", "on"}
    return bool(enabled)


def _get_frontend_enabled_config(config):
    pages_config = config.get("pages", {})
    if isinstance(pages_config, dict):
        return pages_config

    if isinstance(pages_config, list):
        enabled_by_id = {}
        for page_config in pages_config:
            if not isinstance(page_config, dict) or "id" not in page_config:
                continue
            enabled_by_id[page_config["id"]] = page_config.get(
                "enabled",
                page_config.get("menu_enabled", page_config.get("page_enabled", False)),
            )
        return enabled_by_id

    return {}


def _load_frontend_pages():
    with open(FRONTEND_MENU_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    enabled_by_id = _get_frontend_enabled_config(config)
    pages = []
    for page_definition in FRONTEND_PAGES:
        page = dict(page_definition)
        page["enabled"] = _is_frontend_page_enabled(
            {"enabled": enabled_by_id.get(page["id"], False)}
        )
        pages.append(page)

    page_map = {page["id"]: page for page in pages}
    menu_pages = [page for page in pages if _is_frontend_page_enabled(page)]
    return pages, page_map, menu_pages


ALL_PAGES, PAGE_MAP, MENU_PAGES = _load_frontend_pages()


def _render_page(page_id: str):
    page_config = PAGE_MAP.get(page_id)
    if page_config is None or not _is_frontend_page_enabled(page_config):
        return abort(404)
    return render_template(page_config["template"], active_page=page_id)


def _make_frontend_page_view(page_id: str):
    def view():
        return _render_page(page_id)

    view.__name__ = f"frontend_page_{page_id}"
    return view


def _register_frontend_routes():
    for page in ALL_PAGES:
        app.add_url_rule(
            page["path"],
            endpoint=page["endpoint"],
            view_func=_make_frontend_page_view(page["id"]),
        )


_register_frontend_routes()


@app.route("/system-info")
def legacy_system_info():
    return redirect("/power-control", code=308)


@app.context_processor
def inject_state():
    """Expose the current application state to Jinja templates."""

    return {
        "app_state": variable_manager.read(),
        "backend_base_url": app.config["BACKEND_BASE_URL"],
        "menu_pages": MENU_PAGES,
    }


def _json_error(status_code: int, message: str):
    response = jsonify({"error": message})
    response.status_code = status_code
    return response


@app.route("/api/state", methods=["GET"])
def api_get_state():
    return jsonify(variable_manager.read())


@app.route("/api/state", methods=["PATCH", "POST"])
def api_update_state():
    payload = request.get_json(silent=True)
    if payload is None:
        return _json_error(400, "JSON 본문이 필요합니다.")
    try:
        updated = variable_manager.update(payload)
    except TypeError as error:
        return _json_error(400, str(error))
    return jsonify(updated)


@app.route("/api/state/touch/<path:path>", methods=["POST"])
def api_touch_state(path: str):
    try:
        updated = variable_manager.touch(path)
    except ValueError as error:
        return _json_error(400, str(error))
    return jsonify(updated)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=3190)
