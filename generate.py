#!/usr/bin/env python3
"""
Last Mile Adoption Dashboard Generator
Fetches ALL CIL tickets (FlowForge-labelled and plain) for Last Mile epics
in a single pass, capturing status, AI cost, and FlowForge label per ticket.

Usage:
    python3 generate.py
    python3 generate.py --dry-run

Requires:
    pip install requests python-dotenv
    JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in environment or .env file
"""

import argparse
import html as html_lib
import os
import re
import sys
from collections import defaultdict
from datetime import date

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────

JIRA_URL      = os.environ.get("JIRA_URL",   "https://sisu-agile.atlassian.net")
JIRA_EMAIL    = os.environ.get("JIRA_EMAIL", "")
JIRA_TOKEN    = os.environ.get("JIRA_API_TOKEN", "")
AI_COST_FIELD = "customfield_13682"

DASHBOARD_FILE = os.path.join(os.path.dirname(__file__), "index.html")
TEMPLATE_FILE  = os.path.join(os.path.dirname(__file__), "template.html")

# Adoption % is measured from this date forward
FF_ADOPTION_START = "2026-06-01"

# ── Last Mile initiative registry ─────────────────────────────────────────────
# (slug, prod_key, project_number, display_title, {epic_key: epic_title})

INITIATIVES = [
    # ── 15803 · Fusion B2C US ────────────────────────────────────────────────
    ("travel", "PROD-12933", "15803", "Fusion B2C US (Phase 1)", {
        "PROD-13143": "[FR-04] Requote 'Get a Quote' (Traveler's Details)",
        "PROD-13062": "[EHA Widget + MP] — Get Policy and Coverages details",
        "PROD-13400": "EHA Widget — Upload and Delete Case Documents",
        "PROD-13145": "Travel — Braintree Payment Integration",
        "PROD-13136": "Travel — Gadget Fields Integration",
        "PROD-13282": "Travel — [FR-09] Save & Retrieve via Email",
        "PROD-13201": "CIL Library — USPG API Provider",
        "PROD-12844": "Fusion B2C US — Discovery",
    }),

    # ── 15820 · AgentMax Replacement ─────────────────────────────────────────
    ("agentmax-w1", "PROD-11333", "15820", "AgentMax Replacement — Wave 1 (DE, AT, CH)", {
        "PROD-11345": "AgentMax W1 — Project Setup",
        "PROD-11522": "AgentMax W1 — Sales: Fetching Quotes",
        "PROD-11561": "AgentMax W1 — Enable Saved Quotes",
        "PROD-11562": "AgentMax W1 — Enabling Email Sending",
        "PROD-11563": "AgentMax W1 — Email Sending (eMagin dependency)",
        "PROD-11802": "AgentMax W1 — Sales: Buying Policies",
        "PROD-11803": "AgentMax W1 — Sales: Medical Assessment",
        "PROD-12166": "AgentMax W1 — Post-sales: Cancelling Policies",
        "PROD-12503": "AgentMax W1 — Analytics",
    }),
    ("agentmax-uk", "PROD-12001", "15820", "AgentMax Replacement — UK", {
        "PROD-12018": "AgentMax UK — Project Setup",
        "PROD-12021": "AgentMax UK — Sales: Fetching Quotes",
        "PROD-12024": "AgentMax UK — Enable Saved Quotes",
        "PROD-12027": "AgentMax UK — Enabling Email Sending",
        "PROD-12036": "AgentMax UK — Sales: Buying Policies",
        "PROD-12202": "AgentMax UK — Policy Modifications",
        "PROD-12223": "AgentMax UK — Service Expansion",
        "PROD-12239": "AgentMax UK — Person Creation",
        "PROD-12505": "AgentMax UK — Analytics",
    }),
    ("agentmax-es", "PROD-12002", "15820", "AgentMax Replacement — ES", {
        "PROD-12019": "AgentMax ES — Project Setup",
        "PROD-12023": "AgentMax ES — Sales: Fetching Quotes",
        "PROD-12026": "AgentMax ES — Enable Saved Quotes",
        "PROD-12029": "AgentMax ES — Enabling Email Sending",
        "PROD-12038": "AgentMax ES — Sales: Buying Policies",
        "PROD-12506": "AgentMax ES — Analytics",
    }),
    ("agentmax-cz", "PROD-12003", "15820", "AgentMax Replacement — CZ", {
        "PROD-12020": "AgentMax CZ — Project Setup",
        "PROD-12022": "AgentMax CZ — Sales: Fetching Quotes",
        "PROD-12025": "AgentMax CZ — Enable Saved Quotes",
        "PROD-12028": "AgentMax CZ — Enabling Email Sending",
        "PROD-12037": "AgentMax CZ — Sales: Buying Policies",
        "PROD-12504": "AgentMax CZ — Analytics",
    }),
    ("agentmax-w3", "PROD-12848", "15820", "AgentMax Replacement — Wave 3", {
        "PROD-12849": "AgentMax W3 — Project Setup",
        "PROD-13212": "AgentMax W3 — Sales: Fetching Quotes",
        "PROD-13213": "AgentMax W3 — Sales: Buying Policies",
        "PROD-13214": "AgentMax W3 — Enabling Email Sending",
    }),
    ("agentmax-apis", "PROD-13127", "15820", "AgentMax Replacement — APIs", {
        "PROD-13621": "AgentMax APIs — View Endpoints",
        "PROD-13664": "AgentMax APIs — Price Relevant Modifications",
        "PROD-13682": "AgentMax APIs — Non-Price Relevant Modifications",
        "PROD-13696": "AgentMax APIs — Travel Quotation to Radar",
        "PROD-13763": "AgentMax APIs — Trigger Emails via eMagin",
        "PROD-13799": "AgentMax APIs — Notes to Contract Modifications",
    }),

    # ── 15832 · Clara ─────────────────────────────────────────────────────────
    ("clara-replacement", "PROD-11743", "15832", "Clara Replacement", {
        "PROD-12533": "Clara Replacement — [00] Project Setup",
        "PROD-12534": "Clara Replacement — [02] Authentication",
        "PROD-12535": "Clara Replacement — [03] Sales Data Flows — Quoting",
        "PROD-12536": "Clara Replacement — [08] Post-sales — Fetch Policy Data",
        "PROD-12537": "Clara Replacement — [09] Post-sales — Fetch Claims Data",
        "PROD-13189": "Clara Replacement — [04] Sales Data Flows — Payments",
        "PROD-13190": "Clara Replacement — [06] Sales Data Flows — Policy Creation",
        "PROD-13219": "Clara Replacement — [07] Sales Data Flows — Medical Assessment SMS",
        "PROD-13220": "Clara Replacement — [11] Post-sales — Policy Cancellations",
        "PROD-13234": "Clara Replacement — [13] FlowForge",
        "PROD-12730": "Clara Replacement — [10] Post-sales — Policy Amendments (non-price)",
        "PROD-13902": "Clara Replacement — [11] Post-sales — Policy Amendments (price relevant)",
    }),
    ("clara", "PROD-13092", "15832", "Clara EHA Beneficiary Management and MP Access", {
        "PROD-13255": "Clara EHA — CIL Beneficiary Management Implementation",
        "PROD-13235": "FlowForge for Clara EHA Beneficiary Management",
    }),
    ("clara-price", "PROD-13218", "15832", "Clara Price Relevant Modifications (xLOB)", {
        "PROD-13245": "Policy Recalculation for Contract Management (Amendments)",
    }),
    ("clara-eha-widget", "PROD-12960", "15832", "Clara Emergency Home Assistance", {
        "PROD-12963": "EHA Widget — Create Case",
    }),
    ("travel-claims-gap", "PROD-13098", "15832", "Travel Claims Feature Gap", {
        "PROD-13491": "Travel Claims — Unified Claims View Single CIL Entry Point",
    }),
]

