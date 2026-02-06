#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build semantic search embeddings for FlexTools MCP.

Uses sentence-transformers to generate embeddings for all methods and entities,
enabling natural language search queries.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    import faiss
except ImportError:
    print("[ERROR] Required packages not installed. Run: pip install sentence-transformers faiss-cpu")
    sys.exit(1)


# Default model - small and fast, good for semantic search
DEFAULT_MODEL = "all-MiniLM-L6-v2"


def get_index_dir() -> Path:
    """Get the index directory path."""
    return Path(__file__).parent.parent / "index"


def load_flexlibs_data() -> Tuple[Dict, Dict]:
    """Load FlexLibs stable and 2.0 API data."""
    index_dir = get_index_dir()

    flexlibs_stable = {}
    flexlibs2 = {}

    stable_path = index_dir / "flexlibs" / "flexlibs_api.json"
    if stable_path.exists():
        with open(stable_path, "r", encoding="utf-8") as f:
            flexlibs_stable = json.load(f)

    flexlibs2_path = index_dir / "flexlibs" / "flexlibs2_api.json"
    if flexlibs2_path.exists():
        with open(flexlibs2_path, "r", encoding="utf-8") as f:
            flexlibs2 = json.load(f)

    return flexlibs_stable, flexlibs2


def load_liblcm_data() -> Dict:
    """Load LibLCM API data."""
    index_dir = get_index_dir()
    liblcm_path = index_dir / "liblcm" / "flex-api-enhanced.json"

    if liblcm_path.exists():
        with open(liblcm_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def create_method_text(entity_name: str, method: Dict, source: str) -> str:
    """Create searchable text for a method."""
    parts = []

    # Method name with entity context
    name = method.get("name", "")
    parts.append(f"{entity_name} {name}")

    # Description and summary
    desc = method.get("description", "")
    summary = method.get("summary", "")
    if summary and summary != desc:
        parts.append(summary)
    if desc:
        parts.append(desc)

    # Parameters
    for param in method.get("parameters", []):
        param_desc = param.get("description", "")
        if param_desc:
            parts.append(f"{param.get('name', '')} {param_desc}")

    # Return type
    return_type = method.get("return_type", "")
    if return_type:
        parts.append(f"returns {return_type}")

    # Usage hint
    usage = method.get("usage_hint", "")
    if usage:
        parts.append(usage)

    return " ".join(parts)


def create_entity_text(entity_name: str, entity: Dict, source: str) -> str:
    """Create searchable text for an entity."""
    parts = [entity_name]

    desc = entity.get("description", "")
    if desc:
        parts.append(desc)

    summary = entity.get("summary", "")
    if summary and summary != desc:
        parts.append(summary)

    category = entity.get("category", "")
    if category:
        parts.append(f"category {category}")

    usage = entity.get("usage_hint", "")
    if usage:
        parts.append(usage)

    return " ".join(parts)


def extract_searchable_items(flexlibs_stable: Dict, flexlibs2: Dict, liblcm: Dict) -> List[Dict]:
    """Extract all searchable items with their text representations."""
    items = []

    # FlexLibs stable methods
    for entity_name, entity in flexlibs_stable.get("entities", {}).items():
        for method in entity.get("methods", []):
            text = create_method_text(entity_name, method, "flexlibs_stable")
            items.append({
                "id": f"flexlibs_stable:{entity_name}.{method['name']}",
                "source": "flexlibs_stable",
                "entity": entity_name,
                "name": method["name"],
                "type": "method",
                "text": text,
                "signature": method.get("signature", ""),
                "description": method.get("description", ""),
                "category": entity.get("category", "general"),
            })

    # FlexLibs 2.0 methods
    for entity_name, entity in flexlibs2.get("entities", {}).items():
        # Entity itself
        entity_text = create_entity_text(entity_name, entity, "flexlibs2")
        items.append({
            "id": f"flexlibs2:{entity_name}",
            "source": "flexlibs2",
            "entity": entity_name,
            "name": entity_name,
            "type": "entity",
            "text": entity_text,
            "description": entity.get("description", ""),
            "category": entity.get("category", "general"),
        })

        # Methods
        for method in entity.get("methods", []):
            text = create_method_text(entity_name, method, "flexlibs2")
            items.append({
                "id": f"flexlibs2:{entity_name}.{method['name']}",
                "source": "flexlibs2",
                "entity": entity_name,
                "name": method["name"],
                "type": "method",
                "text": text,
                "signature": method.get("signature", ""),
                "description": method.get("description", ""),
                "category": entity.get("category", "general"),
            })

    # LibLCM entities (top-level only, not all methods)
    for entity_name, entity in liblcm.get("entities", {}).items():
        entity_text = create_entity_text(entity_name, entity, "liblcm")
        items.append({
            "id": f"liblcm:{entity_name}",
            "source": "liblcm",
            "entity": entity_name,
            "name": entity_name,
            "type": "entity",
            "text": entity_text,
            "description": entity.get("description", ""),
            "category": entity.get("category", "general"),
        })

    return items


def build_embeddings(items: List[Dict], model_name: str = DEFAULT_MODEL) -> Tuple[np.ndarray, List[Dict]]:
    """Generate embeddings for all items."""
    print(f"[INFO] Loading model: {model_name}")
    model = SentenceTransformer(model_name)

    print(f"[INFO] Generating embeddings for {len(items)} items...")
    texts = [item["text"] for item in items]

    # Generate embeddings in batches
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    return embeddings, items


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """Build a FAISS index for fast similarity search."""
    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)

    # Create index (Inner Product = cosine similarity after normalization)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    return index


