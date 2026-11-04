from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_PATH = (
    Path(__file__).resolve().parents[1] / "notebooks" / "Google_Colab_Lab.ipynb"
)
TUNNEL_PROVIDER_ASSIGNMENT = 'TUNNEL_PROVIDER = "cloudflare"'


def _cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def test_colab_tunnel_configuration_is_an_executable_code_cell() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    cells = notebook.get("cells")

    assert isinstance(cells, list), "Notebook must contain a cells list."

    matching_cells = [
        (index, cell, _cell_source(cell))
        for index, cell in enumerate(cells)
        if TUNNEL_PROVIDER_ASSIGNMENT in _cell_source(cell)
    ]

    assert len(matching_cells) == 1, (
        "Expected exactly one cell defining the Cloudflare tunnel provider."
    )
    index, cell, source = matching_cells[0]

    assert cell.get("cell_type") == "code", (
        f"Tunnel configuration at cell {index} must be executable code, not Markdown."
    )
    assert cell.get("execution_count") is None, (
        "The tunnel setup cell must not contain a stale execution count."
    )
    assert cell.get("outputs", []) == [], (
        "The tunnel setup cell must not contain saved outputs or secrets."
    )
    assert "NGROK_AUTH_TOKEN = None" in source
    assert 'if TUNNEL_PROVIDER == "ngrok":' in source
    assert 'elif TUNNEL_PROVIDER != "cloudflare":' in source

    markdown_with_setup_code = [
        cell_index
        for cell_index, markdown_cell in enumerate(cells)
        if markdown_cell.get("cell_type") == "markdown"
        and TUNNEL_PROVIDER_ASSIGNMENT in _cell_source(markdown_cell)
    ]
    assert not markdown_with_setup_code, (
        "Executable tunnel setup code must not be stored in a Markdown cell."
    )

    compile(source, f"{NOTEBOOK_PATH}:cell-{index}", "exec")


def test_colab_always_syncs_the_latest_main_commit_before_installing() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    sources = [_cell_source(cell) for cell in notebook["cells"]]
    repository_cells = [source for source in sources if "REPO_COMMIT =" in source]
    assert len(repository_cells) == 1
    source = repository_cells[0]
    assert 'git", "-C", str(REPO), "fetch", "origin", "main' in source
    assert 'git", "-C", str(REPO), "reset", "--hard", "origin/main' in source
    assert 'git", "-C", str(REPO), "checkout", "-B", "main", "origin/main' in source
    assert "git pull" not in source
    assert "Runtime code commit:" in source


def test_colab_installs_and_verifies_the_realtime_runtime_updates() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    sources = [_cell_source(cell) for cell in notebook["cells"]]
    install_sources = [source for source in sources if "required_processor_parameters" in source]
    profile_sources = [source for source in sources if "LIVE_PROFILE =" in source]
    supervisor_sources = [source for source in sources if "CURRENT_COMMIT =" in source]

    assert len(install_sources) == 1
    assert len(profile_sources) == 1
    assert len(supervisor_sources) == 1

    install_source = install_sources[0]
    assert "realtime_mode" in install_source
    assert "record_output" in install_source
    assert "inference_size" in install_source
    assert "max_det" in install_source
    assert "LatestFrameBuffer" in install_source
    assert "received_fps" in install_source
    assert "ReconnectingPhoneSource" in install_source

    profile_source = profile_sources[0]
    assert 'LIVE_PROFILE = "low-latency"' in profile_source
    assert "LIVE_IMAGE_SIZE = 320" in profile_source
    assert "LIVE_MAX_DET = 30" in profile_source
    assert "LIVE_MAX_WIDTH = 640" in profile_source
    assert 'LIVE_TRACKER = "bytetrack.yaml"' in profile_source
    assert "LIVE_DURATION_SECONDS = 0" in profile_source
    assert "TRAFFIC_SURVEILLANCE_LIVE_IMAGE_SIZE" in profile_source
    assert "TRAFFIC_SURVEILLANCE_LIVE_MAX_DET" in profile_source
    assert "TRAFFIC_SURVEILLANCE_LIVE_MAX_WIDTH" in profile_source
    assert "TRAFFIC_SURVEILLANCE_LIVE_TRACKER" in profile_source
    assert "TRAFFIC_SURVEILLANCE_LIVE_RECORDING" in profile_source
    assert "LIVE_RECORDING = True" in profile_source

    supervisor_source = supervisor_sources[0]
    assert "CURRENT_COMMIT != REPO_COMMIT" in supervisor_source
    assert "Starting server from commit:" in supervisor_source
    assert "TRAFFIC_SURVEILLANCE_LIVE_PROFILE" not in supervisor_source


def test_colab_runtime_configuration_cells_are_valid_python() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    for index in (5, 7, 9, 11, 15, 18):
        cell = notebook["cells"][index]
        assert cell.get("cell_type") == "code"
        compile(_cell_source(cell), f"{NOTEBOOK_PATH}:cell-{index}", "exec")
