import os
import os.path as path


def strip_php(srcpath: str) -> str:
    """Strip away php code from a file
    Args:
        srcpath: i.e. sourcepath -> like D:/path/to/file.php.
    Returns:
        htmlonly string.
    Example:
        >>> html = strip_php("D:/path/to/php/file.php")

    """
    import re

    with open(srcpath, "r", encoding="utf-8") as f:
        raw = f.read()

    match = re.search(r"<!DOCTYPE html|<html", raw, re.IGNORECASE)

    if match:
        raw = raw[match.start() :]

    html_only = re.sub(r"<\?(?:php|=).*?\?>", "", raw, flags=re.DOTALL)

    directory, filename = os.path.split(srcpath)

    # modified_dir = os.path.join(directory, "modified")

    # if not os.path.exists(modified_dir):
    #     os.mkdir(modified_dir)
    # new_path = os.path.join(modified_dir, filename)

    # with open(new_path, "w", encoding="utf-8") as f:
    #     f.write(html_only)
    return html_only, filename


from playwright.sync_api import sync_playwright


def extract_ui(htmlonly: str, filename: str):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(htmlonly, "html5lib")  # or "html5lib" if markup is messy

    ui_structure = {
        "page": filename,
        "forms": [],
        "buttons": [],
        "links": [],
        "headings": [],
        "tables": [],
        "inputs": [],
        "selects": [],
        "textareas": [],
        "cards": [],
        "modals": [],
        "navigation": [],
        "tabs": [],
        "breadcrumbs": [],
        "images": [],
        "alerts": [],
        "labels": [],
        "sections": [],
        "headers": [],
        "footers": [],
        "asides": [],
        "mains": [],
        "navs": [],
    }

    # Forms and their fields
    for form in soup.find_all("form"):
        fields = []
        for inp in form.find_all("input"):
            fields.append(
                {
                    "name": inp.get("name"),
                    "id": inp.get("id"),
                    "placeholder": inp.get("placeholder"),
                    "value": inp.get("value"),
                    "type": inp.get("type"),
                    "required": bool(inp.get("required")),
                }
            )
        ui_structure["forms"].append(
            {"id": form.get("id"), "action": form.get("action"), "fields": fields}
        )

    # Buttons
    for btn in soup.find_all("button"):
        ui_structure["buttons"].append(
            {
                "label": " ".join(btn.stripped_strings),
                "type": btn.get("type"),
                "position": "unknown",
            }
        )

    # Links
    for link in soup.find_all("a"):
        ui_structure["links"].append(
            {
                "label": link.text.strip(),
                "href": link.get("href"),
                "id": link.get("id"),
                "class": link.get("class"),
            }
        )

    # Headings (h1–h6)
    for level in range(1, 7):
        for heading in soup.find_all(f"h{level}"):
            ui_structure["headings"].append(
                {"level": level, "text": heading.text.strip()}
            )

    # Tables
    for table in soup.find_all("table"):
        ui_structure["tables"].append(
            {
                "id": table.get("id"),
                "rows": len(table.find_all("tr")),
                "columns": len(table.find_all("th")),
            }
        )

    # Inputs (outside forms too)
    for inp in soup.find_all("input"):
        ui_structure["inputs"].append(
            {
                "name": inp.get("name"),
                "type": inp.get("type"),
                "required": bool(inp.get("required")),
            }
        )

    # Select dropdowns
    for sel in soup.find_all("select"):
        options = [opt.text.strip() for opt in sel.find_all("option")]
        ui_structure["selects"].append({"name": sel.get("name"), "options": options})

    # Textareas
    for ta in soup.find_all("textarea"):
        ui_structure["textareas"].append(
            {"name": ta.get("name"), "placeholder": ta.get("placeholder")}
        )

    # Cards (common Bootstrap pattern)
    for card in soup.find_all(class_="card"):
        ui_structure["cards"].append(
            {
                "title": (
                    card.find(class_="card-title").text.strip()
                    if card.find(class_="card-title")
                    else None
                ),
                "content": (
                    card.find(class_="card-body").text.strip()
                    if card.find(class_="card-body")
                    else None
                ),
            }
        )

    # Modals
    for modal in soup.find_all(class_="modal"):
        ui_structure["modals"].append(
            {
                "id": modal.get("id"),
                "title": (
                    modal.find(class_="modal-title").text.strip()
                    if modal.find(class_="modal-title")
                    else None
                ),
            }
        )

    # Navigation bars
    for nav in soup.find_all("nav"):
        ui_structure["navigation"].append(
            {"id": nav.get("id"), "links": [a.text.strip() for a in nav.find_all("a")]}
        )

    # Tabs
    for tab in soup.find_all(class_="nav-tabs"):
        ui_structure["tabs"].append(
            {"tabs": [a.text.strip() for a in tab.find_all("a")]}
        )

    # Breadcrumbs
    for bc in soup.find_all(class_="breadcrumb"):
        ui_structure["breadcrumbs"].append(
            {"items": [li.text.strip() for li in bc.find_all("li")]}
        )

    # Images
    for img in soup.find_all("img"):
        ui_structure["images"].append({"src": img.get("src"), "alt": img.get("alt")})

    # Alerts (Bootstrap pattern)
    for alert in soup.find_all(class_="alert"):
        ui_structure["alerts"].append(
            {"type": " ".join(alert.get("class")), "text": alert.text.strip()}
        )

    # Labels
    for label in soup.find_all("label"):
        ui_structure["labels"].append(
            {"for": label.get("for"), "text": label.text.strip()}
        )

    # Sections

    for sec in soup.find_all("section"):
        ui_structure["sections"].append(
            {
                "id": sec.get("id"),
                "class": " ".join(sec.get("class", [])),
                "content_preview": sec.text.strip()[:100],  # first 100 chars
            }
        )

    # Headers
    for header in soup.find_all("header"):
        ui_structure["headers"].append(
            {
                "id": header.get("id"),
                "class": " ".join(header.get("class", [])),
                "content_preview": header.text.strip()[:100],
            }
        )

    # Footers
    for footer in soup.find_all("footer"):
        ui_structure["footers"].append(
            {
                "id": footer.get("id"),
                "class": " ".join(footer.get("class", [])),
                "content_preview": footer.text.strip()[:100],
            }
        )

    # Asides
    for aside in soup.find_all("aside"):
        ui_structure["asides"].append(
            {
                "id": aside.get("id"),
                "class": " ".join(aside.get("class", [])),
                "content_preview": aside.text.strip()[:100],
            }
        )

    # Mains
    for main in soup.find_all("main"):
        ui_structure["mains"].append(
            {
                "id": main.get("id"),
                "class": " ".join(main.get("class", [])),
                "content_preview": main.text.strip()[:100],
            }
        )

    # Navs
    for nav in soup.find_all("nav"):
        ui_structure["navs"].append(
            {
                "id": nav.get("id"),
                "class": " ".join(nav.get("class", [])),
                "links": [a.text.strip() for a in nav.find_all("a")],
            }
        )

    import json

    print(json.dumps(ui_structure, indent=2))


