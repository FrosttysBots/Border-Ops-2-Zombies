"""Native donor player/HUD observations. No setters, XP awards or inventory edits."""
import math

HUD_FIELDS = ('CachedHealth','CachedMaxHealth','CachedShields','CachedMaxShields',
              'CachedGrenades','CachedMaxGrenades')


def number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Expected finite native numeric value')
    return value


def path(value):
    return None if value is None else str(value._path_name())[:512]


def inspect_player(pc):
    unavailable = {}
    def read(name, getter):
        try: return getter()
        except Exception as exc:
            unavailable[name] = type(exc).__name__
            return None
    pawn = pc.Pawn
    result = {'pawn':path(pawn), 'native':{}, 'hud_cache':{}, 'unavailable':unavailable}
    for name in ('GetHealth','GetMaxHealth','GetShieldStrength','GetMaxShieldStrength'):
        result['native'][name] = read(name,lambda n=name:number(getattr(pawn,n)()))
    result['native']['level'] = read('level',lambda:number(pc.PlayerReplicationInfo.ExpLevel))
    result['native']['xp_next_level_at'] = read('xp_next_level_at',lambda:number(pc.PlayerReplicationInfo.ExpPointsNextLevelAt))
    result['native']['xp_pool_current'] = read('xp_pool_current',lambda:number(pc.ExpPool.Data.GetCurrentValue()))
    result['native']['xp_pool_max'] = read('xp_pool_max',lambda:number(pc.ExpPool.Data.GetMaxValue()))
    for name in HUD_FIELDS:
        result['hud_cache'][name] = read(name,lambda n=name:number(getattr(pc.myHUD.HUDMovie,n)))
    result['grenades'] = read('grenades', lambda:grenade_pool(pc))
    result['backpack_count'] = read('backpack_count',lambda:number(pawn.InvManager.BackpackInventoryCount))
    result['backpack_capacity'] = read('backpack_capacity',lambda:number(pawn.InvManager.InventorySlotMax_Misc))
    result['weapon'] = read('weapon',lambda:path(pawn.Weapon))
    return result


def grenade_pool(pc):
    pools=pc.ResourcePoolManager.ResourcePools
    if len(pools)>64: raise ValueError('Too many resource pools')
    matches=[]
    for pool in pools:
        if pool is None: continue
        if str(pool.Definition.Resource.Name) == 'Ammo_Grenade_Protean':
            matches.append(dict(path=path(pool),current=number(pool.GetCurrentValue()),maximum=number(pool.GetMaxValue())))
    if len(matches)!=1: raise ValueError('Grenade pool missing or ambiguous')
    return matches[0]
