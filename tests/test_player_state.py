import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('player_state_test',ROOT/'adapters/bl2/blacklands_passthrough/player_state.py')
state=importlib.util.module_from_spec(spec);spec.loader.exec_module(state)

class PlayerStateTests(unittest.TestCase):
    def setUp(self):
        self.pool=NS(Definition=NS(Resource=NS(Name='Ammo_Grenade_Protean')),
                     GetCurrentValue=lambda:3.,GetMaxValue=lambda:5.,_path_name=lambda:'GrenadePool')
        self.pc=NS(Pawn=NS(_path_name=lambda:'Pawn',Weapon=None,
                    GetHealth=lambda:90.,GetMaxHealth=lambda:100.,GetShieldStrength=lambda:12.,GetMaxShieldStrength=lambda:50.,
                    InvManager=NS(BackpackInventoryCount=3,InventorySlotMax_Misc=18)),
                   PlayerReplicationInfo=NS(ExpLevel=10,ExpPointsNextLevelAt=1500),
                   ExpPool=NS(Data=NS(GetCurrentValue=lambda:1234.,GetMaxValue=lambda:1500.)),
                   ResourcePoolManager=NS(ResourcePools=[self.pool]),
                   myHUD=NS(HUDMovie=NS(**dict(zip(state.HUD_FIELDS,[89.,100.,11.,50.,3,5])))))

    def test_native_and_cached_values_remain_distinct(self):
        result=state.inspect_player(self.pc)
        self.assertEqual(result['native']['GetHealth'],90.)
        self.assertEqual(result['hud_cache']['CachedHealth'],89.)
        self.assertEqual(result['grenades']['current'],3.)
        self.assertEqual(result['native']['xp_pool_current'],1234.)

    def test_invalid_health_is_unavailable_not_zero(self):
        self.pc.Pawn.GetHealth=lambda:float('nan')
        result=state.inspect_player(self.pc)
        self.assertIsNone(result['native']['GetHealth'])
        self.assertEqual(result['unavailable']['GetHealth'],'ValueError')
        self.assertEqual(result['native']['GetShieldStrength'],12.)

    def test_ambiguous_grenade_pool_is_not_guessed(self):
        self.pc.ResourcePoolManager.ResourcePools.append(self.pool)
        result=state.inspect_player(self.pc)
        self.assertIsNone(result['grenades'])
        self.assertIn('grenades',result['unavailable'])

    def test_missing_hud_does_not_hide_native_state(self):
        self.pc.myHUD=None
        result=state.inspect_player(self.pc)
        self.assertIsNone(result['hud_cache']['CachedShields'])
        self.assertEqual(result['native']['GetShieldStrength'],12.)

    def test_boolean_is_not_a_numeric_native_value(self):
        with self.assertRaises(ValueError):state.number(True)