from playwright.sync_api import sync_playwright
import json

URL = "https://example.com"


def capture_ui(url):

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        page.goto("http://localhost")

        page.wait_for_url("**/dashboard.php", timeout=0)

        print("Logged in!")

        tree = page.evaluate(r"""
() => {

function visible(el){

    const s = getComputedStyle(el);

    if(s.display==="none") return false;
    if(s.visibility==="hidden") return false;
    if(parseFloat(s.opacity)===0) return false;

    const r = el.getBoundingClientRect();

    if(r.width<5 || r.height<5) return false;

    return true;
}

function label(el){

    return (
        el.getAttribute("aria-label") ||
        el.getAttribute("title") ||
        el.innerText.trim().split("\n")[0] ||
        el.placeholder ||
        el.alt ||
        el.tagName
    ).trim();
}

function node(el){

    const r = el.getBoundingClientRect();

    return {
        tag:el.tagName.toLowerCase(),
        label:label(el),
        x:r.x,
        y:r.y,
        width:r.width,
        height:r.height
    };
}

function controls(parent){

    const arr=[];

    parent.querySelectorAll(
        "button,input,select,textarea,a,img,[role=button]"
    ).forEach(el=>{

        if(!visible(el)) return;

        arr.push(node(el));

    });

    return arr;
}

function section(el,name){

    const rows={};

    [...el.children].forEach(child=>{

        if(!visible(child)) return;

        const y=Math.round(child.getBoundingClientRect().top/80);

        if(!rows[y]) rows[y]=[];

        rows[y].push(child);

    });

    const result={};

    Object.keys(rows).sort().forEach((k,i)=>{

        const row=[];

        rows[k]
        .sort((a,b)=>
            a.getBoundingClientRect().left-
            b.getBoundingClientRect().left
        )
        .forEach(card=>{

            row.push({

                title:label(card),

                controls:controls(card)

            });

        });

        result["Row "+(i+1)] = row;

    });

    return result;
}

const output={};

const header=document.querySelector("header");

if(header)
    output["Header"]=section(header,"Header");

const main=document.querySelector("main") || document.body;

output["Main"]=section(main,"Main");

const aside=document.querySelector("aside");

if(aside)
    output["Sidebar"]=section(aside,"Sidebar");

const footer=document.querySelector("footer");

if(footer)
    output["Footer"]=section(footer,"Footer");

return output;

}
""")

        browser.close()

        return tree


if __name__ == "__main__":
    # filepath = os.path.normpath("C:\\xampp\\htdocs\\version3\\stu_dash\\dashboard.php")
    # filepath = filepath.replace("\\", "/")
    # x = strip_php(filepath)
    # print(extract_ui(*x))
    ui = capture_ui("http://localhost/version3/stu_dash/dashboard.php")
    print(json.dumps(ui, indent=4))