def save_embeddings(embeddings: np.ndarray, items: List[Dict], index_dir: Path):
    """Save embeddings and metadata."""
    embeddings_dir = index_dir / "embeddings"
    embeddings_dir.mkdir(exist_ok=True)

    # Save embeddings as numpy array
    np.save(embeddings_dir / "embeddings.npy", embeddings)

    # Save metadata
    metadata = {
        "_schema": "semantic-search/1.0",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_model": DEFAULT_MODEL,
        "items": items,
        "statistics": {
            "total_items": len(items),
            "embedding_dimension": embeddings.shape[1],
            "sources": {
                "flexlibs_stable": len([i for i in items if i["source"] == "flexlibs_stable"]),
                "flexlibs2": len([i for i in items if i["source"] == "flexlibs2"]),
                "liblcm": len([i for i in items if i["source"] == "liblcm"]),
            },
            "types": {
                "method": len([i for i in items if i["type"] == "method"]),
                "entity": len([i for i in items if i["type"] == "entity"]),
            }
        }
    }

    with open(embeddings_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # Save FAISS index
    faiss.normalize_L2(embeddings)  # Re-normalize since we loaded from file
    index = build_faiss_index(embeddings.copy())
    faiss.write_index(index, str(embeddings_dir / "faiss.index"))

    print(f"[INFO] Saved embeddings to: {embeddings_dir}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build semantic search embeddings")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Sentence transformer model name")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: index/)")

    args = parser.parse_args()

    print("=" * 60)
    print("Building Semantic Search Embeddings")
    print("=" * 60)

    # Load data
    print("\n[INFO] Loading API indexes...")
    flexlibs_stable, flexlibs2 = load_flexlibs_data()
    liblcm = load_liblcm_data()

    print(f"  FlexLibs stable: {len(flexlibs_stable.get('entities', {}))} entities")
    print(f"  FlexLibs 2.0: {len(flexlibs2.get('entities', {}))} entities")
    print(f"  LibLCM: {len(liblcm.get('entities', {}))} entities")

    # Extract searchable items
    print("\n[INFO] Extracting searchable items...")
    items = extract_searchable_items(flexlibs_stable, flexlibs2, liblcm)
    print(f"  Total items: {len(items)}")

    # Build embeddings
    print(f"\n[INFO] Building embeddings with model: {args.model}")
    embeddings, items = build_embeddings(items, args.model)
    print(f"  Embedding dimension: {embeddings.shape[1]}")

    # Save
    index_dir = Path(args.output_dir) if args.output_dir else get_index_dir()
    save_embeddings(embeddings, items, index_dir)

    print("\n" + "=" * 60)
    print("[DONE] Embeddings built successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
