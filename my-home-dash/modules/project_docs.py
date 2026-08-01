from __future__ import annotations

from html import escape
from pathlib import Path
import re


PROJECTS_ROOT = Path(__file__).resolve().parent.parent / "projects"
IRRIGATION_ROOT = PROJECTS_ROOT / "irrigation"

DOC_TITLES = {
    "goals.md": "Goals",
    "context.md": "Context",
    "decisions.md": "Decisions",
    "todo.md": "Todo",
}

IMAGE_ONLY_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
LINK_PATTERN = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<href>[^)]+)\)")
ORDERED_LIST_PATTERN = re.compile(r"\d+\.\s+(?P<content>.+)")

IRRIGATION_MATERIALS = [
    {
        "name": "Orbit B-hyve 12-station smart irrigation controller",
        "model": "57950",
        "summary": "Primary controller candidate for the prototype zone and future expansion.",
        "status_label": "Need / Confirm",
        "status_tone": "warning",
        "bucket": "need",
        "image_url": "https://static-data2.manualslib.com/product-images/09a/1401601/300x300/orbit-b-hyve.jpg",
        "source_url": "https://www.manualslib.com/manual/1401601/Orbit-B-Hyve.html#product-B-hyve%2057950",
        "notes": [
            "Model identified in the Orbit B-hyve 57950 manual listing.",
            "The manual references indoor/outdoor use and 12-station control.",
        ],
    },
    {
        "name": "Orbit jar-top in-line sprinkler valve",
        "model": "1-in. / 3/4-in.",
        "summary": "Orbit valve option for the prototype zone, with official Orbit sizing called out for 1-inch and 3/4-inch variants.",
        "status_label": "Need / Confirm",
        "status_tone": "warning",
        "bucket": "need",
        "image_url": "https://orbitirrigate.com/wp-content/uploads/2025/product/979-jar-top-automatic-sprinkler-valves-1.webp",
        "source_url": "https://orbitirrigate.com/product/jar-top-automatic-sprinkler-valves/",
        "notes": [
            "Orbit lists jar-top automatic sprinkler valves with 3/4-in. and 1-in. size options.",
            "Needs a final decision on exact size and quantity for the first zone and the full build-out.",
        ],
    },
    {
        "name": "GB Gardner Bender terminal block",
        "model": "GTB-406",
        "summary": "6-circuit terminal block candidate for organized controller and valve wiring in the prototype zone.",
        "status_label": "Need / Confirm",
        "status_tone": "warning",
        "bucket": "need",
        "image_url": "https://www.gardnerbender.com/-/media/inRiver/GTB-406_HR.jpg?mw=410&mh=270&modified=20260513015218",
        "source_url": "https://www.gardnerbender.com/en/p/GTB-406/6-Circuit-Terminal-Block-22-10-AWG",
        "notes": [
            "Gardner Bender lists GTB-406 as a 6-circuit terminal block for 22-10 AWG wire.",
            "Current reference specs are 30A and 600V, which is useful as a durable wiring junction option for the irrigation build.",
        ],
    },
    {
        "name": "Cerrowire sprinkler wire",
        "model": "240-1007C",
        "summary": "100-foot 18/7 direct-burial sprinkler wire candidate for controller-to-valve field wiring.",
        "status_label": "Need / Confirm",
        "status_tone": "warning",
        "bucket": "need",
        "image_url": "https://m.media-amazon.com/images/I/71UU6LlzEjL._AC_SX425_.jpg",
        "source_url": "https://www.amazon.com/Cerrowire-240-1007C-100-Feet-Sprinkler-Wire/dp/B00FI6X3O6",
        "notes": [
            "Amazon lists part 240-1007C as 18-gauge, 7-conductor sprinkler wire in a 100-foot length.",
            "Current reference details call out direct burial use up to 30 volts, which fits low-voltage irrigation control wiring.",
        ],
    },
    {
        "name": "Old hose sections",
        "model": "Reuse stock",
        "summary": "Base material for most water routing and for improvised protection over wiring runs.",
        "status_label": "Have / Reuse",
        "status_tone": "success",
        "bucket": "have",
        "image_url": None,
        "source_url": None,
        "notes": [
            "Cut to fit the permanent seasonal path.",
            "Leave in place over winter to avoid rebuilding the layout.",
        ],
    },
    {
        "name": "Removable sprinkler heads",
        "model": "TBD",
        "summary": "Seasonal end-point hardware that must be installed, tested, and removed for winter.",
        "status_label": "Need / Confirm",
        "status_tone": "secondary",
        "bucket": "need",
        "image_url": None,
        "source_url": None,
        "notes": [
            "Each head must be tested after installation.",
            "Final count and head type still need confirmation.",
        ],
    },
    {
        "name": "Switches and valve wiring",
        "model": "Per zone",
        "summary": "Each switch needs to be wired and proven against the corresponding head before sign-off.",
        "status_label": "Need / Confirm",
        "status_tone": "secondary",
        "bucket": "need",
        "image_url": None,
        "source_url": "https://www.manualslib.com/manual/1401601/Orbit-B-Hyve.html?page=6#manual",
        "notes": [
            "Need enough wire, connectors, and terminations for each active zone.",
            "Manual page 6 is the current wiring reference for the controller candidate.",
        ],
    },
]


