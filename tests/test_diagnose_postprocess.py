"""Synthetic report-shape test for the read-only post-process inspector."""
import enum
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class UFunction:
    pass


class Field:
    def __init__(self, name, kind):
        self.Name = name
        self.Class = types.SimpleNamespace(Name=kind)


class Cls:
    def __init__(self, path, fields):
        self.path, self.fields = path, fields
        self.ClassDefaultObject = None

    def _path_name(self):
        return self.path

    def _superfields(self):
        return [self]

    def _fields(self):
        return self.fields


class Obj:
    def __init__(self, path, cls, **values):
        self.path, self.Class = path, cls
        for key, value in values.items():
            setattr(self, key, value)

    def _path_name(self):
        return self.path


class DPG(enum.IntEnum):
    SDPG_World = 1
    SDPG_Foreground = 2


class DiagnosePostProcessTests(unittest.TestCase):
    def test_reports_chain_effects_without_invoking_functions(self):
        method = UFunction(); method.Name = 'RemovePostProcessingChain'
        method.Class = types.SimpleNamespace(Name='Function')
        effect_cls = Cls('Engine.UberPostProcessEffect',
                         [Field('SceneDPG', 'ByteProperty'), Field('bShowInGame', 'BoolProperty'), method])
        effect = Obj('Transient.Uber_0', effect_cls, SceneDPG=4, bShowInGame=True)
        chain_cls = Cls('Engine.PostProcessChain', [Field('Effects', 'ArrayProperty')])
        chain = Obj('Transient.PostProcessChain_1', chain_cls, Effects=[effect])
        effect_cls.ClassDefaultObject = Obj('Default__Uber', effect_cls, SceneDPG=4, bShowInGame=True)
        player = types.SimpleNamespace(PlayerPostProcess=chain, PlayerPostProcessChains=[chain])
        pc = types.SimpleNamespace(Pawn=object(), Player=player)
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as box:
            def find_class(name):
                if name == 'Engine.UberPostProcessEffect': return effect_cls
                raise ValueError(name)
            sdk = types.SimpleNamespace(find_class=find_class, find_enum=lambda name: DPG,
                                        logging=types.SimpleNamespace(info=lambda *_: None))
            modules = {'mods_base': types.SimpleNamespace(get_pc=lambda **_: pc), 'unrealsdk': sdk,
                       'unrealsdk.unreal': types.SimpleNamespace(UFunction=UFunction)}
            with patch.dict(sys.modules, modules), patch.dict('os.environ', {'BLACKLANDS_MAILBOX': box}):
                spec = importlib.util.spec_from_file_location('diagnose_postprocess_test',
                            ROOT/'adapters/bl2/blacklands_passthrough/diagnose_postprocess.py')
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
            report = json.loads((Path(box)/'blacklands_postprocess_api.json').read_text())
        self.assertTrue(report['readonly'])
        fields = report['player_chain']['effects'][0]['fields']
        self.assertEqual(fields['SceneDPG']['value'], 4)
        self.assertNotIn('RemovePostProcessingChain', fields)
        self.assertEqual(report['enums']['ESceneDepthPriorityGroup']['SDPG_World'], 1)
        self.assertIn('defaults', report['classes']['Engine.UberPostProcessEffect'])
        self.assertIn('unavailable', report['classes']['Engine.MaterialEffect'])


if __name__ == '__main__':
    unittest.main()
