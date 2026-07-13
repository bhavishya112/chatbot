"""
UI Scraper: section-by-section, pure-DOM extraction of a webpage's UI,
for both a desktop and a mobile viewport, plus auto-discovery of
hidden states (tabs/accordions/modals) revealed by clicking interactive
elements.

Usage:
    python ui_scraper.py https://example.com/leave -o result.json

Requires:
    pip install playwright --break-system-packages
    playwright install chromium
"""

import argparse
import json
import re
from playwright.sync_api import sync_playwright, Page

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}

MAX_DEPTH = 6  # how deep the DOM walk recurses
MAX_TRIGGERS_PER_PAGE = 25  # cap auto-click exploration
DANGEROUS_KEYWORDS = [
    "delete",
    "remove",
    "logout",
    "log out",
    "sign out",
    "submit",
    "pay",
    "confirm",
    "cancel",
    "unsubscribe",
    "deactivate",
]

# ---------------------------------------------------------------------------
# JS injected into the page to do the actual DOM walk.
# Runs entirely in-browser for accurate live geometry/visibility.
# ---------------------------------------------------------------------------

DOM_WALK_JS = r"""
(maxDepth) => {
  function isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function looksInteractive(el) {
    const tag = el.tagName.toLowerCase();
    if (['button', 'a', 'input', 'select', 'textarea', 'summary'].includes(tag)) return true;
    if (el.hasAttribute('onclick')) return true;
    if (el.getAttribute('tabindex') !== null) return true;
    const style = window.getComputedStyle(el);
    if (style.cursor === 'pointer') return true;
    return false;
  }

  function ownText(el) {
    let text = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
    }
    return text.trim();
  }

  function bestSelector(el) {
    if (el.id) return '#' + el.id;
    const dataAttrs = Array.from(el.attributes).filter(a => a.name.startsWith('data-'));
    if (dataAttrs.length) return `[${dataAttrs[0].name}="${dataAttrs[0].value}"]`;
    if (el.className && typeof el.className === 'string' && el.className.trim()) {
      const cls = el.className.trim().split(/\s+/)[0];
      return el.tagName.toLowerCase() + '.' + cls;
    }
    return el.tagName.toLowerCase();
  }

  function looksLikeSectionBreak(el, parent) {
    const tag = el.tagName.toLowerCase();
    const structural = ['header', 'nav', 'main', 'section', 'footer', 'aside', 'form', 'div'];
    if (!structural.includes(tag)) return false;
    const rect = el.getBoundingClientRect();
    if (rect.height <= 0) return false;
    // has a heading child -> likely a labeled section
    if (el.querySelector('h1,h2,h3,h4,h5,h6')) return true;
    // visually distinct from parent (background or border differs)
    if (parent) {
      const s1 = window.getComputedStyle(el);
      const s2 = window.getComputedStyle(parent);
      if (s1.backgroundColor !== s2.backgroundColor && s1.backgroundColor !== 'rgba(0, 0, 0, 0)') return true;
      if (s1.borderStyle !== 'none' && s1.borderStyle !== s2.borderStyle) return true;
    }
    return ['header', 'nav', 'main', 'footer', 'aside'].includes(tag);
  }

  function sectionLabel(el) {
    const heading = el.querySelector('h1,h2,h3,h4,h5,h6');
    if (heading) return heading.textContent.trim().slice(0, 80);
    const aria = el.getAttribute('aria-label');
    if (aria) return aria;
    const txt = ownText(el);
    if (txt) return txt.slice(0, 80);
    return null;
  }

  function serializeLeaf(el) {
    const rect = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || null,
      text: ownText(el).slice(0, 100),
      selector: bestSelector(el),
      position: {
        x: Math.round(rect.x),
        y: Math.round(rect.y + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      visible: isVisible(el),
    };
  }

  function walk(el, depth, parent, sectionIndexRef) {
    if (!el || depth > maxDepth) return null;
    if (['script', 'style', 'noscript', 'svg', 'link', 'meta'].includes(el.tagName.toLowerCase())) {
      return null;
    }
    if (!isVisible(el) && el.tagName.toLowerCase() !== 'body') {
      return null; // skip invisible subtrees (still discoverable via AJAX-trigger crawl separately)
    }

    const interactive = looksInteractive(el);
    const isSection = looksLikeSectionBreak(el, parent);

    // Leaf: interactive element -> capture directly, don't recurse further
    if (interactive && el.tagName.toLowerCase() !== 'form') {
      return serializeLeaf(el);
    }

    // Recurse into children
    const children = [];
    for (const child of el.children) {
      const node = walk(child, depth + 1, el, sectionIndexRef);
      if (node) children.push(node);
    }

    // Collapse pure single-child wrappers with no label to reduce noise
    if (!isSection && children.length === 1 && !sectionLabel(el)) {
      return children[0];
    }
    if (children.length === 0) return null;

    const label = sectionLabel(el) || (isSection ? `section_${sectionIndexRef.i++}` : null);
    const rect = el.getBoundingClientRect();

    return {
      label: label,
      tag: el.tagName.toLowerCase(),
      position: {
        x: Math.round(rect.x),
        y: Math.round(rect.y + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      children: children,
    };
  }

  const sectionIndexRef = { i: 1 };
  const root = walk(document.body, 0, null, sectionIndexRef);
  return root ? (root.children || [root]) : [];
}
"""

