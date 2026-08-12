# Extraction asymmetry: `interfaces` vs. `base_classes` (inheritance-resolution, issues #85/#86)

`liblcm_extractor.py`'s type extraction does **not** treat interface and
class ancestry the same way. Implementers walking an entity's ancestors for
any purpose (inheritance merging, casting, navigation) will hit this:

| Field | Extractor call | Depth | Notes |
|---|---|---|---|
| `interfaces` | `t.GetInterfaces()` (`liblcm_extractor.py:698`) | **Full transitive closure** (minus `IDisposable`, `IEnumerable`, `IComparable`, filtered out before storing -- `liblcm_extractor.py:700`) -- .NET returns every interface the type implements, directly or via an ancestor. | One pass over `entity["interfaces"]` is sufficient; no recursive walk needed to find all interface ancestors. |
| `base_classes` | `t.BaseType` (`liblcm_extractor.py:695-696`) | **One level only** -- the immediate parent class, not the full class chain. | A class-inheritance chain more than one level deep requires an actual recursive walk; treating `base_classes` as already-flattened will silently miss grandparent-and-higher members. |

Both `properties` and `methods` are extracted with
`BindingFlags.DeclaredOnly` (`liblcm_extractor.py:656`) -- **own-declared
members only**. An entity's `properties`/`methods` lists never include
inherited members; any consumer that wants ancestor members (own or merged)
must read them from the ancestor entity's own record and combine explicitly.

This asymmetry is why an interface-ancestor walk is a single flat pass over
`interfaces` (cheap, cycle-free by construction) while a class-ancestor walk
needs a cycle-guarded loop following `base_classes` until it terminates at
`None`/`Object`.
