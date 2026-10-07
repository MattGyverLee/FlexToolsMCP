"""Type-aware LCM member detection (follow-up to the bridge/reverse-map fix).

Name-shape detection recognised a property by its suffix (`SensesOS`, `MsaRA`)
or membership of a 14-name list. LCM has 1,522 distinct property names and
1,140 are not suffix-shaped, so `ITsString.Text`, `ILexEntry.HomographNumber`
and `ILexSense.ScientificName` were all invisible.

These tests pin the four inference routes that make a receiver's type known,
the qualified `member_access` output that turns member coverage into a
measurement, and the degradation path when no LibLCM index is present.
"""

import ast

import pytest

from flextoolsmcp import flexicon_analyzer as fa
from flextoolsmcp.lcm_type_index import LcmTypeIndex, load_lcm_type_index


@pytest.fixture(scope="module")
def idx():
    index = load_lcm_type_index()
    if not index:
        pytest.skip("LibLCM index not present in this checkout")
    return index


def _analyze(src, imports=None):
    return fa.extract_lcm_calls(ast.parse(src).body[0], imports or [])


# ---------------------------------------------------------------------------
# the four seeding routes
# ---------------------------------------------------------------------------

def test_annotation_seeds_type(idx):
    env = fa._seed_lcm_types(ast.parse(
        "def f(self, sense: ILexSense):\n    pass\n").body[0], [], idx)
    assert env["sense"] == "ILexSense"


def test_docstring_args_seed_type(idx):
    """flexicon never annotates LCM params; the Args: block is the only place
    the interface is named."""
    src = '''
def GetScientificName(self, sense_or_hvo):
    """Get the scientific name.

    Args:
        sense_or_hvo: The ILexSense object or HVO.
    """
    return sense_or_hvo.ScientificName
'''
    env = fa._seed_lcm_types(ast.parse(src).body[0], [], idx)
    assert env["sense_or_hvo"] == "ILexSense"


def test_relationship_traversal_types_loop_variable(idx):
    src = '''
def f(self, entry: ILexEntry):
    for s in entry.SensesOS:
        x = s.Definition
'''
    env = fa._seed_lcm_types(ast.parse(src).body[0], [], idx)
    assert env["s"] == "ILexSense"


def test_factory_create_types_result(idx):
    src = '''
def f(self):
    fac = ILexSenseFactory
    made = fac.Create()
'''
    env = fa._seed_lcm_types(ast.parse(src).body[0], [{"name": "ILexSenseFactory"}], idx)
    assert env["made"] == "ILexSense"


def test_private_resolver_preserves_argument_type(idx):
    """`sense = self.__GetSenseObject(sense_or_hvo)` is flexicon's dominant
    idiom: accept object-or-HVO, hand back the object."""
    src = '''
def f(self, sense_or_hvo):
    """Doc.

    Args:
        sense_or_hvo: The ILexSense object or HVO.
    """
    sense = self.__GetSenseObject(sense_or_hvo)
    return sense.ScientificName
'''
    env = fa._seed_lcm_types(ast.parse(src).body[0], [], idx)
    assert env["sense"] == "ILexSense"


def test_ordinary_method_does_not_preserve_type(idx):
    """GetAll(entry) returns senses, not entries - the identity rule must not
    fire on it, or every wrapper method would poison the environment."""
    src = '''
def f(self, entry: ILexEntry):
    things = self.GetAll(entry)
'''
    env = fa._seed_lcm_types(ast.parse(src).body[0], [], idx)
    assert "things" not in env


# ---------------------------------------------------------------------------
# what the detection now yields
# ---------------------------------------------------------------------------

def test_plain_named_properties_are_detected(idx):
    """These carry no LCM suffix and are not in COMMON_LCM_PROPERTIES, so
    name-shape detection could never see them."""
    src = '''
def f(self, sense: ILexSense, entry: ILexEntry):
    a = sense.ScientificName
    b = sense.Bibliography
    c = entry.HomographNumber
'''
    props = _analyze(src)["properties_accessed"]
    assert {"ScientificName", "Bibliography", "HomographNumber"} <= set(props)


def test_member_access_is_qualified_and_attributed_to_declaring_type(idx):
    src = '''
def f(self, sense: ILexSense):
    g = sense.Gloss
    h = sense.Hvo
'''
    out = _analyze(src)
    assert "ILexSense.Gloss" in out["member_access"]
    # Hvo is declared on ICmObject, not ILexSense; attributing it to the
    # subtype would overstate that subtype's covered surface.
    assert not any(m == "ILexSense.Hvo" for m in out["member_access"])


def test_kind_comes_from_the_index_not_the_suffix(idx):
    out = _analyze("def f(self, entry: ILexEntry):\n    s = entry.SensesOS\n")
    assert out["property_kinds"]["SensesOS"] == "OwningSequence"


def test_no_annotated_spellings_leak(idx):
    out = _analyze("def f(self, entry: ILexEntry):\n    s = entry.SensesOS\n")
    assert [p for p in out["properties_accessed"] if "(" in p] == []


# ---------------------------------------------------------------------------
# degradation
# ---------------------------------------------------------------------------

def test_empty_index_is_falsy_and_safe():
    empty = LcmTypeIndex()
    assert not empty
    assert empty.sole_owner("Gloss") is None
    assert empty.declaring_type("ILexSense", "Gloss") is None


def test_uninformative_base_types_are_not_used_for_attribution(idx):
    """Typing a receiver as ICmObject would let Hvo/Guid/ClassName masquerade
    as domain coverage on every object in the model."""
    assert idx.sole_owner("Hvo") is None


def test_getattr_with_string_literal_is_detected(idx):
    """Dynamic access leaves no ast.Attribute node. flexicon uses it 273 times;
    POSOperations.GetStemNameText reads getattr(stem_name, "Name", None), which
    is why IMoStemName read as untouched despite 18 mentions in the source."""
    src = '''
def f(self, stem_name_or_hvo):
    """Doc.

    Args:
        stem_name_or_hvo: The IMoStemName object or HVO.
    """
    stem_name = self.__ResolveStemName(stem_name_or_hvo)
    ms = getattr(stem_name, "Name", None)
    ab = getattr(stem_name, "Abbreviation", None)
    return ms, ab
'''
    out = _analyze(src)
    assert "IMoStemName.Name" in out["member_access"]
    assert "IMoStemName.Abbreviation" in out["member_access"]