# Build lookup tables
EPIC_TO_INIT = {}
INIT_META    = {}   # slug → (prod_key, project_number, title, epics_dict)
for slug, prod_key, proj, title, epics in INITIATIVES:
    INIT_META[slug] = (prod_key, proj, title, epics)
    EPIC_TO_INIT[prod_key] = slug
    for e in epics:
        EPIC_TO_INIT[e] = slug

ALL_EPIC_KEYS = set(EPIC_TO_INIT.keys())

PROJECT_LABELS = {
    "15803": "Fusion B2C US",
    "15820": "AgentMax Replacement",
    "15832": "Clara",
}


# ── Jira helpers ──────────────────────────────────────────────────────────────

def jira_search(jql, fields):
    auth = (JIRA_EMAIL, JIRA_TOKEN)
    fields_list = fields.split(",") if isinstance(fields, str) else fields
    all_issues, next_token = [], None
    while True:
        body = {"jql": jql, "fields": fields_list, "maxResults": 100}
        if next_token:
            body["nextPageToken"] = next_token
        r = requests.post(
            f"{JIRA_URL}/rest/api/3/search/jql",
            auth=auth, json=body, timeout=30
        )
        r.raise_for_status()
        data = r.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        if data.get("isLast", True) or not issues:
            break
        next_token = data.get("nextPageToken")
        if not next_token:
            break
    return all_issues


