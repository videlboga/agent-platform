#!/usr/bin/env python3
"""
e2e-screenshot.py — take screenshots with Playwright, diff against baseline.

Usage:
  python3 scripts/e2e-screenshot.py \
    --url http://localhost:8080 \
    --output screenshots/current/homepage.png \
    [--baseline screenshots/baseline/homepage.png] \
    [--viewport 1280,720] \
    [--wait 2] \
    [--selector "body"] \
    [--full-page]

Output: JSON to stdout, screenshot file to --output.
If --baseline is given, writes a diff image alongside the output (output + ".diff.png").
Exits 0 on success, 1 on diff > threshold.
"""
import argparse
import json
import os
import sys
import time

def parse_args():
    parser = argparse.ArgumentParser(description="Take and compare screenshots")
    parser.add_argument("--url", required=True, help="Page URL to capture")
    parser.add_argument("--output", required=True, help="Where to save the screenshot")
    parser.add_argument("--baseline", help="Baseline image for visual diff")
    parser.add_argument("--viewport", default="1280,720", help="Viewport WxH")
    parser.add_argument("--wait", type=float, default=2.0, help="Seconds to wait after load")
    parser.add_argument("--selector", default="body", help="CSS selector to screenshot")
    parser.add_argument("--full-page", action="store_true", help="Full page scroll screenshot")
    parser.add_argument("--threshold", type=float, default=0.05, help="Max diff ratio (0.0-1.0)")
    parser.add_argument("--diff-output", help="Custom path for diff image (default: output + .diff.png)")
    return parser.parse_args()


def take_screenshot(url, output, viewport, wait, selector, full_page):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            ignore_https_errors=True,
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

        time.sleep(wait)

        el = page.query_selector(selector)
        if not el:
            print(json.dumps({"status": "error", "error": f"Selector '{selector}' not found"}))
            sys.exit(1)

        if full_page:
            el.screenshot(path=output, full_page=True)
        else:
            el.screenshot(path=output)

        browser.close()
        return output


def diff_images(baseline_path, current_path, diff_output, threshold):
    from PIL import Image
    import pixelmatch

    im1 = Image.open(baseline_path).convert("RGBA")
    im2 = Image.open(current_path).convert("RGBA")

    # Resize if different dimensions
    if im1.size != im2.size:
        im2 = im2.resize(im1.size, Image.LANCZOS)

    w, h = im1.size
    diff_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    total = w * h

    diff_pixels = pixelmatch.contrib.pixelmatch(
        im1.tobytes(),
        im2.tobytes(),
        w, h,
        output=diff_img.tobytes(),
        threshold=0.1,
    )

    # pixelmatch returns pixel count; save the diff
    diff_img.save(diff_output)

    ratio = diff_pixels / total if total > 0 else 0
    return ratio, diff_pixels, total


def main():
    args = parse_args()
    viewport = tuple(int(x) for x in args.viewport.split(","))

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # Take screenshot
    result = take_screenshot(
        url=args.url,
        output=args.output,
        viewport=viewport,
        wait=args.wait,
        selector=args.selector,
        full_page=args.full_page,
    )

    output_data = {
        "status": "ok",
        "screenshot": result,
        "viewport": args.viewport,
        "selector": args.selector,
    }

    # Diff against baseline if provided
    if args.baseline and os.path.exists(args.baseline):
        diff_out = args.diff_output or (args.output + ".diff.png")
        ratio, diff_pixels, total = diff_images(args.baseline, args.output, diff_out, args.threshold)

        output_data["diff"] = {
            "baseline": args.baseline,
            "diff_image": diff_out,
            "diff_pixels": diff_pixels,
            "total_pixels": total,
            "ratio": round(ratio, 4),
            "threshold": args.threshold,
            "passed": ratio <= args.threshold,
        }

        if ratio > args.threshold:
            output_data["status"] = "diff_failed"
    elif args.baseline:
        output_data["warning"] = f"Baseline not found: {args.baseline}"

    print(json.dumps(output_data, indent=2))

    if output_data.get("status") == "diff_failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
