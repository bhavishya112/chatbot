"""
Consumes the JSON produced by the new extract_ui_tree() scraper and:
  1. Flattens the nested {desktop: {...body tree...}, mobile: {...body tree...}}
     structure into flat rows with a human-readable breadcrumb "path" per element.
  2. Embeds each row and stores it in a local Chroma vector DB.
  3. Provides a query() function to test retrieval.

Usage:
    python flatten_and_index.py snapshot.json --page leave
    python flatten_and_index.py snapshot.json --page leave --query "why isn't the submit button working"

Requires:
    pip install chromadb sentence-transformers --break-system-packages

NOTE ON SCHEMA CHANGE vs. the old ui_scraper.py:
  - Each view (desktop/mobile) is now a SINGLE root node (the <body> tree),
    not {"sections": [...], "discovered_states": [...]}. There is no more
    AJAX/tab/modal state discovery, so the old "state" field is always None
    now (kept in the row schema for backwards compatibility with any
    existing DB / downstream code that expects the key).
  - Nodes now carry tagName / id / className / role / text / children
    instead of label / tag / type / selector / position / visible.
  - `element.innerText` includes ALL descendant text, so a node's raw
    "text" field duplicates everything beneath it (e.g. the body node's
    text is the entire page). We compute each node's *own* text
    (its text with its children's text subtracted out) and use that for
    the embedding document and the breadcrumb label, to avoid massive
    duplication/noise in the vector index. The full (raw) text is still
    kept in metadata, truncated, in case it's useful for debugging.

"""

import logging, traceback

logger = logging.getLogger(__name__)

logging.basicConfig(
    filename="logs/ai_backend.log",
    filemode="a",  # 'a' appends new logs; 'w' overwrites each run
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    datefmt="%H:%M %d %B",
    encoding="utf-8",
)

import argparse
import json
import uuid

import chromadb

from openai import OpenAI

openaiclient = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

MODEL_NAME = "all-minilm:l6-v2"  # small, fast, good enough for UI-label matching
COLLECTION_NAME = "ui_elements"

FULL_TEXT_TRUNCATE = 300  # cap on raw innerText stored in metadata


# ---------------------------------------------------------------------------
# Step 1: Flatten
# ---------------------------------------------------------------------------


def _own_text(node: dict) -> str:
    """
    element.innerText includes all descendant text, so subtract out the
    concatenation of each child's own text to approximate the text that
    "belongs" to this node alone (e.g. a button's own label, not everything
    inside every nested element too).
    """
    full = (node.get("text") or "").strip()
    if not full:
        return ""

    children = node.get("children") or []
    child_texts = [(c.get("text") or "").strip() for c in children if c]
    child_texts = [t for t in child_texts if t]

    if not child_texts:
        return full

    combined_children = " ".join(child_texts)
    # Best-effort subtraction: innerText concatenates children in order with
    # newlines, so a simple substring removal handles the common case.
    remainder = full
    for t in child_texts:
        remainder = remainder.replace(t, "")
    remainder = " ".join(remainder.split())  # collapse whitespace

    return remainder


def _label_for(node: dict, own_text: str) -> str:
    """Pick the most human-identifiable label for a node."""
    if own_text:
        # keep it short for breadcrumbs
        return own_text[:60]
    if node.get("id"):
        return f"#{node['id']}"
    if node.get("role"):
        return f"[{node['role']}]"
    class_name = node.get("className")
    if class_name:
        first_class = str(class_name).split()[0]
        return f".{first_class}"
    return node.get("tagName") or "unnamed"


def _pseudo_selector(node: dict) -> str:
    """Best-effort CSS-like selector since the new scraper doesn't provide one."""
    tag = node.get("tagName") or "*"
    if node.get("id"):
        return f"{tag}#{node['id']}"
    class_name = node.get("className")
    if class_name:
        classes = ".".join(str(class_name).split())
        return f"{tag}.{classes}"
    return tag