def fetch_all_tickets(epic_keys):
    """Single fetch of ALL CIL tickets under Last Mile epics.
    Captures: key, summary, parent, created, status, cat, is_flowforge, ai_cost."""
    keys_list  = list(epic_keys)
    all_tickets = []
    batch_size  = 50
    fields      = f"summary,status,parent,created,labels,{AI_COST_FIELD}"

    for i in range(0, len(keys_list), batch_size):
        batch    = keys_list[i:i + batch_size]
        keys_str = ",".join(batch)
        jql      = f'project = CIL AND "Epic Link" in ({keys_str}) ORDER BY created ASC'
        try:
            raw = jira_search(jql, fields)
        except Exception as e:
            print(f"  Warning: batch {i // batch_size} failed: {e}", file=sys.stderr)
            raw = []

        for issue in raw:
            f        = issue["fields"]
            labels   = f.get("labels") or []
            parent   = (f.get("parent") or {}).get("key", "")
            status   = f.get("status") or {}
            stat_name = status.get("name", "")
            stat_cat  = status.get("statusCategory", {}).get("name", "To Do")
            created  = (f.get("created") or "")[:10]
            try:
                ai_cost = float(f.get(AI_COST_FIELD) or 0)
            except (TypeError, ValueError):
                ai_cost = 0.0

            all_tickets.append({
                "key":          issue["key"],
                "summary":      f.get("summary", ""),
                "parent":       parent,
                "created":      created,
                "status":       stat_name,
                "cat":          stat_cat,
                "is_flowforge": "FlowForge" in labels,
                "ai_cost":      ai_cost,
            })

    return all_tickets


# ── Data computation ──────────────────────────────────────────────────────────

def compute_stats(all_tickets):
    """Compute per-initiative stats from the single ticket list."""
    by_slug = defaultdict(list)
    for t in all_tickets:
        slug = EPIC_TO_INIT.get(t["parent"])
        if slug:
            by_slug[slug].append(t)

    stats = {}
    for slug, (prod_key, proj, title, epics) in INIT_META.items():
        tickets = by_slug[slug]
        ff      = [t for t in tickets if t["is_flowforge"]]

        total_since = sum(1 for t in tickets if t["created"] >= FF_ADOPTION_START)
        ff_since    = sum(1 for t in ff      if t["created"] >= FF_ADOPTION_START)
        pct_since   = round(ff_since / total_since * 100) if total_since > 0 else 0

        stats[slug] = {
            "slug":        slug,
            "prod_key":    prod_key,
            "proj":        proj,
            "title":       title,
            "total":       len(tickets),
            "ff":          len(ff),
            "total_since": total_since,
            "ff_since":    ff_since,
            "pct_since":   pct_since,
            "done_ff":     sum(1 for t in ff if t["cat"] == "Done"),
            "wip_ff":      sum(1 for t in ff if t["cat"] == "In Progress"),
            "todo_ff":     sum(1 for t in ff if t["cat"] == "To Do"),
            "ai_cost":     sum(t["ai_cost"] for t in tickets),
            "tickets":     tickets,
        }
    return stats


def compute_monthly_adoption(all_tickets):
    """Per-project-number monthly series: {proj: {ym: {total, ff, cost}}}"""
    by_proj = defaultdict(lambda: defaultdict(lambda: {"total": 0, "ff": 0, "cost": 0.0}))

    for t in all_tickets:
        slug = EPIC_TO_INIT.get(t["parent"])
        if not slug:
            continue
        proj = INIT_META[slug][1]
        ym   = t["created"][:7]
        by_proj[proj][ym]["total"] += 1
        if t["is_flowforge"]:
            by_proj[proj][ym]["ff"] += 1
        by_proj[proj][ym]["cost"] += t["ai_cost"]

    all_months = sorted({ym for d in by_proj.values() for ym in d})
    return by_proj, all_months


# ── HTML builders ─────────────────────────────────────────────────────────────

