#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule B (issue #121 casting dataflow) must read the expected interface from the
called parameter, not only from the Operations class name.

SegmentOperations.GetAll(paragraph_or_hvo) takes the owning IStTxtPara. Before
this fix Rule B assumed every SegmentOperations method takes an ISegment and
hard-blocked the textbook paragraph -> segment walk.
"""

import unittest

from server.validators import detect_casting_needs


CASTING_INDEX = {
    "properties": {},
    "polymorphic_collections": {},
    "class_name_mapping": {
        "StTxtPara": "IStTxtPara",
        "Segment": "ISegment",
        "LexEntry": "ILexEntry",
    },
}


class _FakeAPIIndex:
    def __init__(self, get_all_param_desc="The IStTxtPara object or HVO."):
        self.flexicon = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "Paragraphs", "return_type": "StTxtParaOperations"},
                        {"name": "Segments", "return_type": "SegmentOperations"},
                    ],
                    "methods": [],
                },
                "StTxtParaOperations": {
                    "methods": [
                        {
                            "name": "GetAll",
                            "is_mutating": False,
                            "element_type": "IStTxtPara",
                            "polymorphic": True,
                        },
                    ]
                },
                "SegmentOperations": {
                    "methods": [
                        {
                            "name": "GetAll",
                            "is_mutating": False,
                            "parameters": [
                                {
                                    "name": "paragraph_or_hvo",
                                    "type": "",
                                    "description": get_all_param_desc,
                                }
                            ],
                        },
                        {
                            "name": "GetBaselineText",
                            "is_mutating": False,
                            "parameters": [
                                {
                                    "name": "segment_or_hvo",
                                    "type": "",
                                    "description": "The ISegment object or HVO.",
                                }
                            ],
                        },
                    ]
                },
            }
        }


WALK = (
    "for paragraph in project.Paragraphs.GetAll(text):\n"
    "    for segment in project.Segments.GetAll(paragraph):\n"
    "        pass\n"
)


def _rule_b_issues(result, method):
    return [i for i in result["casting_issues"] if i.get("property") == method]


class TestRuleBParameterInterface(unittest.TestCase):
    def test_owner_argument_documented_in_index_is_not_flagged(self):
        result = detect_casting_needs(WALK, CASTING_INDEX, api_index=_FakeAPIIndex())
        self.assertEqual(_rule_b_issues(result, "GetAll"), [], result)

    def test_keyword_argument_uses_the_named_parameter(self):
        code = (
            "for paragraph in project.Paragraphs.GetAll(text):\n"
            "    project.Segments.GetAll(paragraph_or_hvo=paragraph)\n"
        )
        result = detect_casting_needs(code, CASTING_INDEX, api_index=_FakeAPIIndex())
        self.assertEqual(_rule_b_issues(result, "GetAll"), [], result)

    def test_wrong_object_for_documented_parameter_still_flags(self):
        # A paragraph passed where the index documents an ISegment is still
        # a real cast risk.
        code = (
            "for paragraph in project.Paragraphs.GetAll(text):\n"
            "    project.Segments.GetBaselineText(paragraph)\n"
        )
        result = detect_casting_needs(code, CASTING_INDEX, api_index=_FakeAPIIndex())
        self.assertTrue(_rule_b_issues(result, "GetBaselineText"), result)

    def test_undocumented_parameter_falls_back_to_class_name(self):
        # No interface named in the parameter: keep the pre-fix behaviour.
        api_index = _FakeAPIIndex(get_all_param_desc="The paragraph or HVO.")
        result = detect_casting_needs(WALK, CASTING_INDEX, api_index=api_index)
        self.assertTrue(_rule_b_issues(result, "GetAll"), result)


if __name__ == "__main__":
    unittest.main()
