"""
Consumes the JSON produced by ui_scraper.py and:
  1. Flattens the nested {desktop: {...}, mobile: {...}} tree into flat rows
     with a human-readable breadcrumb "path" per element.
  2. Embeds each row and stores it in a local Chroma vector DB.
  3. Provides a query() function to test retrieval.

Usage:
    python flatten_and_index.py snapshot.json --page leave
    python flatten_and_index.py snapshot.json --page leave --query "why isn't the submit button working"

Requires:
    pip install chromadb sentence-transformers --break-system-packages
"""

import argparse
import json
import uuid

import chromadb
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"  # small, fast, good enough for UI-label matching
COLLECTION_NAME = "ui_elements"


# ---------------------------------------------------------------------------
# Step 1: Flatten
# ---------------------------------------------------------------------------


def flatten(nodes, path="", page="page", view="desktop", state=None, rows=None):
    """
    Walks the nested section/children tree produced by ui_scraper.py
    and returns a flat list of dict rows, one per element, each carrying
    a breadcrumb "path" that encodes the hierarchy (no graph DB needed).
    """
    if rows is None:
        rows = []

    for node in nodes:
        label = node.get("label") or node.get("text") or node.get("tag") or "unnamed"
        current_path = f"{path} > {label}" if path else label

        rows.append(
            {
                "id": str(uuid.uuid4()),
                "page": page,
                "view": view,
                "state": state,  # None for base page, else trigger_text of the AJAX state
                "path": current_path,
                "label": label,
                "tag": node.get("tag"),
                "type": node.get("type"),
                "text": node.get("text", "") or "",
                "selector": node.get("selector"),
                "position": node.get("position"),
                "visible": node.get("visible", True),
            }
        )

        if node.get("children"):
            flatten(node["children"], current_path, page, view, state, rows)

    return rows


def flatten_snapshot(snapshot: dict, page: str) -> list:
    """
    Flattens a full ui_scraper.py output (both desktop + mobile, including
    any auto-discovered AJAX states) into one flat list of rows.
    """
    all_rows = []

    for view in ("desktop", "mobile"):
        if view not in snapshot:
            continue
        view_data = snapshot[view]

        # base page sections
        all_rows.extend(
            flatten(view_data.get("sections", []), path="", page=page, view=view)
        )

        # each auto-discovered state (tab/modal/accordion reveal) gets tagged separately
        for state in view_data.get("discovered_states", []):
            state_name = state.get("trigger_text") or state.get("trigger_selector")
            all_rows.extend(
                flatten(
                    state.get("sections", []),
                    path="",
                    page=page,
                    view=view,
                    state=state_name,
                )
            )

    return all_rows


# ---------------------------------------------------------------------------
# Step 2: Embed + store
# ---------------------------------------------------------------------------


def build_index(rows: list, db_path: str = "./data/vectordb/ui_vector_db"):
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    # searchable text = path + label + text, this is what gets embedded
    documents = [f"{r['path']} {r['text']}".strip() for r in rows]
    embeddings = model.encode(documents).tolist()

    ids = [r["id"] for r in rows]
    metadatas = []
    for r in rows:
        # Chroma metadata values must be str/int/float/bool, so stringify position
        meta = dict(r)
        meta["position"] = (
            json.dumps(meta["position"]) if meta.get("position") else None
        )
        meta.pop("id", None)
        metadatas.append(meta)

    collection.upsert(
        ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
    )
    print(f"Indexed {len(rows)} elements into '{db_path}'")
    return collection


# ---------------------------------------------------------------------------
# Step 3: Query
# ---------------------------------------------------------------------------


def query(question: str, db_path: str = "data/vectordb/ui_vector_db", top_k: int = 5):
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    embedding = model.encode([question]).tolist()
    results = collection.query(query_embeddings=embedding, n_results=top_k)

    matches = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        meta = dict(meta)
        if meta.get("position"):
            meta["position"] = json.loads(meta["position"])
        matches.append({"score": round(1 - dist, 3), "text": doc, **meta})

    return matches


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Flatten ui_scraper.py output and index it for search"
    )
    parser.add_argument("snapshot_file", help="Path to JSON produced by ui_scraper.py")
    parser.add_argument(
        "--page", default="page", help="Logical page name, e.g. 'leave'"
    )
    parser.add_argument(
        "--db", default="./data/vectordb/ui_vector_db", help="Path to vector DB directory"
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

    rows = flatten_snapshot(snapshot, page=args.page)
    build_index(rows, db_path=args.db)


if __name__ == "__main__":
    main()