def pct_color(pct):
    if pct >= 70:
        return "#16a34a"
    if pct >= 40:
        return "#d97706"
    return "#dc2626"


def _status_badge(cat, status):
    if cat == "Done":
        return '<span class="t-badge t-done">Done</span>'
    if cat == "In Progress":
        return f'<span class="t-badge t-wip">{html_lib.escape(status)}</span>'
    return f'<span class="t-badge t-todo">{html_lib.escape(status)}</span>'


def _cost_str(cost):
    if cost >= 1:
        return f"${cost:.2f}"
    if cost > 0:
        return f"${cost:.3f}"
    return "—"


def build_detail_panel(s):
    """Expandable panel: epics → tickets with key, summary, FF label, status, AI cost."""
    prod_key = s["prod_key"]
    slug     = s["slug"]
    _, proj, title, epics = INIT_META[slug]

    by_epic = defaultdict(list)
    for t in s["tickets"]:
        by_epic[t["parent"]].append(t)

    parts = []
    for epic_key, epic_title in epics.items():
        tickets = by_epic.get(epic_key, [])
        if not tickets:
            continue
        ff_count   = sum(1 for t in tickets if t["is_flowforge"])
        epic_cost  = sum(t["ai_cost"] for t in tickets)
        ff_badge   = f'<span class="epic-ff-badge">{ff_count} FF</span>' if ff_count else ""
        cost_badge = f'<span class="epic-cost-badge">✦ {_cost_str(epic_cost)}</span>' if epic_cost > 0 else ""
        key_html   = (
            f'<a class="epic-key-link" href="{JIRA_URL}/browse/{epic_key}" target="_blank">{epic_key}</a>'
            if epic_key else ""
        )
        rows = ""
        for t in sorted(tickets, key=lambda x: x["key"]):
            pill = '<span class="ff-pill">FlowForge</span>' if t["is_flowforge"] else '<span class="plain-pill">plain</span>'
            stat = _status_badge(t["cat"], t["status"])
            cost = f'<span class="ticket-cost">{_cost_str(t["ai_cost"])}</span>'
            rows += (
                f'<div class="ticket-item">'
                f'<a class="ticket-key" href="{JIRA_URL}/browse/{t["key"]}" target="_blank">{t["key"]}</a>'
                f'<span class="ticket-summary">{html_lib.escape(t["summary"])}</span>'
                f'{pill}{stat}{cost}'
                f'</div>\n'
            )
        parts.append(
            f'<div class="epic-group">'
            f'<div class="epic-head">{key_html}'
            f'<span class="epic-title">{html_lib.escape(epic_title)}</span>'
            f'{ff_badge}{cost_badge}</div>'
            f'<div class="ticket-list">{rows}</div>'
            f'</div>'
        )

    # Tickets parented directly to the initiative prod_key
    direct = [t for t in by_epic.get(prod_key, []) if prod_key not in epics]
    if direct:
        rows = ""
        for t in sorted(direct, key=lambda x: x["key"]):
            pill = '<span class="ff-pill">FlowForge</span>' if t["is_flowforge"] else '<span class="plain-pill">plain</span>'
            stat = _status_badge(t["cat"], t["status"])
            cost = f'<span class="ticket-cost">{_cost_str(t["ai_cost"])}</span>'
            rows += (
                f'<div class="ticket-item">'
                f'<a class="ticket-key" href="{JIRA_URL}/browse/{t["key"]}" target="_blank">{t["key"]}</a>'
                f'<span class="ticket-summary">{html_lib.escape(t["summary"])}</span>'
                f'{pill}{stat}{cost}'
                f'</div>\n'
            )
        parts.append(
            f'<div class="epic-group">'
            f'<div class="epic-head"><span class="epic-title">Direct tickets</span></div>'
            f'<div class="ticket-list">{rows}</div>'
            f'</div>'
        )

    inner = "\n".join(parts) if parts else '<span style="color:#475569;font-size:12px">No tickets found.</span>'
    return f'<div class="detail-panel">{inner}</div>'


