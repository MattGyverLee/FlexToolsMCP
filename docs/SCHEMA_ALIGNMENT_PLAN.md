# Schema Alignment Plan

## Current Schema Comparison

### Entity-Level Fields

| Field | LibLCM (flex-api-enhanced) | FlexLibs (stable/2.0) | Action |
|-------|---------------------------|----------------------|--------|
| `id` | Yes | No (`name` instead) | Add `id` as alias |
| `name` | No | Yes | Keep (same as `id`) |
| `type` | Yes (interface/class) | Yes (class) | Already aligned |
| `namespace` | Yes | Yes | Already aligned |
| `category` | Yes | Yes | Already aligned |
| `description` | Yes | Yes | Already aligned |
| `summary` | Yes | Yes | Already aligned |
| `usage_hint` | Yes | **No** | **Generate from type/category** |
| `signature` | Yes | **No** | **Add entity signature** |
| `properties` | Yes (detailed) | Yes (basic) | Enhance property extraction |
| `methods` | Yes | Yes | See method-level below |
| `relationships` | Yes | **No** | **Extract from base_classes/deps** |
| `tags` | Yes | Yes | Already aligned |
| `source_file` | No | Yes | Keep (FlexLibs only) |
| `example` | No | Yes | Keep (FlexLibs only) |
| `base_classes` | No | Yes | Keep (FlexLibs only) |
| `lcm_dependencies` | No | Yes | Keep (FlexLibs only) |

### Method-Level Fields

| Field | LibLCM | FlexLibs | Action |
|-------|--------|----------|--------|
| `name` | Yes | Yes | Already aligned |
| `signature` | Yes (basic) | Yes (detailed) | Already aligned |
| `description` | Yes | Yes | Already aligned |
| `summary` | No | Yes | Keep (FlexLibs only) |
| `usage_hint` | Yes | **No** | **Generate from name/return_type** |
| `parameters` | No | Yes | Keep (FlexLibs only) |
| `returns` | No | Yes | Keep (FlexLibs only) |
| `return_type` | No | Yes | Keep (FlexLibs only) |
| `raises` | No | Yes | Keep (FlexLibs only) |
| `example` | No | Yes | Keep (FlexLibs only) |
| `lcm_mapping` | No | Yes | Keep (FlexLibs only) |

### Property-Level Fields (LibLCM has detailed, FlexLibs minimal)

| Field | LibLCM | FlexLibs | Action |
|-------|--------|----------|--------|
| `name` | Yes | Yes | Already aligned |
| `type` | Yes | **No** | **Add to FlexLibs** |
| `kind` | Yes | No | LibLCM only (OA/OS/RA/RS) |
| `relationship` | Yes | No | LibLCM only |
| `target_type` | Yes | No | LibLCM only |
| `is_multistring` | Yes | No | LibLCM only |
| `description` | Yes | **No** | **Add to FlexLibs** |

---

## Implementation Plan

### Phase 1: Add Missing Fields to FlexLibs Analyzer (Quick Wins)

1. **Add `id` field** - Simple alias for `name`
   ```python
   entity["id"] = entity["name"]
   ```

2. **Add `usage_hint` to entities** - Generate from type and category
   ```python
   entity["usage_hint"] = f"Class for working with {category} objects in FieldWorks"
   ```

3. **Add `usage_hint` to methods** - Generate from method name pattern
   ```python
   if method_name.startswith("Get"):
       usage_hint = "retrieval"
   elif method_name.startswith("Set"):
       usage_hint = "modification"
   elif method_name.startswith("Create"):
       usage_hint = "creation"
   elif method_name.startswith("Delete"):
       usage_hint = "deletion"
   ```

4. **Add `signature` to entities** - Class/function signature
   ```python
   entity["signature"] = f"class {name}({', '.join(base_classes)})"
   ```

5. **Add `relationships` to entities** - From base_classes and lcm_dependencies
   ```python
   relationships = []
   for base in base_classes:
       relationships.append({"type": "inherits", "target": base})
   for dep in lcm_dependencies:
       relationships.append({"type": "uses", "target": dep})
   ```

### Phase 2: Enhance Property Extraction in FlexLibs

Currently FlexLibs only extracts `@property` decorated methods as properties.
Need to extract:
- Property type (from return type or docstring)
- Property description (from docstring)

### Phase 3: Unified Schema Wrapper

Create a utility function that normalizes any API file to a common schema:

```python
def normalize_entity(entity, source_type):
    """Normalize entity to unified schema."""
    normalized = {
        "id": entity.get("id") or entity.get("name"),
        "name": entity.get("name") or entity.get("id"),
        "type": entity.get("type", "class"),
        "namespace": entity.get("namespace", ""),
        "category": entity.get("category", "general"),
        "description": entity.get("description", ""),
        "summary": entity.get("summary", ""),
        "usage_hint": entity.get("usage_hint") or generate_usage_hint(entity),
        "signature": entity.get("signature") or generate_signature(entity),
        "properties": entity.get("properties", []),
        "methods": [normalize_method(m) for m in entity.get("methods", [])],
        "relationships": entity.get("relationships") or extract_relationships(entity),
        "tags": entity.get("tags", []),
        # Source-specific fields (preserved)
        "source_file": entity.get("source_file"),
        "example": entity.get("example"),
        "base_classes": entity.get("base_classes"),
        "lcm_dependencies": entity.get("lcm_dependencies"),
    }
    return normalized
```

---

## Priority

1. **High Priority** (Essential for MCP server consistency):
   - Add `id` field
   - Add `usage_hint` to entities and methods
   - Add `relationships`

2. **Medium Priority** (Improves documentation):
   - Add `signature` to entities
   - Enhance property extraction with type/description

3. **Low Priority** (Nice to have):
   - Unified schema wrapper
   - Property kind/relationship info (requires deeper analysis)

---

## Estimated Effort

| Task | Effort | Impact |
|------|--------|--------|
| Add `id` field | 5 min | High |
| Add entity `usage_hint` | 15 min | High |
| Add method `usage_hint` | 15 min | Medium |
| Add entity `signature` | 10 min | Medium |
| Add `relationships` | 20 min | High |
| Enhance property extraction | 1 hour | Medium |
| Unified schema wrapper | 2 hours | Low |

**Total for Phase 1: ~1 hour**
