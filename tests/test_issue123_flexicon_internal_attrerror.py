"""Issue #123: flexicon-internal AttributeError must not become PolymorphicAttributeError."""

from flextoolsmcp.server.validators import (
    attribute_error_raising_frame,
    detect_flexicon_internal_attribute_error,
    detect_polymorphic_error,
    split_runner_error_and_traceback,
)


def test_split_runner_error_and_traceback():
    raw = (
        "Execution error: 'ILcmServiceLocator' object has no attribute 'GetInstance'\n"
        "Traceback (most recent call last):\n"
        '  File "<string>", line 3, in Main\n'
        '  File "/usr/lib/site-packages/flexicon/code/FLExProject.py", line 4576, in LexiconAddComplexForm\n'
        "    factory = self.project.ServiceLocator.GetInstance(ILexEntryRefFactory)\n"
        "AttributeError: 'ILcmServiceLocator' object has no attribute 'GetInstance'\n"
    )
    msg, tb = split_runner_error_and_traceback(raw)
    assert "GetInstance" in msg
    assert "FLExProject.py" in tb


def test_attribute_error_raising_frame_innermost_is_flexicon():
    tb = (
        "Traceback (most recent call last):\n"
        '  File "<string>", line 3, in Main\n'
        '  File "/opt/pyflexicon/flexicon/code/FLExProject.py", line 4576, in LexiconAddComplexForm\n'
        "    factory = self.project.ServiceLocator.GetInstance(ILexEntryRefFactory)\n"
    )
    frame = attribute_error_raising_frame(tb)
    assert frame is not None
    assert frame["line"] == 4576
    assert frame["function"] == "LexiconAddComplexForm"


def test_detect_flexicon_internal_attribute_error():
    raw = (
        "Execution error: 'ILcmServiceLocator' object has no attribute 'GetInstance'\n"
        "Traceback (most recent call last):\n"
        '  File "<string>", line 3, in Main\n'
        '  File "/usr/lib/site-packages/flexicon/code/FLExProject.py", line 4576, in LexiconAddComplexForm\n'
        "    factory = self.project.ServiceLocator.GetInstance(ILexEntryRefFactory)\n"
    )
    result = detect_flexicon_internal_attribute_error(raw)
    assert result["is_wrapper_internal"] is True
    assert result["object_type"] == "ILcmServiceLocator"
    assert result["property_name"] == "GetInstance"
    assert "flexicon#272" in result["suggestion"]
    assert "No cast" in result["suggestion"]


def test_user_frame_still_polymorphic():
    raw = "'ILexEntry' object has no attribute 'HeadWord'"
    assert detect_flexicon_internal_attribute_error(raw)["is_wrapper_internal"] is False
    assert detect_polymorphic_error(raw)["is_polymorphic_error"] is True


def test_user_string_frame_not_wrapper_internal():
    raw = (
        "Execution error: 'ILexSense' object has no attribute 'Glosss'\n"
        "Traceback (most recent call last):\n"
        '  File "<string>", line 5, in Main\n'
        "AttributeError: 'ILexSense' object has no attribute 'Glosss'\n"
    )
    assert detect_flexicon_internal_attribute_error(raw)["is_wrapper_internal"] is False
