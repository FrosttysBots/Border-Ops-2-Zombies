"""Synthetic verification. These tests do not run the real games."""
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
import wire
from inspect_weapon import matches_donor
from record_weapon import transition
from event_wire import EventBuffer, CAPACITY, parse_events

FRAME = 'BLPT1|7|2500|10|20|-3|1|90|0|100|2|m1911_zm|END\n'


class WireTests(unittest.TestCase):
    def test_event_buffer_accounts_for_evictions_and_rejects_gaps(self):
        buffer=EventBuffer()
        for i in range(CAPACITY+3):
            buffer.append('consume_ammo',i,'Gun',{'reload_count':4})
        packet=dict(schema=1,source='bl2_events',capture_id='a'*32,donor_session='b'*32,
                    seq=1,last_id=buffer.last_id,evicted=buffer.evicted,errors=0,active=True,
                    events=list(buffer.events))
        self.assertEqual(parse_events(json.dumps(packet))['evicted'],3)
        packet['events'][1]['id']+=1
        with self.assertRaises(ValueError):parse_events(json.dumps(packet))

    def test_reads_complete_native_snapshot(self):
        frame = wire.parse_host(FRAME)
        self.assertEqual(frame['seq'], 7)
        self.assertEqual(frame['position'], [10.,20.,-3.])
        self.assertEqual(frame['round'], 2)

    def test_partial_write_does_not_become_a_frame(self):
        for n in range(len(FRAME)-4):
            with self.assertRaises(ValueError):
                wire.parse_host(FRAME[:n])

    def test_rejects_unsupported_nonfinite_and_out_of_range(self):
        for text in [FRAME.replace('BLPT1','BLPT2'), FRAME.replace('|10|','|NaN|'),
                     FRAME.replace('|7|','|-1|'), FRAME.replace('|100|','|999999999|'),
                     FRAME.replace('m1911_zm','bad|field')]:
            with self.assertRaises(ValueError):wire.parse_host(text)

    def test_old_snapshots_and_frozen_ticks_stay_offline(self):
        freshness = wire.Freshness()
        freshness.observe(7, 0)
        self.assertFalse(freshness.online(0))
        freshness.observe(7, 1)
        self.assertFalse(freshness.online(1))
        freshness.observe(8, 2)
        self.assertTrue(freshness.online(2))
        freshness.observe(8, 5)
        self.assertFalse(freshness.online(5))

    def test_bounds_disk_reads_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            path = Path(folder)/'snapshot'
            wire.write_atomic(path, FRAME)
            self.assertEqual(wire.parse_host(wire.read_bounded(path))['seq'], 7)
            self.assertFalse(path.with_name('snapshot.tmp').exists())
            path.write_bytes(b'x'*(wire.MAX_BYTES+1))
            with self.assertRaises(ValueError):wire.read_bounded(path)

    def test_weapon_report_rejects_nonfinite_or_nonnumeric_stats(self):
        frame = dict(schema=1,source='bl2_weapon',session='a'*32,seq=1,
                     weapon=dict(object_path='Test.Gun',display_name='Gun',definitions={},
                                 native_properties={'WeaponDamage':12},unavailable={}))
        self.assertEqual(wire.parse_weapon(json.dumps(frame))['weapon']['display_name'],'Gun')
        for value in (float('nan'), float('inf'), True, '12', [12]):
            frame['weapon']['native_properties']['WeaponDamage']=value
            with self.assertRaises(ValueError):wire.parse_weapon(json.dumps(frame))

    def test_old_or_switched_weapon_cannot_match_current_donor(self):
        detail={'session':'a'*32,'seq':4,'weapon':{'object_path':'Test.Gun'}}
        donor={'session':'a'*32,'seq':4,'weapon':'Test.Gun'}
        self.assertTrue(matches_donor(detail,donor))
        for changes in ({'session':'b'*32},{'seq':20},{'seq':3},{'weapon':'Other.Gun'}):
            self.assertFalse(matches_donor(detail,donor|changes))

    def test_recording_does_not_infer_ammo_changes_across_switches_or_gaps(self):
        a=dict(session='a',object_path='Gun',seq=10,elapsed=1,getters={'GetAmmoCount':4})
        b=a|dict(seq=11,elapsed=1.25,getters={'GetAmmoCount':3})
        self.assertEqual(transition(a,b)['kind'],'ammo_decreased')
        self.assertEqual(transition(b,b|dict(seq=12,elapsed=1.5,getters={'GetAmmoCount':4}))['kind'],'ammo_increased')
        for change in ({'session':'b'},{'object_path':'Other'},{'seq':10},{'seq':30},{'elapsed':4},
                       {'getters':{'GetAmmoCount':None}}):
            self.assertIsNone(transition(a,b|change))

    def test_native_state_rejects_numbers_and_getters_reject_strings(self):
        weapon=dict(object_path='Gun',display_name='Gun',definitions={},native_properties={},
                    unavailable={},native_state={'bIsFiringWeapon':True},native_getters={'GetAmmoCount':4})
        frame=dict(schema=1,source='bl2_weapon',session='a'*32,seq=1,weapon=weapon)
        wire.parse_weapon(json.dumps(frame))
        weapon['native_state']['bIsFiringWeapon']=1
        with self.assertRaises(ValueError):wire.parse_weapon(json.dumps(frame))
        weapon['native_state']['bIsFiringWeapon']=True
        weapon['native_getters']['GetAmmoCount']='4'
        with self.assertRaises(ValueError):wire.parse_weapon(json.dumps(frame))


