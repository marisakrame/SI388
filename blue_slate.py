import csv
import re
import datetime
import json
from pathlib import Path
from html import escape

IMAGE_BASE = "https://si339.github.io/ClientData/21615274/"  # trailing slash matters
DEFAULT_IMAGE_URL = "https://raw.githubusercontent.com/vannesschia/SI338/main/images/skyline_logo.jpg"  # optional hosted fallback image URL
YEAR_FILTER = None  # set to "2025" if you only want one season; leave None for all races


# ---------------------------
# CSV parsing: Bio + Results sections
# ---------------------------
def read_sections(csv_path: Path):
    """
    Expects a CSV with marker rows:
      Bio
      <bio header>
      <bio rows...>
      Results
      <results header>
      <results rows...>
    """
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    bio_marker = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Bio"), None)
    results_marker = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Results"), None)

    if bio_marker is None or results_marker is None:
        raise ValueError("Could not find 'Bio' and 'Results' markers in the CSV.")

    bio_header = rows[bio_marker + 1]
    bio_rows = rows[bio_marker + 2 : results_marker]

    results_header = rows[results_marker + 1]
    results_rows = rows[results_marker + 2 :]

    return bio_header, bio_rows, results_header, results_rows


def parse_primary_bio(bio_header, bio_rows):
    if not bio_rows:
        return {}
    first = bio_rows[0]
    return {bio_header[i]: (first[i] if i < len(first) else "") for i in range(len(bio_header))}


def parse_results(results_header, results_rows):
    records = []
    for r in results_rows:
        if not any((cell or "").strip() for cell in r):
            continue
        rec = {results_header[i]: (r[i] if i < len(r) else "") for i in range(len(results_header))}
        records.append(rec)
    return records


# ---------------------------
# Helpers
# ---------------------------
def safe(val: str, default: str = "N/A") -> str:
    v = (val or "").strip()
    return v if v else default


def year_from_date(date_str: str) -> str:
    if not date_str:
        return ""
    m = re.search(r"\b(20\d{2})\b", date_str)
    return m.group(1) if m else ""


def image_url(photo_filename: str) -> str:
    fn = (photo_filename or "").strip()
    if not fn or fn.upper() == "N/A":
        return DEFAULT_IMAGE_URL.strip() if DEFAULT_IMAGE_URL.strip() else ""
    return IMAGE_BASE + fn

def image_alt_text(record: dict, fallback: str) -> str:
    """Prefer explicit AltText from the CSV; otherwise use a sensible fallback."""
    alt = (record.get("AltText") or "").strip()
    return alt if alt else fallback

def parse_time_to_seconds(time_str: str):
    """Parse common race time formats into seconds (float)."""
    t = (time_str or "").strip()
    if not t or t.upper() == "N/A":
        return None

    if t.count(":") == 2:
        # H:MM:SS(.ms)
        a, b, c = t.split(":")
        try:
            return int(a) * 3600 + int(b) * 60 + float(c)
        except ValueError:
            return None

    if t.count(":") == 1:
        # MM:SS(.ms)
        a, b = t.split(":", 1)
        try:
            return int(a) * 60 + float(b)
        except ValueError:
            return None

    try:
        return float(t)
    except ValueError:
        return None


def build_race_series(records):
    """Return [{date, meet, time, seconds}] sorted by date if parsable."""
    points = []
    for r in records:
        if YEAR_FILTER is not None and year_from_date((r.get("Date") or "").strip()) != YEAR_FILTER:
            continue

        meet = safe(r.get("Meet Name"))
        date = safe(r.get("Date"))
        time = safe(r.get("Time"))
        sec = parse_time_to_seconds(time)

        sort_key = ""
        ds = (r.get("Date") or "").strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%B %d %Y"):
            try:
                sort_key = datetime.datetime.strptime(ds, fmt).date().isoformat()
                break
            except Exception:
                pass

        points.append({"date": date, "meet": meet, "time": time, "seconds": sec, "_sort": sort_key})

    points.sort(key=lambda p: (p["_sort"] == "", p["_sort"]))
    return [{"date": p["date"], "meet": p["meet"], "time": p["time"], "seconds": p["seconds"]} for p in points]

