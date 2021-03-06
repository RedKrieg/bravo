from collections import namedtuple

from construct import Struct, Container, Embed, Enum, MetaField
from construct import MetaArray, If, Switch, Const, Peek, Magic
from construct import OptionalGreedyRange, RepeatUntil
from construct import Flag, PascalString, Adapter
from construct import UBInt8, UBInt16, UBInt32, UBInt64
from construct import SBInt8, SBInt16, SBInt32
from construct import BFloat32, BFloat64
from construct import BitStruct, BitField
from construct import StringAdapter, LengthValueAdapter, Sequence

def IPacket(object):
    """
    Interface for packets.
    """

    def parse(buf, offset):
        """
        Parse a packet out of the given buffer, starting at the given offset.

        If the parse is successful, returns a tuple of the parsed packet and
        the next packet offset in the buffer.

        If the parse fails due to insufficient data, returns a tuple of None
        and the amount of data required before the parse can be retried.

        Exceptions may be raised if the parser finds invalid data.
        """

def simple(name, fmt, *args):
    """
    Make a customized namedtuple representing a simple, primitive packet.
    """

    from struct import Struct

    s = Struct(fmt)

    @classmethod
    def parse(cls, buf, offset):
        if len(buf) >= s.size + offset:
            unpacked = s.unpack_from(buf, offset)
            return cls(*unpacked), s.size + offset
        else:
            return None, s.size - len(buf)

    def build(self):
        return s.pack(*self)

    methods = {
        "parse": parse,
        "build": build,
    }

    return type(name, (namedtuple(name, *args),), methods)


DUMP_ALL_PACKETS = False

# Strings.
# This one is a UCS2 string, which effectively decodes single writeChar()
# invocations. We need to import the encoding for it first, though.
from bravo.encodings import ucs2
from codecs import register
register(ucs2)

class DoubleAdapter(LengthValueAdapter):

    def _encode(self, obj, context):
        return len(obj) / 2, obj

def AlphaString(name):
    return StringAdapter(
        DoubleAdapter(
            Sequence(name,
                UBInt16("length"),
                MetaField("data", lambda ctx: ctx["length"] * 2),
            )
        ),
        encoding="ucs2",
    )

# Boolean converter.
def Bool(*args, **kwargs):
    return Flag(*args, default=True, **kwargs)

# Flying, position, and orientation, reused in several places.
grounded = Struct("grounded", UBInt8("grounded"))
position = Struct("position",
    BFloat64("x"),
    BFloat64("y"),
    BFloat64("stance"),
    BFloat64("z")
)
orientation = Struct("orientation", BFloat32("rotation"), BFloat32("pitch"))

# Notchian item packing
items = Struct("items",
    SBInt16("primary"),
    If(lambda context: context["primary"] >= 0,
        Embed(Struct("item_information",
            UBInt8("count"),
            UBInt16("secondary"),
            Magic("\xff\xff"),
        )),
    ),
)

Metadata = namedtuple("Metadata", "type value")
metadata_types = ["byte", "short", "int", "float", "string", "slot",
    "coords"]

# Metadata adaptor.
class MetadataAdapter(Adapter):

    def _decode(self, obj, context):
        d = {}
        for m in obj.data:
            d[m.id.second] = Metadata(metadata_types[m.id.first], m.value)
        return d

    def _encode(self, obj, context):
        c = Container(data=[], terminator=None)
        for k, v in obj.iteritems():
            t, value = v
            d = Container(
                id=Container(first=metadata_types.index(t), second=k),
                value=value,
                peeked=None)
            c.data.append(d)
        if c.data:
            c.data[-1].peeked = 127
        else:
            c.data.append(Container(id=Container(first=0, second=0), value=0,
                peeked=127))
        return c

# Metadata inner container.
metadata_switch = {
    0: UBInt8("value"),
    1: UBInt16("value"),
    2: UBInt32("value"),
    3: BFloat32("value"),
    4: AlphaString("value"),
    5: Struct("slot",
        UBInt16("primary"),
        UBInt8("count"),
        UBInt16("secondary"),
    ),
    6: Struct("coords",
        UBInt32("x"),
        UBInt32("y"),
        UBInt32("z"),
    ),
}

# Metadata subconstruct.
metadata = MetadataAdapter(
    Struct("metadata",
        RepeatUntil(lambda obj, context: obj["peeked"] == 0x7f,
            Struct("data",
                BitStruct("id",
                    BitField("first", 3),
                    BitField("second", 5),
                ),
                Switch("value", lambda context: context["id"]["first"],
                    metadata_switch),
                Peek(UBInt8("peeked")),
            ),
        ),
        Const(UBInt8("terminator"), 0x7f),
    ),
)