class AdapterTests(unittest.TestCase):
    def load_events(self):
        self.hook_registry={}
        def add(function, kind, identifier, callback):
            key=(function,kind,identifier)
            if key in self.hook_registry:return False
            self.hook_registry[key]=callback
            return True
        def remove(function,kind,identifier):
            return self.hook_registry.pop((function,kind,identifier),None) is not None
        sys.modules['unrealsdk'].hooks=types.SimpleNamespace(
            Type=types.SimpleNamespace(POST='post',PRE='pre'),add_hook=add,remove_hook=remove)
        unreal=types.ModuleType('unrealsdk.unreal')
        unreal.WeakPointer=lambda obj: lambda: obj
        sys.modules['unrealsdk.unreal']=unreal
        return importlib.import_module('blacklands_passthrough.events')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.mailbox = Path(self.temp.name)
        self.events = []
        self.pc = types.SimpleNamespace(Pawn=types.SimpleNamespace(
            Location=types.SimpleNamespace(X=10,Y=20,Z=30),
            Weapon=types.SimpleNamespace(_path_name=lambda: 'Synthetic.Weapon_1')))
        sdk = types.ModuleType('unrealsdk')
        sdk.logging = types.SimpleNamespace(info=self.events.append,warning=self.events.append)
        base = types.ModuleType('mods_base')
        base.Game = types.SimpleNamespace(BL2='BL2')
        base.hook = lambda name: lambda callback: callback
        base.get_pc = lambda **kwargs: self.pc
        base.build_mod = lambda **kwargs: self.events.append(kwargs)
        self.modules = patch.dict(sys.modules, {'mods_base':base,'unrealsdk':sdk})
        self.modules.start()
        sys.path.insert(0,str(ROOT/'work/staging/sdk_mods'))
        self.adapter = importlib.import_module('blacklands_passthrough')
        self.env = patch.dict(os.environ, {'BLACKLANDS_MAILBOX':str(self.mailbox)})
        self.env.start()
        self.adapter.enable()

    def tearDown(self):
        self.adapter.disable()
        self.env.stop()
        self.modules.stop()
        sys.path.pop(0)
        for name in list(sys.modules):
            if name == 'blacklands_passthrough' or name.startswith('blacklands_passthrough.'):
                del sys.modules[name]
        self.temp.cleanup()

    def test_returns_host_sequence_with_native_weapon_read(self):
        (self.mailbox/wire.HOST_FILE).write_text(FRAME)
        self.adapter.sample()
        frame = wire.parse_donor(wire.read_bounded(self.mailbox/wire.DONOR_FILE))
        self.assertEqual(frame['host_seq'], 7)
        self.assertEqual(frame['weapon'], 'Synthetic.Weapon_1')
        self.assertEqual((self.mailbox/wire.REPLY_FILE).read_text(),'BLPT1|7|1|ACK\n')
        self.assertEqual(self.pc.Pawn.Location.X,10)

    def test_missing_host_does_not_create_a_false_ack(self):
        self.adapter.sample()
        frame = json.loads((self.mailbox/wire.DONOR_FILE).read_text())
        self.assertIsNone(frame['host_seq'])
        self.assertFalse((self.mailbox/wire.REPLY_FILE).exists())

    def test_loading_and_disabled_mod_do_not_sample(self):
        self.pc.Pawn = None
        self.adapter.sample()
        self.assertFalse((self.mailbox/wire.DONOR_FILE).exists())
        self.adapter.disable()
        self.adapter._next_sample = 0
        self.adapter.sample()
        self.assertFalse((self.mailbox/wire.DONOR_FILE).exists())

    def test_missing_weapon_and_partial_host_are_safe(self):
        self.pc.Pawn.Weapon = None
        (self.mailbox/wire.HOST_FILE).write_text(FRAME[:25])
        self.adapter.sample()
        frame = json.loads((self.mailbox/wire.DONOR_FILE).read_text())
        self.assertEqual(frame['weapon'],'None')
        self.assertIsNone(frame['host_seq'])

    def test_native_parts_and_numeric_properties_are_read_without_mutation(self):
        native = types.SimpleNamespace(_path_name=lambda: 'GD_Test.Barrel')
        weapon = self.pc.Pawn.Weapon
        weapon.DefinitionData = types.SimpleNamespace(BarrelPartDefinition=native,
            ElementalPartDefinition=None, ManufacturerGradeIndex=3, GameStage=4, UniqueId=-123)
        weapon.GetShortHumanReadableName = lambda: 'Test Pistol'
        weapon.InstantHitDamage = 12.5
        weapon.GetAmmoCount = lambda: 30
        weapon.bIsFiringWeapon = False
        weapon.ReloadTime = float('nan')
        self.adapter.sample()
        detail = json.loads((self.mailbox/wire.WEAPON_FILE).read_text())['weapon']
        self.assertEqual(detail['display_name'], 'Test Pistol')
        self.assertEqual(detail['definitions']['BarrelPartDefinition'], 'GD_Test.Barrel')
        self.assertEqual(detail['definitions']['UniqueId'], -123)
        self.assertIsNone(detail['definitions']['ElementalPartDefinition'])
        self.assertNotIn('ElementalPartDefinition',detail['unavailable'])
        self.assertEqual(detail['native_properties']['InstantHitDamage'],12.5)
        self.assertEqual(detail['native_getters']['GetAmmoCount'],30)
        self.assertIs(detail['native_state']['bIsFiringWeapon'],False)
        wire.parse_weapon(json.dumps({'schema':1,'source':'bl2_weapon',
                                     'session':'a'*32,'seq':1,'weapon':detail}))
        self.assertIsNone(detail['native_properties']['ReloadTime'])
        self.assertIn('ReloadTime',detail['unavailable'])
        self.assertIn('BalanceDefinition',detail['unavailable'])
        self.assertIs(weapon.DefinitionData.BarrelPartDefinition,native)

    def test_unequip_clears_previous_weapon_details(self):
        self.adapter.sample()
        self.pc.Pawn.Weapon = None
        self.adapter._next_sample = 0
        self.adapter.sample()
        detail = json.loads((self.mailbox/wire.WEAPON_FILE).read_text())
        self.assertIsNone(detail['weapon'])
        self.assertEqual(detail['seq'],2)

    def test_default_mailbox_survives_normal_game_launch(self):
        default = self.mailbox/'Plutonium/storage/t6/raw/scriptdata'
        default.mkdir(parents=True)
        with patch.dict(os.environ, {'BLACKLANDS_MAILBOX':'', 'LOCALAPPDATA':str(self.mailbox)}):
            self.adapter.enable()
        self.assertEqual(self.adapter._mailbox,default)

    def test_invalid_explicit_mailbox_does_not_fall_back(self):
        with patch.dict(os.environ, {'BLACKLANDS_MAILBOX':str(self.mailbox/'missing')}):
            self.adapter.enable()
        self.assertIsNone(self.adapter._mailbox)

    def test_oversized_details_do_not_stop_acknowledgements(self):
        (self.mailbox/wire.HOST_FILE).write_text(FRAME)
        with patch.object(self.adapter, 'inspect_weapon', return_value={'oversized':'x'*9000}):
            self.adapter.sample()
        self.assertEqual(wire.parse_donor((self.mailbox/wire.DONOR_FILE).read_text())['host_seq'],7)
        self.assertTrue((self.mailbox/wire.REPLY_FILE).exists())
        self.assertFalse((self.mailbox/wire.WEAPON_FILE).exists())

    def test_event_hooks_filter_other_weapons_and_never_invoke_original(self):
        events=self.load_events()
        events.start()
        self.assertEqual(len(self.hook_registry),12)
        weapon=self.pc.Pawn.Weapon
        weapon.ReloadCnt,weapon.AmmoNotInClip=3,100
        args=types.SimpleNamespace(FireModeNum=0)
        def original(*args):raise AssertionError('Original function must not be invoked')
        callback=next(cb for key,cb in self.hook_registry.items() if key[0].endswith(':ConsumeAmmo'))
        self.assertIsNone(callback(types.SimpleNamespace(),args,None,original))
        self.assertIsNone(callback(weapon,args,None,original))
        self.assertEqual(events.packet()['last_id'],1)
        self.assertEqual(weapon.ReloadCnt,3)
        events.stop()
        self.assertEqual(len(self.hook_registry),0)
        frame=parse_events((self.mailbox/'blacklands_events.json').read_text())
        self.assertEqual(frame['events'][0]['kind'],'consume_ammo')
        self.assertFalse(frame['active'])

    def test_damage_notifications_are_local_but_not_attributed_to_equipped_gun(self):
        events=self.load_events();events.start()
        data=types.SimpleNamespace(TotalDamageForDamageType=42, DamagedActor=None)
        args=types.SimpleNamespace(PC=object(),DamageEventData=data)
        events.on_event('display_damage',None,args,None)
        self.assertEqual(events.packet()['last_id'],0)
        args.PC=self.pc
        events.on_event('display_damage',None,args,None)
        event=events.packet()['events'][0]
        self.assertIsNone(event['weapon'])
        self.assertEqual(event['data']['damage'],42)
        events.stop()

    def test_restart_and_timeout_do_not_leave_duplicate_event_hooks(self):
        events=self.load_events();events.start()
        first=events.packet()['capture_id']
        events.start(seconds=1)
        self.assertNotEqual(first,events.packet()['capture_id'])
        self.assertEqual(len(self.hook_registry),12)
        with patch.object(events.time,'monotonic',return_value=events._capture['deadline']+1):
            events.on_tick()
        self.assertFalse(events.packet()['active'])
        self.assertFalse(self.hook_registry)

    def test_failed_hook_registration_rolls_back_all_our_hooks(self):
        events=self.load_events()
        original=sys.modules['unrealsdk'].hooks.add_hook
        def add(function,*args):
            return False if function.endswith(':ReloadDone') else original(function,*args)
        sys.modules['unrealsdk'].hooks.add_hook=add
        with self.assertRaises(RuntimeError):events.start()
        self.assertFalse(self.hook_registry)

    def test_projectile_hit_keeps_original_weapon_after_weapon_switch(self):
        events=self.load_events();events.start()
        gun=self.pc.Pawn.Weapon
        gun.ReloadCnt,gun.AmmoNotInClip=3,100
        projectile=types.SimpleNamespace(_path_name=lambda:'World.Projectile_1',Class=types.SimpleNamespace(Name='WillowProjectile'))
        firing=types.SimpleNamespace(FiringModeDefinition=None)
        events.on_fire_begin(gun,firing,None,None)
        events.on_event('projectile_spawn',gun,types.SimpleNamespace(InProjectile=projectile),None)
        events.on_event('fire_mode',gun,firing,None)
        self.pc.Pawn.Weapon=types.SimpleNamespace(_path_name=lambda:'Different.Gun')
        target=types.SimpleNamespace(_path_name=lambda:'World.Enemy')
        events.on_event('take_damage',target,types.SimpleNamespace(InstigatedBy=self.pc,DamageCauser=projectile,Damage=42),None)
        hit=events.packet()['events'][-1]
        self.assertEqual(hit['weapon'],'Synthetic.Weapon_1')
        self.assertEqual(hit['data']['shot_id'],1)
        self.assertEqual(hit['data']['attribution'],'spawned_projectile_reference')
        events.stop()

    def test_unseen_or_invalidated_projectile_stays_unattributed(self):
        events=self.load_events();events.start()
        projectile=types.SimpleNamespace(_path_name=lambda:'World.Projectile_1',Class=types.SimpleNamespace(Name='WillowProjectile'))
        target=types.SimpleNamespace(_path_name=lambda:'World.Enemy')
        args=types.SimpleNamespace(InstigatedBy=self.pc,DamageCauser=projectile,Damage=42)
        events.on_event('take_damage',target,args,None)
        self.assertIsNone(events.packet()['events'][-1]['data']['shot_id'])
        events._capture['projectiles']['World.Projectile_1']=dict(weak=lambda:None,weapon='Old.Gun',shot_id=9)
        events.on_event('take_damage',target,args,None)
        self.assertIsNone(events.packet()['events'][-1]['weapon'])
        events.stop()

    def test_direct_weapon_causer_does_not_guess_most_recent_shot(self):
        events=self.load_events();events.start()
        gun=self.pc.Pawn.Weapon
        gun.Class=types.SimpleNamespace(Name='WillowWeapon')
        target=types.SimpleNamespace(_path_name=lambda:'World.Enemy')
        events.on_event('take_damage',target,types.SimpleNamespace(InstigatedBy=self.pc,DamageCauser=gun,Damage=42),None)
        hit=events.packet()['events'][-1]
        self.assertEqual(hit['weapon'],'Synthetic.Weapon_1')
        self.assertIsNone(hit['data']['shot_id'])
        self.assertEqual(hit['data']['attribution'],'native_weapon_causer')
        events.stop()

    def test_aborted_firing_context_is_cleared_before_later_tick(self):
        events=self.load_events();events.start()
        gun=self.pc.Pawn.Weapon
        gun.ReloadCnt,gun.AmmoNotInClip=3,100
        events.on_fire_begin(gun,types.SimpleNamespace(FiringModeDefinition=None),None,None)
        events.on_tick()
        projectile=types.SimpleNamespace(_path_name=lambda:'World.Projectile_1')
        events.on_event('projectile_spawn',gun,types.SimpleNamespace(InProjectile=projectile),None)
        self.assertIsNone(events.packet()['events'][-1]['data']['shot_id'])
        self.assertFalse(events._capture['projectiles'])
        events.stop()

    def test_impact_scope_requires_matching_weapon_and_target_and_expires(self):
        events=self.load_events();events.start()
        gun=self.pc.Pawn.Weapon
        gun.Class=types.SimpleNamespace(Name='WillowWeapon')
        target=types.SimpleNamespace(_path_name=lambda:'World.Enemy')
        other=types.SimpleNamespace(_path_name=lambda:'World.Other')
        args=types.SimpleNamespace(Impact=types.SimpleNamespace(HitActor=target),
                                   BulletDamage=42,FiringModeDefinition=None)
        damage=types.SimpleNamespace(InstigatedBy=self.pc,DamageCauser=gun,Damage=42)
        events.on_impact(gun,args,None,None,begin=True)
        events.on_event('take_damage',other,damage,None)
        self.assertIsNone(events.packet()['events'][-1]['data']['impact_id'])
        events.on_event('take_damage',target,damage,None)
        hit=events.packet()['events'][-1]
        self.assertEqual(hit['data']['impact_id'],1)
        self.assertIsNone(hit['data']['shot_id'])
        events.on_impact(gun,args,None,None,begin=False)
        events.on_event('take_damage',target,damage,None)
        self.assertIsNone(events.packet()['events'][-1]['data']['impact_id'])
        events.on_impact(gun,args,None,None,begin=True)
        events.on_tick()
        events.on_event('take_damage',target,damage,None)
        self.assertIsNone(events.packet()['events'][-1]['data']['impact_id'])
        events.stop()

    def test_nested_impacts_preserve_outer_context(self):
        events=self.load_events();events.start()
        gun=self.pc.Pawn.Weapon
        args=types.SimpleNamespace(Impact=types.SimpleNamespace(HitActor=None),
                                   BulletDamage=42,FiringModeDefinition=None)
        events.on_impact(gun,args,None,None,begin=True)
        events.on_impact(gun,args,None,None,begin=True)
        events.on_impact(gun,args,None,None,begin=False)
        self.assertEqual(events._capture['impacts'][-1]['impact_id'],1)
        events.on_impact(gun,args,None,None,begin=False)
        self.assertFalse(events._capture['impacts'])
        events.stop()

    def test_runtime_reads_only_local_tick_and_cleans_up_on_disconnect(self):
        self.load_events()
        runtime=importlib.import_module('blacklands_passthrough.runtime')
        sent=[]
        publisher=types.SimpleNamespace(last_ack=None,send=lambda *args:sent.append(args),
                                        status=lambda:{'online':False},close=lambda:None)
        self.pc.Rotation=types.SimpleNamespace(Pitch=1,Yaw=2,Roll=3)
        with patch.object(runtime,'Publisher',return_value=publisher):runtime.start()
        runtime.on_tick(object());self.assertFalse(sent)
        runtime.on_tick(self.pc)
        self.assertEqual(sent,[([10.,20.,30.],[1.,2.,3.],'Synthetic.Weapon_1')])
        self.assertEqual(self.adapter._seq,0)
        self.assertEqual(self.pc.Pawn.Location.X,10)
        with patch.object(runtime.time,'monotonic',return_value=runtime._state['started']+6):
            runtime.on_tick(self.pc)
        self.assertFalse(self.hook_registry)
        self.assertEqual(runtime.status()['reason'],'sidecar_unresponsive')

    def test_runtime_hook_registration_failure_closes_publisher(self):
        self.load_events()
        runtime=importlib.import_module('blacklands_passthrough.runtime')
        closed=[]
        publisher=types.SimpleNamespace(status=lambda:{},close=lambda:closed.append(True))
        with patch.object(runtime,'Publisher',return_value=publisher), patch.object(
                runtime.hooks,'add_hook',return_value=False):
            with self.assertRaises(RuntimeError):runtime.start()
        self.assertTrue(closed)
        self.assertFalse(self.hook_registry)


if __name__ == '__main__':unittest.main()
