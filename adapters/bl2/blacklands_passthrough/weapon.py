"""Read native weapon data on the game thread; never construct or modify items."""
import math

DEFINITION_PATHS = (
    'WeaponTypeDefinition', 'BalanceDefinition', 'ManufacturerDefinition',
    'BodyPartDefinition', 'GripPartDefinition', 'BarrelPartDefinition',
    'SightPartDefinition', 'StockPartDefinition', 'ElementalPartDefinition',
    'Accessory1PartDefinition', 'Accessory2PartDefinition', 'MaterialPartDefinition',
    'PrefixPartDefinition', 'TitlePartDefinition',
)
DEFINITION_NUMBERS = ('ManufacturerGradeIndex', 'GameStage', 'UniqueId')
# Raw native properties, not item-card values or final damage against an enemy.
STAT_FIELDS = ('InstantHitDamage', 'InstantHitDamageBaseValue', 'FireInterval',
               'ReloadTime', 'ClipSize', 'ShotCost', 'Spread', 'AmmoNotInClip',
               'LastReloadCnt', 'ReloadCnt', 'AmmoLeftInClipDuringReload',
               'ReplicatedReloadState')
# Zero-argument numeric getters confirmed by live UFunction reflection.
GETTERS = ('GetAmmoCount', 'GetMaxAmmo', 'GetMultiProjectileDamage')
STATE_FIELDS = ('bIsFiringWeapon', 'bAmmoRefilledDuringReload', 'bManualReload')


def boolean(value):
    if not isinstance(value, bool):
        raise ValueError('not a boolean property')
    return value


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('not a numeric property')
    if not math.isfinite(value):
        raise ValueError('nonfinite property')
    return value


def inspect_weapon(weapon):
    if weapon is None:
        return None
    unavailable = {}

    def read(label, getter):
        try:
            return getter()
        except Exception as exc:
            unavailable[label] = type(exc).__name__
            return None

    def path(value):
        return None if value is None else str(value._path_name())[:512]

    data = read('DefinitionData', lambda: weapon.DefinitionData)
    definitions = {}
    if data is not None:
        for field in DEFINITION_PATHS:
            definitions[field] = read(field, lambda f=field: path(getattr(data, f)))
        for field in DEFINITION_NUMBERS:
            definitions[field] = read(field, lambda f=field: finite_number(getattr(data, f)))
    stats = {field: read(field, lambda f=field: finite_number(getattr(weapon, f)))
             for field in STAT_FIELDS}
    getters = {name: read(name, lambda n=name: finite_number(getattr(weapon, n)()))
               for name in GETTERS}
    state = {name: read(name, lambda n=name: boolean(getattr(weapon, n)))
             for name in STATE_FIELDS}
    return {
        'object_path': path(weapon),
        'display_name': read('display_name', lambda: str(weapon.GetShortHumanReadableName())[:256]),
        'definitions': definitions,
        'native_properties': stats,
        'native_getters': getters,
        'native_state': state,
        'inspection_revision': 2,
        'unavailable': unavailable,
    }