FIND_TRIGGERS_JS = r"""
() => {
  function isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  function looksInteractive(el) {
    const tag = el.tagName.toLowerCase();
    if (['button', 'a', 'summary'].includes(tag)) return true;
    if (el.hasAttribute('onclick')) return true;
    const style = window.getComputedStyle(el);
    if (style.cursor === 'pointer') return true;
    return false;
  }
  function bestSelector(el) {
    if (el.id) return '#' + el.id;
    const dataAttrs = Array.from(el.attributes).filter(a => a.name.startsWith('data-'));
    if (dataAttrs.length) return `[${dataAttrs[0].name}="${dataAttrs[0].value}"]`;
    return null; // skip elements we can't reliably re-select
  }
  const results = [];
  document.querySelectorAll('body *').forEach(el => {
    if (!isVisible(el)) return;
    if (!looksInteractive(el)) return;
    const sel = bestSelector(el);
    if (!sel) return;
    const text = (el.textContent || '').trim().slice(0, 60);
    results.push({ selector: sel, text });
  });
  return results;
}
"""

DOM_SIGNATURE_JS = """
() => {
  // cheap structural signature: count of visible elements + total text length
  const all = document.querySelectorAll('body *');
  let visibleCount = 0, textLen = 0;
  all.forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) visibleCount++;
  });
  textLen = document.body.innerText.length;
  return visibleCount + ':' + textLen;
}
"""


def is_dangerous(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in DANGEROUS_KEYWORDS)


def extract_sections(page: Page) -> list:
    return page.evaluate(DOM_WALK_JS, MAX_DEPTH)


def get_dom_signature(page: Page) -> str:
    return page.evaluate(DOM_SIGNATURE_JS)


def discover_states(page: Page, max_triggers=MAX_TRIGGERS_PER_PAGE) -> list:
    """
    Auto-click candidate interactive elements, diff DOM before/after,
    and record any newly revealed state as a separate snapshot.
    Skips dangerous actions (delete/submit/logout/etc.) and reverts
    (via Escape + reload-free back-click) between attempts where possible.
    """
    discovered_states = []
    triggers = page.evaluate(FIND_TRIGGERS_JS)

    seen_signatures = set()
    seen_signatures.add(get_dom_signature(page))

    count = 0
    for trigger in triggers:
        if count >= max_triggers:
            break
        if is_dangerous(trigger["text"]):
            continue
        selector = trigger["selector"]

        try:
            before_sig = get_dom_signature(page)
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            locator.click(timeout=2000, force=True)
            page.wait_for_timeout(300)  # let AJAX/animations settle
            after_sig = get_dom_signature(page)

            if after_sig != before_sig and after_sig not in seen_signatures:
                seen_signatures.add(after_sig)
                sections = extract_sections(page)
                discovered_states.append(
                    {
                        "trigger_selector": selector,
                        "trigger_text": trigger["text"],
                        "sections": sections,
                    }
                )

            # try to revert: Escape (closes modals/dropdowns) then click trigger again (toggles tab back)
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)

        except Exception:
            # trigger not clickable / detached / navigated away - skip it
            continue

        count += 1

    return discovered_states


def scrape_page(url: str, headless: bool = True) -> dict:
    result = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        for view_name, viewport in VIEWPORTS.items():
            page = browser.new_page(viewport=viewport)
            page.goto(url, timeout=30000)

            base_sections = extract_sections(page)
            states = discover_states(page)

            result[view_name] = {
                "url": url,
                "viewport": viewport,
                "sections": base_sections,
                "discovered_states": states,
            }

            page.close()

        browser.close()

    return result


def flatten(sections, path="", page="leave", view="desktop"):
    rows = []
    for node in sections:
        label = node.get("label") or node.get("text") or node.get("tag")
        current_path = f"{path} > {label}" if path else label
        rows.append(
            {
                "page": page,
                "view": view,
                "path": current_path,  # human-readable breadcrumb
                "label": label,
                "tag": node.get("tag"),
                "text": node.get("text", ""),
                "position": node.get("position"),
                "selector": node.get("selector"),
            }
        )
        if "children" in node:
            rows.extend(flatten(node["children"], current_path, page, view))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Section-wise pure-DOM UI scraper")
    parser.add_argument("url", help="URL of the page to scrape")
    parser.add_argument(
        "-o", "--output", default="ui_snapshot.json", help="Output JSON file path"
    )
    parser.add_argument(
        "--headed", action="store_true", help="Run browser in headed mode (debugging)"
    )
    args = parser.parse_args()

    data = scrape_page(args.url, headless=not args.headed)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved UI snapshot to {args.output}")


if __name__ == "__main__":
    main()