def _render_inline(markdown_text: str) -> str:
    parts: list[str] = []
    last_index = 0
    for match in LINK_PATTERN.finditer(markdown_text):
        parts.append(escape(markdown_text[last_index:match.start()]))
        href = escape(match.group("href"), quote=True)
        label = escape(match.group("label"))
        parts.append(f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>')
        last_index = match.end()
    parts.append(escape(markdown_text[last_index:]))
    return "".join(parts)


def render_simple_markdown(markdown_text: str) -> str:
    html_parts: list[str] = []
    list_type: str | None = None

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            html_parts.append(f"</{list_type}>")
            list_type = None

    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            close_list()
            continue

        image_match = IMAGE_ONLY_PATTERN.fullmatch(stripped)
        if image_match:
            close_list()
            alt_text = escape(image_match.group("alt"))
            image_src = escape(image_match.group("src"), quote=True)
            html_parts.append(
                "<figure class=\"mhd-markdown-figure\">"
                f"<img src=\"{image_src}\" alt=\"{alt_text}\" class=\"mhd-markdown-image rounded border\">"
            )
            if alt_text:
                html_parts.append(f"<figcaption>{alt_text}</figcaption>")
            html_parts.append("</figure>")
            continue

        if stripped == "---":
            close_list()
            html_parts.append("<hr>")
            continue

        if stripped.startswith("#"):
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            content = stripped[level:].strip()
            html_parts.append(f"<h{level}>{_render_inline(content)}</h{level}>")
            continue

        if stripped.startswith(">"):
            close_list()
            html_parts.append(f"<blockquote>{_render_inline(stripped[1:].strip())}</blockquote>")
            continue

        is_unordered = stripped.startswith("- ")
        ordered_match = ORDERED_LIST_PATTERN.fullmatch(stripped)
        desired_list_type: str | None = None

        if is_unordered:
            desired_list_type = "ul"
            content = stripped[2:].strip()
        elif ordered_match is not None:
            desired_list_type = "ol"
            content = ordered_match.group("content").strip()

        if desired_list_type is not None:
            if list_type != desired_list_type:
                close_list()
                html_parts.append(f"<{desired_list_type}>")
                list_type = desired_list_type

            html_parts.append(f"<li>{_render_inline(content)}</li>")
            continue

        close_list()
        html_parts.append(f"<p>{_render_inline(stripped)}</p>")

    close_list()
    return "\n".join(html_parts)


def _read_doc(filename: str, title: str) -> dict | None:
    path = IRRIGATION_ROOT / filename
    if not path.exists():
        return None

    return {
        "filename": filename,
        "title": title,
        "html": render_simple_markdown(path.read_text(encoding="utf-8")),
    }


def get_irrigation_project() -> dict:
    docs = [
        doc
        for filename, title in DOC_TITLES.items()
        for doc in [_read_doc(filename, title)]
        if doc is not None
    ]

    return {
        "materials": IRRIGATION_MATERIALS,
        "docs": docs,
        "have_items": [item["name"] for item in IRRIGATION_MATERIALS if item["bucket"] == "have"],
        "need_items": [item["name"] for item in IRRIGATION_MATERIALS if item["bucket"] == "need"],
        "framework_filename": "abstract_goal_context_decisions_todo.md",
        "framework_exists": (IRRIGATION_ROOT / "abstract_goal_context_decisions_todo.md").exists(),
    }