def build_initiative_row(s):
    pct   = s["pct_since"]
    color = pct_color(pct)
    ff    = s["ff_since"]
    total = s["total_since"]
    cost  = s["ai_cost"]

    done_html = f'<span class="badge badge-done">{s["done_ff"]} done</span>' if s["done_ff"] else ""
    wip_html  = f'<span class="badge badge-wip">{s["wip_ff"]} active</span>'  if s["wip_ff"]  else ""
    todo_html = f'<span class="badge badge-todo">{s["todo_ff"]} to do</span>' if s["todo_ff"] else ""
    cost_html = f'<span class="init-cost">✦ {_cost_str(cost)}</span>' if cost > 0 else ""

    detail = build_detail_panel(s)

    return (
        f'<tr class="init-row">'
        f'<td class="init-name">'
        f'<button class="expand-btn" onclick="toggleInit(this)" title="Show epics &amp; tickets">▶</button> '
        f'<a href="{JIRA_URL}/browse/{s["prod_key"]}" target="_blank" class="init-link">{html_lib.escape(s["title"])}</a>'
        f'</td>'
        f'<td class="adopt-cell">'
        f'<div class="adopt-bar-wrap"><div class="adopt-bar" style="width:{pct}%;background:{color}"></div></div>'
        f'</td>'
        f'<td class="pct-cell" style="color:{color}">{pct}%</td>'
        f'<td class="count-cell">{ff} <span class="dim">/ {total}</span></td>'
        f'<td class="badge-cell">{wip_html}{done_html}{todo_html}</td>'
        f'<td class="cost-cell">{cost_html}</td>'
        f'</tr>'
        f'<tr class="detail-row"><td colspan="6">{detail}</td></tr>'
    )


def build_project_section(proj, label, init_slugs, stats):
    proj_total_since = sum(stats[s]["total_since"] for s in init_slugs if s in stats)
    proj_ff_since    = sum(stats[s]["ff_since"]    for s in init_slugs if s in stats)
    proj_pct         = round(proj_ff_since / proj_total_since * 100) if proj_total_since > 0 else 0
    proj_cost        = sum(stats[s]["ai_cost"] for s in init_slugs if s in stats)
    color            = pct_color(proj_pct)

    rows = "\n".join(
        build_initiative_row(stats[s])
        for s in init_slugs if s in stats and stats[s]["total"] > 0
    )
    cost_html = f'<span class="proj-cost">✦ {_cost_str(proj_cost)}</span>' if proj_cost > 0 else ""

    return (
        f'<div class="proj-section" data-proj="{proj}">\n'
        f'  <div class="proj-head" onclick="this.closest(\'.proj-section\').classList.toggle(\'open\')">\n'
        f'    <span class="proj-arrow">▶</span>\n'
        f'    <span class="proj-num">[{proj}]</span>\n'
        f'    <span class="proj-label">{html_lib.escape(label)}</span>\n'
        f'    <div class="proj-summary">'
        f'<div class="adopt-bar-wrap proj-bar"><div class="adopt-bar" style="width:{proj_pct}%;background:{color}"></div></div>'
        f'<span class="adopt-pct" style="color:{color}">{proj_pct}% adoption</span>'
        f'<span class="proj-counts">{proj_ff_since} FF / {proj_total_since} tickets since Jun 2026</span>'
        f'{cost_html}'
        f'</div>\n'
        f'  </div>\n'
        f'  <div class="proj-body">\n'
        f'    <table class="init-table">\n'
        f'      <thead><tr>'
        f'<th>Initiative</th><th>FF Adoption</th><th>%</th>'
        f'<th>FF / Total</th><th>Status</th><th>AI Cost</th>'
        f'</tr></thead>\n'
        f'      <tbody>\n{rows}\n      </tbody>\n'
        f'    </table>\n'
        f'  </div>\n'
        f'</div>\n'
    )


def build_summary_cards(stats, all_months):
    total_all   = sum(s["total"]       for s in stats.values())
    total_ff    = sum(s["ff"]          for s in stats.values())
    total_since = sum(s["total_since"] for s in stats.values())
    ff_since    = sum(s["ff_since"]    for s in stats.values())
    pct         = round(ff_since / total_since * 100) if total_since > 0 else 0
    total_cost  = sum(s["ai_cost"]     for s in stats.values())
    active      = sum(1 for s in stats.values() if s["total"] > 0)
    color       = pct_color(pct)
    return (
        f'<div class="summary-card purple"><div class="num">{total_all}</div><div class="lbl">Total CIL Tickets</div></div>\n'
        f'<div class="summary-card green"><div class="num">{total_ff}</div><div class="lbl">FlowForge Tickets</div></div>\n'
        f'<div class="summary-card amber"><div class="num" style="color:{color}">{pct}%</div><div class="lbl">FF Adoption (since Jun 2026)</div></div>\n'
        f'<div class="summary-card blue"><div class="num">{active}</div><div class="lbl">Active Initiatives</div></div>\n'
        f'<div class="summary-card gold"><div class="num">{_cost_str(total_cost)}</div><div class="lbl">Total AI Cost (FF tickets)</div></div>'
    )


