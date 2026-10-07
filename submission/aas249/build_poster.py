"""Render the executed tie illustration as an offline AAS poster asset."""

import json
from fractions import Fraction
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

pdfmetrics.registerFont(TTFont("DVSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent
result = json.loads((root / "docs/evidence/aas249-tie-demonstration-2026-10-07.json").read_text())
assert result["result"] == "PASS" and result["evaluations"] == 192
abstract = (folder / "abstract.txt").read_text().strip()
assert len(abstract) <= 2250
data = [r for r in result["summary"] if r["model_label"] == "incumbent"]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 13,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
fig, ax = plt.subplots(figsize=(11, 4))
x = [r["budget"] for r in data]
lo = [float(Fraction(r["row_order_precision_min"])) for r in data]
hi = [float(Fraction(r["row_order_precision_max"])) for r in data]
ax.vlines(x, lo, hi, color="#8394ad", lw=14, alpha=0.45, label="Possible precision under row order")
ax.plot(
    x,
    [0.5] * 4,
    "o-",
    color="#1958ac",
    lw=2.5,
    markersize=9,
    label="Declared uniform-tie expectation",
)
ax.set(
    xticks=x,
    xlabel="Review budget in the four-object example",
    ylabel="Precision at budget",
    ylim=(-0.06, 1.08),
)
ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
ax.grid(axis="y", alpha=0.15)
ax.legend(loc="upper right", frameon=False, fontsize=10)
fig.tight_layout()
fig.savefig(folder / "tie_policy.png", dpi=200)
plt.close(fig)

w, h = 1440, 900
c = canvas.Canvas(str(folder / "SIDEREA_AAS249_Poster.pdf"), pagesize=(w, h))
c.setTitle("SIDEREA candidate review with explicit tie semantics")
c.setAuthor("Aadi Ajeesh Nair; Ryan Gomez")
c.setFillColor(HexColor("#f7f9fc"))
c.rect(0, 0, w, h, fill=1, stroke=0)
ink = HexColor("#142944")
blue = HexColor("#1958ac")
quiet = HexColor("#4d6078")
styles = {
    "body": ParagraphStyle("body", fontName="DVSans", fontSize=17, leading=24, textColor=ink),
    "small": ParagraphStyle("small", fontName="DVSans", fontSize=13, leading=18, textColor=quiet),
    "heading": ParagraphStyle(
        "heading", fontName="DVBold", fontSize=23, leading=28, textColor=blue
    ),
}


def p(text, x, y, width, kind="body"):
    obj = Paragraph(text, styles[kind])
    _, height = obj.wrap(width, 900)
    obj.drawOn(c, x, y - height)
    return y - height


c.setFillColor(blue)
c.setFont("DVBold", 15)
c.drawString(48, 852, "SIDEREA / AAS249 SOFTWARE PRESENTATION ASSET")
c.setFillColor(ink)
c.setFont("DVBold", 38)
c.drawString(48, 790, "Candidate review with explicit tie semantics")
c.setFont("DVSans", 20)
c.drawString(48, 752, "Aadi Ajeesh Nair and Ryan Gomez")
p(
    "Constructed arithmetic evidence. No real-sky performance or discovery claim.",
    48,
    722,
    1300,
    "small",
)
c.setStrokeColor(HexColor("#c7d4e7"))
c.line(48, 686, 1392, 686)

y = p("The question", 48, 654, 402, "heading") - 14
y = (
    p(
        'Can changing CSV row order alter a score when equal priorities cross a '
        'review-budget boundary?',
        48,
        y,
        402,
    )
    - 24
)
y = p("The declared policy", 48, y, 402, "heading") - 14
y = (
    p(
        'Keep higher scores. For tied scores, use expected positives under uniform '
        'selection. Ranking cannot replace catalogue evidence or human review.',
        48,
        y,
        402,
    )
    - 24
)
y = p("What was checked", 48, y, 402, "heading") - 14
y = p(
    '24 row permutations x two score columns x four budgets. All 192 outputs '
    'match exact rational precision and recall.',
    48,
    y,
    402,
)

p("One tied cohort across four review budgets", 490, 654, 880, "heading")
c.drawImage(str(folder / "tie_policy.png"), 490, 300, width=880, height=320, mask="auto")
p(
    'Four constructed objects, two positive labels, all incumbent scores equal. A '
    'selected single row can be positive or negative; the declared expectation '
    'remains one half.',
    490,
    279,
    872,
    "small",
)

c.setStrokeColor(HexColor("#c7d4e7"))
c.line(48, 217, 1392, 217)
p("What this supports", 48, 192, 405, "heading")
p(
    'A reproducible software demonstration, explicit metric semantics and a '
    'reviewable evidence trail.',
    48,
    154,
    405,
)
p("What remains open", 490, 192, 872, "heading")
p(
    'Dated photometry, independent labels and prospective validation are still '
    'needed for sky completeness, purity, discovery yield or comparative model '
    'benefit.',
    490,
    154,
    872,
)
p(
    'Source: examples/space_jepa_2_tie_fixture.csv; '
    'scripts/aas249_tie_demonstration.py; '
    'docs/evidence/aas249-tie-demonstration-2026-10-07.json',
    48,
    52,
    1320,
    "small",
)
c.save()
(folder / "asset_receipt.json").write_text(
    json.dumps(
        {
            "abstract_characters": len(abstract),
            "abstract_limit": 2250,
            "evaluations": 192,
            "poster_pages": 1,
            "presentation_status": "offline asset; unsubmitted; native iPoster pending acceptance",
        },
        indent=2,
    )
    + "\n"
)
print(folder / "SIDEREA_AAS249_Poster.pdf")