# Build faces, used during dig and build.
faces = {
    "noop": -1,
    "-y": 0,
    "+y": 1,
    "-z": 2,
    "+z": 3,
    "-x": 4,
    "+x": 5,
}
face = Enum(SBInt8("face"), **faces)

# World dimension.
dimensions = {
    "earth": 0,
    "sky": 1,
    "nether": 255,
}
dimension = Enum(UBInt8("dimension"), **dimensions)

# Difficulty levels
difficulties = {
    "peaceful": 0,
    "easy": 1,
    "normal": 2,
    "hard": 3,
}
difficulty = Enum(UBInt8("difficulty"), **difficulties)

modes = {
    "survival": 0,
    "creative": 1,
    "adventure": 2,
}
mode = Enum(UBInt8("mode"), **modes)

# Possible effects.
# XXX these names aren't really canonized yet
effect = Enum(UBInt8("effect"),
    move_fast=1,
    move_slow=2,
    dig_fast=3,
    dig_slow=4,
    damage_boost=5,
    heal=6,
    harm=7,
    jump=8,
    confusion=9,
    regenerate=10,
    resistance=11,
    fire_resistance=12,
    water_resistance=13,
    invisibility=14,
    blindness=15,
    night_vision=16,
    hunger=17,
    weakness=18,
    poison=19,
    wither=20,
)

