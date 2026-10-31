"""Best-guess show type from the title, used only when the venue gives no label.

Deliberately conservative: when nothing matches it returns "" so the site shows no tag
rather than a wrong one. Ticketmaster's own classification, where we have it, overrides this.
"""
import re

_MUSICAL_EXACT = {
    "six", "hamilton", "wicked", "the lion king", "lion king", "matilda", "grease", "chicago", "oliver", "annie", "tina", "cats",
    "evita", "hadestown", "heathers", "waitress", "mamma mia", "mamma mia!", "frozen", "shrek", "elf", "pretty woman", "kinky boots",
    "hairspray", "footloose", "starlight express", "spamalot", "the producers", "the bodyguard", "bat out of hell", "jersey boys",
    "dirty dancing", "blood brothers", "legally blonde", "sister act", "joseph", "the book of mormon", "book of mormon", "les miserables",
    "les misérables", "the phantom of the opera", "phantom of the opera", "back to the future", "& juliet", "moulin rouge", "mean girls",
    "school of rock", "billy elliot", "the great gatsby", "dear evan hansen", "fiddler on the roof", "west side story", "sunset boulevard",
    "little shop of horrors", "everybody's talking about jamie", "we will rock you", "chitty chitty bang bang", "the rocky horror show",
    "rocky horror show", "cabaret", "company", "rent", "fame", "hair", "mary poppins", "beetlejuice", "titanique", "operation mincemeat",
    "standing at the sky's edge", "the addams family", "addams family", "oklahoma!", "oklahoma", "guys and dolls", "singin' in the rain", "kiss me kate", "42nd street",
}
_RULES = [
    ("Dance", r"\bballet\b|bourne|swan lake|nutcracker|giselle|riverdance|flamenco|rhythm of the dance|\btango\b|\bdance\b"),
    ("Pantomime", r"\bpanto(mime)?\b|cinderella|aladdin|puss in boots|goldilocks|treasure island|jack and the beanstalk|beauty and the beast|dick whittington|snow white|sleeping beauty|robin hood|mother goose|peter pan"),
    ("Musical", r"the musical|a musical|new musical|musical comedy|musical theatre|\bmusical\b"),
    ("Tribute", r"tribute|\bstory of\b|legends|the music of|rumours of|illegal eagles|\bperform(s|ing) the songs\b|songs of"),
    ("Classical", r"orchestra|philharmon|symphon|\bchoir\b|choral|brass band|chamber (music|orchestra|choir|ensemble)|\bopera\b|\brecital\b|baroque"),
    ("Comedy", r"comed(y|ian)|stand.?up|improv|\blive at the\b"),
    ("Family", r"kids.? (show|club|disco)|children|family (show|friendly|fun)|gruffalo|peppa|paw patrol|bluey|mr\.? men|room on the broom|tiger who came|horrible histories|walliams|julia donaldson|\bpuppet|dinosaur|story ?time|on ice"),
    ("Play", r"mousetrap|inspector calls|woman in black|play that goes wrong|\b2:22\b|39 steps|death on the nile|agatha christie|shakespeare|hamlet|macbeth|romeo and juliet|othello|king lear|midsummer night|twelfth night|much ado|the tempest|doll.s house|dracula|frankenstein|\bthe play\b|a new play|curious incident|before i go to sleep|amadeus|crucible|death of a salesman|blithe spirit|importance of being earnest|pygmalion|\bnt live\b|murder in the cathedral|golden boy"),
    ("Music", r"in concert|\bsings\b|unplugged|acoustic|anniversary tour|\bgig\b|live in concert"),
    ("Talk", r"an evening with|in conversation|\btalk\b|lecture|q ?& ?a\b|storytelling"),
    ("Event", r"\bbingo\b|\bquiz\b|afternoon tea|\bmarket\b|\bfair\b|disco|supper club|\byoga\b|workshop|private bar|open day"),
]
_COMPILED = [(g, re.compile(rx, re.I)) for g, rx in _RULES]


def guess_genre(title):
    t = (title or "").strip()
    low = re.sub(r"\s*[-–:|]\s*(the )?musical$", "", t.lower()).strip()
    low = re.sub(r"^(the )?", "", low) if low not in _MUSICAL_EXACT else low
    if t.lower() in _MUSICAL_EXACT or low in _MUSICAL_EXACT or ("the " + low) in _MUSICAL_EXACT:
        return "Musical"
    for g, rx in _COMPILED:
        if rx.search(t):
            return g
    return ""


def from_ticketmaster(cls):
    """Map a Ticketmaster classification ({segment, genre, subGenre}) to our labels, or ''."""
    def nm(k):
        v = ((cls or {}).get(k) or {}).get("name") or ""
        return "" if v.lower() in ("undefined", "other", "") else v.lower()
    seg, g, sg = nm("segment"), nm("genre"), nm("subGenre")
    if seg == "music":
        return "Classical" if ("classical" in g or "opera" in g or "classical" in sg) else "Music"
    if seg == "arts & theatre":
        if "comedy" in g or "comedy" in sg:
            return "Comedy"
        if "musical" in sg or "musical" in g:
            return "Musical"
        if "children" in g or "children" in sg or "family" in g:
            return "Family"
        if "dance" in g or "ballet" in g:
            return "Dance"
        if "opera" in g or "classical" in g:
            return "Classical"
        if "magic" in g or "magic" in sg or "variety" in g or "circus" in g:
            return "Variety"
        if "theatre" in g or "play" in g or "drama" in sg or "play" in sg:
            return "Play"
        return "Event"
    if seg in ("miscellaneous", "film"):
        return "Family" if ("family" in g or "children" in g) else ("Comedy" if "comedy" in g else "Event")
    return ""