def build_chart_data(monthly, all_months):
    proj_colors = {"15803": "#6366f1", "15820": "#f59e0b", "15832": "#10b981"}
    lines = []
    for proj, color in proj_colors.items():
        if proj not in monthly:
            continue
        ff_vals    = [monthly[proj].get(ym, {}).get("ff",    0)   for ym in all_months]
        total_vals = [monthly[proj].get(ym, {}).get("total", 0)   for ym in all_months]
        cost_vals  = [round(monthly[proj].get(ym, {}).get("cost", 0.0), 2) for ym in all_months]
        pct_vals   = [
            round(ff / t * 100) if t > 0 else 0
            for ff, t in zip(ff_vals, total_vals)
        ]
        lines.append(
            f'  "{proj}": {{"color":"{color}","label":"{PROJECT_LABELS[proj]}",'
            f'"ff":{ff_vals},"total":{total_vals},"pct":{pct_vals},"cost":{cost_vals}}}'
        )
    months_js = "[" + ",".join(f'"{m}"' for m in all_months) + "]"
    return f'window.CHART_DATA = {{\n  "months": {months_js},\n' + ",\n".join(lines) + "\n};\n"


# ── Template filler ───────────────────────────────────────────────────────────

SLOT_RE = re.compile(r'<!-- SLOT:(\w+) -->')


def fill_template(stats, monthly, all_months):
    with open(TEMPLATE_FILE) as f:
        html = f.read()

    proj_slugs = defaultdict(list)
    for slug, prod_key, proj, title, epics in INITIATIVES:
        proj_slugs[proj].append(slug)

    sections = ""
    for proj in ["15803", "15820", "15832"]:
        sections += build_project_section(proj, PROJECT_LABELS[proj], proj_slugs[proj], stats)

    today_str = date.today().strftime("%d %b %Y")

    replacements = {
        "last_pull":     today_str,
        "summary_cards": build_summary_cards(stats, all_months),
        "sections":      sections,
        "chart_data":    build_chart_data(monthly, all_months),
    }

    def replace_slot(m):
        name = m.group(1)
        if name not in replacements:
            sys.exit(f"ERROR: unknown slot '{name}' in template.html")
        return replacements[name]

    return SLOT_RE.sub(replace_slot, html)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Regenerate Last Mile Adoption Dashboard")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not JIRA_EMAIL or not JIRA_TOKEN:
        sys.exit("Set JIRA_EMAIL and JIRA_API_TOKEN environment variables")

    print("Fetching all CIL tickets for Last Mile epics…")
    all_tickets = fetch_all_tickets(ALL_EPIC_KEYS)
    all_tickets = [t for t in all_tickets if t["status"] != "Closed"]
    print(f"  {len(all_tickets)} tickets ({sum(t['is_flowforge'] for t in all_tickets)} FlowForge)")

    stats          = compute_stats(all_tickets)
    monthly, months = compute_monthly_adoption(all_tickets)

    if args.dry_run:
        total_all = sum(s["total"] for s in stats.values())
        ff_since  = sum(s["ff_since"] for s in stats.values())
        tot_since = sum(s["total_since"] for s in stats.values())
        pct       = round(ff_since / tot_since * 100) if tot_since else 0
        total_cost = sum(s["ai_cost"] for s in stats.values())
        print(f"  Adoption since Jun 2026: {pct}% ({ff_since}/{tot_since})")
        print(f"  Total AI cost: {_cost_str(total_cost)}")
        for slug, s in sorted(stats.items(), key=lambda x: -x[1]["pct_since"]):
            if s["total"] > 0:
                print(f"  {s['title'][:50]:<50} {s['pct_since']:3}%  FF:{s['ff']}/{s['total']}  cost:{_cost_str(s['ai_cost'])}")
        return

    print("Filling template…")
    new_html = fill_template(stats, monthly, months)
    with open(DASHBOARD_FILE, "w") as f:
        f.write(new_html)
    print(f"  Written {DASHBOARD_FILE} ({len(new_html):,} chars)")


if __name__ == "__main__":
    main()
