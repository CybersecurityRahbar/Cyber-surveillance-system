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