# ---------------------------
# Build meet cards with toggle details
# ---------------------------
def build_meet_cards(records):
    # Optional season filter
    filtered = []
    for r in records:
        if YEAR_FILTER is None:
            filtered.append(r)
        else:
            if year_from_date((r.get("Date") or "").strip()) == YEAR_FILTER:
                filtered.append(r)

    cards = []
    for i, r in enumerate(filtered, start=1):
        meet = safe(r.get("Meet Name"))
        date = safe(r.get("Date"))
        time = safe(r.get("Time"))
        grade = safe(r.get("Grade"))
        place = safe(r.get("Overall Place"))

        photo_fn = (r.get("PhotoFileName") or "").strip()
        img_src = image_url(photo_fn)

        details_id = f"race-details-{i}"
        title_id = f"meet-{i}-title"

        img_html = (
            f'<img src="{escape(img_src)}" alt="{image_alt_text(r, fallback=f"Photo from {meet}.")}" loading="lazy" decoding="async">'
            if img_src
            else '<p>No image available.</p>'
        )

        cards.append(f"""
        <article class="meet-card" aria-labelledby="{title_id}">
          <h3 id="{title_id}">{escape(meet)}</h3>

          <div class="spacer">
            {img_html}
          </div>

          <button type="button" class="open-panel" aria-expanded="false" aria-controls="{details_id}">
            More info
          </button>

          <div id="{details_id}" class="race-details" hidden>
            <p><strong>Date:</strong> {escape(date)}</p>
            <p><strong>Time:</strong> {escape(time)}</p>
            <p><strong>Grade:</strong> {escape(grade)}</p>
            <p><strong>Overall place:</strong> {escape(place)}</p>
          </div>
        </article>
""")

    if not cards:
        return "<p>No meets found.</p>"

    return "".join(cards)


# ---------------------------
# Inject cards into the template
# ---------------------------
def inject_cards_into_template(template_html: str, cards_html: str) -> str:
    """
    Replaces everything between:
      <div id="meet-grid"...>
    and:
      <div id="performance-panel"...>
    leaving the performance panel intact.
    """
    meet_grid_open = re.search(r'(<div\s+id="meet-grid"[^>]*>)', template_html)
    if not meet_grid_open:
        raise ValueError('Could not find <div id="meet-grid"...> in the template.')

    panel_start = re.search(r'(<div\s+id="performance-panel"[^>]*>)', template_html)
    if not panel_start:
        raise ValueError('Could not find <div id="performance-panel"...> in the template.')

    start_idx = meet_grid_open.end()
    panel_idx = panel_start.start()

    before = template_html[:start_idx]
    panel_and_after = template_html[panel_idx:]

    return before + "\n" + cards_html + "\n" + panel_and_after