def flatten(node, path, page: str, description: str, view="desktop", rows=None):
    """
    Walks the nested tagName/children tree produced by the new scraper
    and returns a flat list of dict rows, one per element, each carrying
    a breadcrumb "path" that encodes the hierarchy (no graph DB needed).
    """
    if rows is None:
        rows = []

    if not node:
        return rows

    own_text = _own_text(node)
    label = _label_for(node, own_text)
    current_path = f"{path} > {label}" if path else label

    rows.append(
        {
            "id": str(uuid.uuid4()),
            "page": page,
            "description": description,
            "view": view,
            "state": None,  # no AJAX/state discovery in the new scraper
            "path": current_path,
            "label": label,
            "tag": node.get("tagName"),
            "type": node.get("role"),  # closest analogue to the old "type" field
            "element_id": node.get("id"),
            "class_name": node.get("className"),
            "text": own_text,
            "full_text": (node.get("text") or "")[:FULL_TEXT_TRUNCATE],
            "selector": _pseudo_selector(node),
            "position": node.get("position"),  # not provided by the new scraper
            "size": node.get("size"),
            "visible": node.get("visible"),
            "color": node.get("color"),
        }
    )

    for child in node.get("children") or []:
        flatten(child, current_path, page, view, rows)

    return rows


def flatten_snapshot(snapshot: dict, page: str, description: str) -> list:
    """
    Flattens a full extract_ui_tree() output (desktop + mobile body trees)
    into one flat list of rows.
    """
    all_rows = []

    for view in ("desktop", "mobile"):
        root = snapshot.get(view)
        if not root:
            continue
        flatten(
            root, path="", page=page, description=description, view=view, rows=all_rows
        )

    return all_rows


# ---------------------------------------------------------------------------
# Step 2: Embed + store
# ---------------------------------------------------------------------------


def build_index(rows: list, db_path: str = "./data/vectordb/ui_vector_db2"):

    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    # searchable text = path + own text, this is what gets embedded
    documents = [
        f"{r['page']} : {r['description']}\ntext : {r['text']}".strip() for r in rows
    ]
    response = openaiclient.embeddings.create(input=documents, model=MODEL_NAME)
    embeddings = [emb.embedding for emb in response.data]

    ids = [r["id"] for r in rows]
    metadatas = []
    for r in rows:
        # Chroma metadata values must be str/int/float/bool (or None)
        meta = dict(r)
        meta.pop("id", None)
        for key, value in meta.items():
            if value is None:
                continue
            if not isinstance(value, (str, int, float, bool)):
                meta[key] = json.dumps(value)
        metadatas.append(meta)
    try:
        collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
    except Exception as e:
        logger.error(e)
        print(e)

        # print(traceback.print_exc())
    print(f"Indexed {len(rows)} elements into '{db_path}'")
    return collection


# ---------------------------------------------------------------------------
# Step 3: Query
# ---------------------------------------------------------------------------


def query(question: str, db_path: str = "data/vectordb/ui_vector_db2", top_k: int = 5):
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    response = openaiclient.embeddings.create(input=question, model=MODEL_NAME)
    embedding = [emb.embedding for emb in response.data]
    results = collection.query(query_embeddings=embedding, n_results=top_k)

    matches = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        meta = dict(meta)
        matches.append({"score": round(1 - dist, 3), "text": doc, **meta})

    return matches


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Flatten extract_ui_tree() output and index it for search"
    )
    parser.add_argument(
        "snapshot_file", help="Path to JSON produced by extract_ui_tree()"
    )
    parser.add_argument("--page", help="Logical page name, e.g. 'leave'")
    parser.add_argument(
        "--desc",
        help="features included in the page",
    )
    parser.add_argument(
        "--db",
        default="./data/vectordb/ui_vector_db2",
        help="Path to vector DB directory",
    )
    parser.add_argument(
        "--query", help="If provided, run a test query instead of (re)indexing"
    )
    args = parser.parse_args()

    if args.query:
        matches = query(args.query, db_path=args.db)
        print(json.dumps(matches, indent=2))
        return

    with open(args.snapshot_file, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    rows = flatten_snapshot(snapshot, page=args.page, description=args.desc)
    build_index(rows, db_path=args.db)


if __name__ == "__main__":
    main()