# The actual packet list.
packets = {
    0: Struct("ping",
        UBInt32("pid"),
    ),
    1: Struct("login",
        # Player Entity ID (random number generated by the server)
        UBInt32("eid"),
        # default, flat, largeBiomes
        AlphaString("leveltype"),
        mode,
        dimension,
        difficulty,
        UBInt8("unused"),
        UBInt8("maxplayers"),
    ),
    2: Struct("handshake",
        UBInt8("protocol"),
        AlphaString("username"),
        AlphaString("host"),
        UBInt32("port"),
    ),
    3: Struct("chat",
        AlphaString("message"),
    ),
    4: Struct("time",
        # Total Ticks
        UBInt64("timestamp"),
        # Time of day
        UBInt64("time"),
    ),
    5: Struct("entity-equipment",
        UBInt32("eid"),
        UBInt16("slot"),
        Embed(items),
    ),
    6: Struct("spawn",
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
    ),
    7: Struct("use",
        UBInt32("eid"),
        UBInt32("target"),
        UBInt8("button"),
    ),
    8: Struct("health",
        UBInt16("hp"),
        UBInt16("fp"),
        BFloat32("saturation"),
    ),
    9: Struct("respawn",
        dimension,
        difficulty,
        mode,
        UBInt16("height"),
        AlphaString("leveltype"),
    ),
    10: grounded,
    11: Struct("position",
        position,
        grounded
    ),
    12: Struct("orientation",
        orientation,
        grounded
    ),
    # TODO: Differ between client and server 'position'
    13: Struct("location",
        position,
        orientation,
        grounded
    ),
    14: Struct("digging",
        Enum(UBInt8("state"),
            started=0,
            cancelled=1,
            stopped=2,
            checked=3,
            dropped=4,
            # Also eating
            shooting=5,
        ),
        SBInt32("x"),
        UBInt8("y"),
        SBInt32("z"),
        face,
    ),
    15: Struct("build",
        SBInt32("x"),
        UBInt8("y"),
        SBInt32("z"),
        face,
        Embed(items),
        UBInt8("cursorx"),
        UBInt8("cursory"),
        UBInt8("cursorz"),
    ),
    # Hold Item Change
    16: Struct("equip",
        # Only 0-8
        UBInt16("slot"),
    ),
    17: Struct("bed",
        UBInt32("eid"),
        UBInt8("unknown"),
        SBInt32("x"),
        UBInt8("y"),
        SBInt32("z"),
    ),
    18: Struct("animate",
        UBInt32("eid"),
        Enum(UBInt8("animation"),
            noop=0,
            arm=1,
            hit=2,
            leave_bed=3,
            eat=5,
            unknown=102,
            crouch=104,
            uncrouch=105,
        ),
    ),
    19: Struct("action",
        UBInt32("eid"),
        Enum(UBInt8("action"),
            crouch=1,
            uncrouch=2,
            leave_bed=3,
            start_sprint=4,
            stop_sprint=5,
        ),
    ),
    20: Struct("player",
        UBInt32("eid"),
        AlphaString("username"),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        UBInt8("yaw"),
        UBInt8("pitch"),
        # 0 For none, unlike other packets
        # -1 crashes clients
        SBInt16("item"),
        metadata,
    ),
    # Spawn Dropped Item
    21: Struct("pickup",
        UBInt32("eid"),
        Embed(items),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        UBInt8("yaw"),
        UBInt8("pitch"),
        UBInt8("roll"),
    ),
    22: Struct("collect",
        UBInt32("eid"),
        UBInt32("destination"),
    ),
    # Object/Vehicle
    23: Struct("vehicle",
        UBInt32("eid"),
        Enum(UBInt8("type"),
            boat=1,
            minecart=10,
            storage_cart=11,
            powered_cart=12,
            tnt=50,
            ender_crystal=51,
            arrow=60,
            snowball=61,
            egg=62,
            thrown_enderpearl=65,
            wither_skull=66,
            # See http://wiki.vg/Entities#Objects
            falling_block=70,
            ender_eye=72,
            thrown_potion=73,
            dragon_egg=74,
            thrown_xp_bottle=75,
            fishing_float=90,
        ),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        SBInt32("data"),
        # The following 3 are 0 if data is 0
        SBInt16("speedx"),
        SBInt16("speedy"),
        SBInt16("speedz"),
    ),
    24: Struct("mob",
        UBInt32("eid"),
        Enum(UBInt8("type"), **{
            "Creeper": 50,
            "Skeleton": 51,
            "Spider": 52,
            "GiantZombie": 53,
            "Zombie": 54,
            "Slime": 55,
            "Ghast": 56,
            "ZombiePig": 57,
            "Enderman": 58,
            "CaveSpider": 59,
            "Silverfish": 60,
            "Blaze": 61,
            "MagmaCube": 62,
            "EnderDragon": 63,
            "Wither": 64,
            "Bat": 65,
            "Witch": 66,
            "Pig": 90,
            "Sheep": 91,
            "Cow": 92,
            "Chicken": 93,
            "Squid": 94,
            "Wolf": 95,
            "Mooshroom": 96,
            "Snowman": 97,
            "Ocelot": 98,
            "IronGolem": 99,
            "Villager": 120
        }),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        SBInt8("yaw"),
        SBInt8("pitch"),
        SBInt8("head_yaw"),
        SBInt16("vx"),
        SBInt16("vy"),
        SBInt16("vz"),
        metadata,
    ),
    25: Struct("painting",
        UBInt32("eid"),
        AlphaString("title"),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        face,
    ),
    26: Struct("experience",
        UBInt32("eid"),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        UBInt16("quantity"),
    ),
    28: Struct("velocity",
        UBInt32("eid"),
        SBInt16("dx"),
        SBInt16("dy"),
        SBInt16("dz"),
    ),
    29: Struct("destroy",
        UBInt8("count"),
        MetaArray(lambda context: context["count"], UBInt32("eid")),
    ),
    30: Struct("create",
        UBInt32("eid"),
    ),
    31: Struct("entity-position",
        UBInt32("eid"),
        SBInt8("dx"),
        SBInt8("dy"),
        SBInt8("dz")
    ),
    32: Struct("entity-orientation",
        UBInt32("eid"),
        UBInt8("yaw"),
        UBInt8("pitch")
    ),
    33: Struct("entity-location",
        UBInt32("eid"),
        SBInt8("dx"),
        SBInt8("dy"),
        SBInt8("dz"),
        UBInt8("yaw"),
        UBInt8("pitch")
    ),
    34: Struct("teleport",
        UBInt32("eid"),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
        UBInt8("yaw"),
        UBInt8("pitch"),
    ),
    35: Struct("entity-head",
        UBInt32("eid"),
        UBInt8("yaw"),
    ),
    38: Struct("status",
        UBInt32("eid"),
        Enum(UBInt8("status"),
            damaged=2,
            killed=3,
            taming=6,
            tamed=7,
            drying=8,
            eating=9,
            sheep_eat=10,
        ),
    ),
    39: Struct("attach",
        UBInt32("eid"),
        # -1 for detatching
        UBInt32("vid"),
    ),
    40: Struct("metadata",
        UBInt32("eid"),
        metadata,
    ),
    41: Struct("effect",
        UBInt32("eid"),
        effect,
        UBInt8("amount"),
        UBInt16("duration"),
    ),
    42: Struct("uneffect",
        UBInt32("eid"),
        effect,
    ),
    43: Struct("levelup",
        BFloat32("current"),
        UBInt16("level"),
        UBInt16("total"),
    ),
    51: Struct("chunk",
        SBInt32("x"),
        SBInt32("z"),
        Bool("continuous"),
        UBInt16("primary"),
        UBInt16("add"),
        PascalString("data", length_field=UBInt32("length"), encoding="zlib"),
    ),
    52: Struct("batch",
        SBInt32("x"),
        SBInt32("z"),
        UBInt16("count"),
        PascalString("data", length_field=UBInt32("length")),
    ),
    53: Struct("block",
        SBInt32("x"),
        UBInt8("y"),
        SBInt32("z"),
        UBInt16("type"),
        UBInt8("meta"),
    ),
    # XXX This covers general tile actions, not just note blocks.
    # TODO: Needs work
    54: Struct("block-action",
        SBInt32("x"),
        SBInt16("y"),
        SBInt32("z"),
        UBInt8("byte1"),
        UBInt8("byte2"),
        UBInt16("blockid"),
    ),
    55: Struct("block-break-anim",
        UBInt32("eid"),
        UBInt32("x"),
        UBInt32("y"),
        UBInt32("z"),
        UBInt8("stage"),
    ),
    56: Struct("bulk-chunk",
        UBInt16("count"),
        # Length
        # Data
        # metadata
    ),
    # TODO: Needs work?
    60: Struct("explosion",
        BFloat64("x"),
        BFloat64("y"),
        BFloat64("z"),
        BFloat32("radius"),
        UBInt32("count"),
        MetaField("blocks", lambda context: context["count"] * 3),
        BFloat32("motionx"),
        BFloat32("motiony"),
        BFloat32("motionz"),
    ),
    61: Struct("sound",
        Enum(UBInt32("sid"),
            click2=1000,
            click1=1001,
            bow_fire=1002,
            door_toggle=1003,
            extinguish=1004,
            record_play=1005,
            charge=1007,
            fireball=1008,
            zombie_wood=1010,
            zombie_metal=1011,
            zombie_break=1012,
            wither=1013,
            smoke=2000,
            block_break=2001,
            splash_potion=2002,
            ender_eye=2003,
            blaze=2004,
        ),
        SBInt32("x"),
        UBInt8("y"),
        SBInt32("z"),
        UBInt32("data"),
        Bool("volume-mod"),
    ),
    62: Struct("named-sound",
        AlphaString("name"),
        UBInt32("x"),
        UBInt32("y"),
        UBInt32("z"),
        BFloat32("volume"),
        UBInt8("pitch"),
    ),
    70: Struct("state",
        Enum(UBInt8("state"),
            bad_bed=0,
            start_rain=1,
            stop_rain=2,
            mode_change=3,
            run_credits=4,
        ),
        mode,
    ),
    71: Struct("thunderbolt",
        UBInt32("eid"),
        UBInt8("gid"),
        SBInt32("x"),
        SBInt32("y"),
        SBInt32("z"),
    ),
    100: Struct("window-open",
        UBInt8("wid"),
        Enum(UBInt8("type"),
            chest=0,
            workbench=1,
            furnace=2,
            dispenser=3,
            enchatment_table=4,
            brewing_stand=5,
        ),
        AlphaString("title"),
        UBInt8("slots"),
    ),
    101: Struct("window-close",
        UBInt8("wid"),
    ),
    102: Struct("window-action",
        UBInt8("wid"),
        UBInt16("slot"),
        UBInt8("button"),
        UBInt16("token"),
        Bool("shift"),
        Embed(items),
    ),
    103: Struct("window-slot",
        UBInt8("wid"),
        UBInt16("slot"),
        Embed(items),
    ),
    104: Struct("inventory",
        UBInt8("wid"),
        UBInt16("length"),
        MetaArray(lambda context: context["length"], items),
    ),
    105: Struct("window-progress",
        UBInt8("wid"),
        UBInt16("bar"),
        UBInt16("progress"),
    ),
    106: Struct("window-token",
        UBInt8("wid"),
        UBInt16("token"),
        Bool("acknowledged"),
    ),
    107: Struct("window-creative",
        UBInt16("slot"),
        Embed(items),
    ),
    108: Struct("enchant",
        UBInt8("wid"),
        UBInt8("enchantment"),
    ),
    130: Struct("sign",
        SBInt32("x"),
        UBInt16("y"),
        SBInt32("z"),
        AlphaString("line1"),
        AlphaString("line2"),
        AlphaString("line3"),
        AlphaString("line4"),
    ),
    131: Struct("map",
        UBInt16("type"),
        UBInt16("itemid"),
        PascalString("data", length_field=UBInt8("length")),
    ),
    # TODO: NBT data array
    132: Struct("tile-update",
        SBInt32("x"),
        UBInt16("y"),
        SBInt32("z"),
        UBInt8("action"),
        # nbt data
    ),
    200: Struct("statistics",
        UBInt32("sid"), # XXX I could be an Enum
        UBInt8("count"),
    ),
    201: Struct("players",
        AlphaString("name"),
        Bool("online"),
        UBInt16("ping"),
    ),
    202: Struct("abilities",
        UBInt8("flags"),
        UBInt8("fly-speed"),
        UBInt8("walk-speed"),
    ),
    203: Struct("tab",
        AlphaString("autocomplete"),
    ),
    204: Struct("settings",
        AlphaString("locale"),
        UBInt8("distance"),
        UBInt8("chat"),
        difficulty,
        Bool("cape"),
    ),
    205: Struct("statuses",
        UBInt8("payload")
    ),
    # TODO: Needs DATA field
    250: Struct("plugin-message",
        AlphaString("channel"),
        UBInt16("length"),
        # Data
    ),
    # TODO: Missing byte arrays
    252: Struct("key-response",
        UBInt16("shared-len"),
        # Shared Secret, byte array
        UBInt16("token-len"),
        # Token byte array
    ),
    # TODO: Missing byte arrays
    253: Struct("key-request",
        AlphaString("server"),
        UBInt16("key-len"),
        # Pubkey byte array
        UBInt16("token-len"),
        # Token byte arrap
    ),
    254: Struct("poll", UBInt8("unused")),
    255: Struct("error", AlphaString("message")),
}