def inject_scripts(html_text: str, race_series_json: str) -> str:
    """Injects:
      - race data JSON
      - toggle behavior for dropdown details
      - Chart.js time trend rendering (requires Chart.js + #time-chart in template)
    """
    script = f"""
<script id="race-data" type="application/json">{race_series_json}</script>
<script>
  // Toggle per-card details (layout-stable overlay)
  document.addEventListener("click", function (e) {{
    const btn = e.target.closest("button.open-panel");
    if (!btn) return;

    const targetId = btn.getAttribute("aria-controls");
    if (!targetId) return;

    const panel = document.getElementById(targetId);
    if (!panel) return;

    const isOpen = !panel.hasAttribute("hidden");
    if (isOpen) {{
      panel.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", "false");
    }} else {{
      panel.removeAttribute("hidden");
      btn.setAttribute("aria-expanded", "true");
    }}
  }});

  // Chart.js time trend
  document.addEventListener("DOMContentLoaded", function () {{
    const el = document.getElementById("race-data");
    const canvas = document.getElementById("time-chart");
    if (!el || !canvas || typeof Chart === "undefined") return;

    const races = JSON.parse(el.textContent || "[]")
      .filter(r => typeof r.seconds === "number" && !Number.isNaN(r.seconds));

    if (!races.length) return;

    const labels = races.map(r => r.date);
    const seconds = races.map(r => r.seconds);

    function formatTime(sec) {{
      const m = Math.floor(sec / 60);
      const s = sec - m * 60;
      const sInt = Math.floor(s);
      const tenths = Math.round((s - sInt) * 10);
      const ss = String(sInt).padStart(2, "0");
      return tenths > 0 ? `${{m}}:${{ss}}.${{tenths}}` : `${{m}}:${{ss}}`;
    }}

    const ctx = canvas.getContext("2d");
    new Chart(ctx, {{
      type: "line",
      data: {{
        labels,
        datasets: [{{
          label: "Race time",
          data: seconds,
          tension: 0.25,
          pointRadius: 3
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          tooltip: {{
            callbacks: {{
              title: (items) => {{
                const i = items?.[0]?.dataIndex ?? 0;
                return races[i]?.meet ? `${{races[i].meet}}` : `${{labels[i]}}`;
              }},
              label: (item) => `Time: ${{formatTime(item.parsed.y)}}`,
              afterLabel: (item) => {{
                const i = item.dataIndex;
                return races[i]?.date ? `Date: ${{races[i].date}}` : "";
              }}
            }}
          }}
        }},
        scales: {{
          y: {{
            reverse: true,
            ticks: {{
              callback: (value) => formatTime(value)
            }},
            title: {{ display: true, text: "Time (mm:ss)" }}
          }},
          x: {{
            title: {{ display: true, text: "Meet date" }}
          }}
        }}
      }}
    }});
  }});
</script>
"""
    if "</body>" not in html_text:
        return html_text + script
    return html_text.replace("</body>", script + "\n</body>")


def replace_first_h1(html_text: str, new_name: str) -> str:
    """
    Updates the first <h1>...</h1> in the template to match the CSV.
    Keeps everything else unchanged.
    """
    if not new_name.strip():
        return html_text
    return re.sub(r"<h1>.*?</h1>", f"<h1>{escape(new_name.strip())}</h1>", html_text, count=1, flags=re.DOTALL)


# ---------------------------
# Main
# ---------------------------
def main():
    base_dir = Path(__file__).resolve().parent

    # IMPORTANT:
    # Rename your uploaded template to index.template.html
    template_path = base_dir / "index.template.html"
    csv_path = base_dir / "AthleteData - Garrett_Comer.csv"
    if not csv_path.exists():
        csv_path = base_dir / "AthleteData - Garrett_Comer.csv.csv"

    out_path = base_dir / "blue_slate_index.html"

    template_html = template_path.read_text(encoding="utf-8")

    bio_header, bio_rows, results_header, results_rows = read_sections(csv_path)
    bio = parse_primary_bio(bio_header, bio_rows)
    results = parse_results(results_header, results_rows)

    cards_html = build_meet_cards(results)
    out_html = inject_cards_into_template(template_html, cards_html)

    # Update name in header (optional, but usually desired)
    athlete_name = (bio.get("Athlete Name") or "").strip()
    out_html = replace_first_h1(out_html, athlete_name)

    # Build race series JSON for Chart.js
    race_series = build_race_series(results)
    race_series_json = json.dumps(race_series)

    # Add scripts (toggle + chart)
    out_html = inject_scripts(out_html, race_series_json)

    out_path.write_text(out_html, encoding="utf-8")
    print(f"Wrote {out_path.name}")


if __name__ == "__main__":
    main()