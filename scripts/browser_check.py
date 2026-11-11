"""Real browser → production bundle → API → SQLite → rendered outcome checks."""

import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="evidence/browser")
    args = parser.parse_args()
    output = ROOT / args.out
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        expect(page.get_by_role("heading", name="Handoff Queue", exact=True)).to_be_visible()
        checks.append("Production React bundle renders")
        if page.get_by_role("button", name="Run 15 supplied samples").count():
            page.screenshot(path=str(output / "empty.png"), full_page=True)
        page.get_by_role("button", name="Run conversation", exact=True).click()
        page.get_by_label("Conversation", exact=True).select_option("cv_0011")
        page.get_by_role("button", name="Execute script", exact=True).click()
        expect(page.get_by_role("heading", name="Conversation cv_0011", exact=True)).to_be_visible(timeout=60000)
        expect(page.get_by_text("clinical_urgent", exact=True)).to_be_visible()
        expect(page.get_by_text("No appointment was created, moved or cancelled.", exact=True)).to_be_visible()
        expect(page.locator(".tool-card code")).to_have_count(1)
        expect(page.locator(".tool-card code")).to_contain_text("escalate_to_human")
        page.get_by_text("Tool result", exact=True).click()
        checks.append("Runner sends caller script to backend and renders real urgent escalation with exactly one tool")
        page.screenshot(path=str(output / "conversation-detail.png"), full_page=True)
        page.get_by_role("button", name="Resolve handoff", exact=True).click()
        expect(page.get_by_role("button", name="Resolved", exact=True)).to_be_disabled()
        page.reload(wait_until="networkidle")
        response = page.request.get(args.url + "/api/runs").json()
        assert any(r["conversation_id"] == "cv_0011" and r["resolved"] for r in response["runs"])
        checks.append("Resolve persists in backend SQLite across reload")
        page.get_by_role("button", name="Run conversation", exact=True).click()
        page.get_by_label("Conversation", exact=True).select_option("cv_0002")
        page.get_by_role("button", name="Execute script", exact=True).click()
        expect(page.get_by_role("heading", name="Conversation cv_0002", exact=True)).to_be_visible(timeout=60000)
        expect(page.locator(".outcome dd").filter(has_text="booked").first).to_be_visible()
        expect(page.locator(".bubble").last).to_contain_text("2026-10-07")
        checks.append("Corrected booking reaches grounded committed outcome")
        page.get_by_role("button", name="Back to handoff queue").click()
        page.get_by_role("button", name="All runs", exact=True).click()
        expect(page.get_by_role("button", name="cv_0002", exact=True).first).to_be_visible()
        page.screenshot(path=str(output / "handoff-queue.png"), full_page=True)
        checks.append("Sidebar, queue filters and conversation navigation work")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        checks.append("390px mobile viewport has no document overflow")
        # A real failed API response must surface as a visible error.
        page.route(
            "**/api/run",
            lambda route: route.fulfill(
                status=503, content_type="application/json", body='{"detail":"Simulated backend unavailable"}'
            ),
        )
        page.get_by_role("button", name="Run conversation", exact=True).click()
        page.get_by_role("button", name="Execute script", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Simulated backend unavailable")
        checks.append("Backend failure is shown, not a fabricated success")
        browser.close()
    report = {"passed": len(checks), "checks": checks, "console_errors": failures, "url": args.url}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    assert not failures, failures


if __name__ == "__main__":
    main()