packet_stream = Struct("packet_stream",
    OptionalGreedyRange(
        Struct("full_packet",
            UBInt8("header"),
            Switch("payload", lambda context: context["header"], packets),
        ),
    ),
    OptionalGreedyRange(
        UBInt8("leftovers"),
    ),
)

def parse_packets(bytestream):
    """
    Opportunistically parse out as many packets as possible from a raw
    bytestream.

    Returns a tuple containing a list of unpacked packet containers, and any
    leftover unparseable bytes.
    """

    container = packet_stream.parse(bytestream)

    l = [(i.header, i.payload) for i in container.full_packet]
    leftovers = "".join(chr(i) for i in container.leftovers)

    if DUMP_ALL_PACKETS:
        for packet in l:
            print "Parsed packet %d" % packet[0]
            print packet[1]

    return l, leftovers

incremental_packet_stream = Struct("incremental_packet_stream",
    Struct("full_packet",
        UBInt8("header"),
        Switch("payload", lambda context: context["header"], packets),
    ),
    OptionalGreedyRange(
        UBInt8("leftovers"),
    ),
)

def parse_packets_incrementally(bytestream):
    """
    Parse out packets one-by-one, yielding a tuple of packet header and packet
    payload.

    This function returns a generator.

    This function will yield all valid packets in the bytestream up to the
    first invalid packet.

    :returns: a generator yielding tuples of headers and payloads
    """

    while bytestream:
        parsed = incremental_packet_stream.parse(bytestream)
        header = parsed.full_packet.header
        payload = parsed.full_packet.payload
        bytestream = "".join(chr(i) for i in parsed.leftovers)

        yield header, payload

packets_by_name = dict((v.name, k) for (k, v) in packets.iteritems())

def make_packet(packet, *args, **kwargs):
    """
    Constructs a packet bytestream from a packet header and payload.

    The payload should be passed as keyword arguments. Additional containers
    or dictionaries to be added to the payload may be passed positionally, as
    well.
    """

    if packet not in packets_by_name:
        print "Couldn't find packet name %s!" % packet
        return ""

    header = packets_by_name[packet]

    for arg in args:
        kwargs.update(dict(arg))
    container = Container(**kwargs)

    if DUMP_ALL_PACKETS:
        print "Making packet %s (%d)" % (packet, header)
        print container
    payload = packets[header].build(container)
    return chr(header) + payload

def make_error_packet(message):
    """
    Convenience method to generate an error packet bytestream.
    """

    return make_packet("error", message=message)
