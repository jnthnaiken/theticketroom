"""nba_voice.py -- COLLINS2-2026-10-25. The basketball write-ups, rewritten, with a memory.

Owner, 10-25: "the basketball writeups are repeating way too much. i would prefer it if they didnt repeat at all.
like on all boards. none of this sounds like nick collins to be honest" (he means Eric Collins, the Hornets'
play-by-play man -- same voice COLLINS-2026-10-19 aimed at and missed).

MEASURED BEFORE: the last three NBA boards printed 106 sentences with 49 repeats inside a board and 22 lines that
came back the next night ("It all starts in the circle" x4 on 10-24, "Hold onto your hats" x3). Every line was a
generic shout ending in "!", which is ESPN-hype, not a play-by-play man.

THE REGISTER NOW (original lines, none of his own trademark calls):
  * He CALLS THE PLAY. Each player gets a little imagined first possession -- the tip, the curl, the cut, the
    finish -- drawn from the angle the model earned (tip / early shots / finishing / sleeper).
  * Alliterative nicknames hung on the surname ("Kilowatt Kuzma"), the way he names everybody.
  * Homespun Carolina flavour: sweet tea, biscuits, the Queen City, the porch, the county fair.
  * Rhythm, not volume: short bursts, stretched vowels, a full stop as often as a bang.

THE MEMORY: Mem.pick() never reuses a phrasing on the same board, and skips any phrasing printed on the previous
RECENT archived boards while another one is left. Banks are big enough that a night uses well under half of each.
Deterministic: same date + same prior boards + same ticket order => same words, every rebuild.
"""
import glob, json, os, re

RECENT = 2
_STRIP = ' ,.;:!?—-–\'"'


def _fnv(key):
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def core(tpl):
    """The longest literal stretch of a template between its placeholders, lowercased."""
    parts = re.split(r'\{[a-z]+\}', tpl)
    best = max((p.strip(_STRIP) for p in parts), key=len, default='').lower()
    return best if len(best) >= 8 else None


def recent_text(boards_dir, date, n=RECENT):
    """Every note and card printed on the last n archived boards before `date`, lowercased."""
    out = []
    fs = sorted(f for f in glob.glob(os.path.join(boards_dir, '*.json')) if os.path.basename(f)[:10] < date)[-n:]
    for f in fs:
        try:
            D = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        out += [t.get('note') or '' for t in D.get('tickets', [])]
        P = D.get('players') or {}
        out += [(p or {}).get('why') or '' for p in (P.values() if isinstance(P, dict) else [])]
    return ' '.join(out).lower()


class Mem:
    def __init__(self, date='', recent=''):
        self.date, self.recent, self.used, self.uses = date, recent or '', set(), {}

    def pick(self, bank, key):
        order = sorted(bank, key=lambda x: _fnv(self.date + '|' + key + '|' + x))
        def ok(x, fresh):
            c = core(x)
            if c is None: return True
            if c in self.used: return False
            return not (fresh and c in self.recent)
        x = next((x for x in order if ok(x, True)), None) or next((x for x in order if ok(x, False)), None)
        if x is None:   # bank spent tonight: least used
            x = min(order, key=lambda y: self.uses.get(core(y), 0))
        c = core(x)
        if c:
            self.used.add(c); self.uses[c] = self.uses.get(c, 0) + 1
        return x


# ---------------------------------------------------------------------------------------------- the calls
TIP = [
    "Ball goes up, {s} goes up higher, and the {t} have it.",
    "{s} in the circle, the ref tosses it, and {s} swats it right to a teammate.",
    "Up goes the ball, up goes {s}, and the {t} come out running.",
    "{s} reaches for the rafters on the opening toss and taps it home to the {t}.",
    "Jump ball, and {s} plays it like a volleyball spike.",
    "{s} wins the tip, gets it right back on the block, and goes to work.",
    "{s} controls the toss, the {t} swing it inside, and here comes {s} again.",
    "It's {s} at center court, all elbows and knees and ambition.",
    "{s} springs off that hardwood like somebody swapped it for a trampoline.",
    "Toss goes up, and {s} meets it like they had a lunch date.",
    "{s} paws the tip, rolls to the rim, and the {t} feed him.",
    "Opening tip: {s} up, {s} early, {s} everywhere.",
    "{s} taps it back and posts up before the defense ties its shoes.",
    "Center jump, {s} against the world, and the world is losing.",
    "{s} gets up so high on the tip he could change a light bulb.",
    "The ref flips it, {s} flicks it, and the {t} are off to the races.",
    "Tip to the {t}, a quick swing, and {s} is sealing his man under the basket.",
    "{s} plants his feet in the circle like a porch post in red clay.",
    "{s} wins the jump, trails the play, and the {t} find him all alone.",
    "Here's {s} at the opening toss, long arms, big hands, bigger plans.",
    "{s} gets the first touch with his fingertips, the second with both hands.",
    "{s} wins the tip, and the {t} run the first set right back through him.",
    "{s} squares up in the circle, the whistle blows, and he's already in the air.",
    "Tip goes to the {t}, and {s} is rumbling down the lane right behind it.",
    "{s} flicks the tip to the wing like he's dealing cards.",
    "The ball barely leaves the ref's hand before {s} slaps it to the {t}.",
    "{s} times the toss like a man catching the last bus home.",
    "Here we go: {s} versus the other big, and {s} gets there a hair early.",
    "{s} rises, taps, and runs. The {t} have the ball and he wants it back.",
    "Opening toss, {s} skies for it, and the {t} start on offense.",
    "{s} wins it clean, then camps out on the block waiting for the entry pass.",
    "{s} tips it forward and beats everybody to the rim.",
    "Big man, big jump, big chance. That's {s} at the start of the night.",
    "{s} goes up like he's reaching for the top shelf at the grocery store.",
    "Jump ball. {s} wins it, and the {t} go right back to the paint.",
    "{s} gets the tip, the {t} get the ball, and the big fella gets position.",
    "Ref throws it up, {s} sends it to the {t} with a smile.",
    "{s} at the opening jump, and he's got springs in those sneakers tonight.",
    "{s} rakes the tip and trots to the block like he owns the place.",
    "The {t} send {s} to the circle, and the circle sends the ball to the {t}.",
    "Here's {s}, crouched and coiled at center court. Up he goes.",
    "{s} gets a fingernail on the toss, and a fingernail is all he needs.",
    "Toss, tap, sprint, seal. That's the {s} special.",
    "{s} wins the opening tip and the {t} go right at the rim with him.",
    "{s} gets the jump on the jump ball, and the {t} are in business.",
    "{s} meets that toss at its peak and steers it straight to the {t} point guard.",
    "Up it goes at center court, and {s} snatches the first possession for the {t}.",
    "{s} tips it, the {t} push it, and he rolls for the first look.",
    "There's {s} in the circle, long as a summer day, and twice as hot.",
    "Win the tip, then dive to the rim: that's how {s} likes to start the evening.",
]
TIPWIN = [
    "He wins those tips like he's got the ref on speed dial.",
    "He has been owning that circle all season long.",
    "Win the tip, take the first swing, and nobody wins the tip like him.",
    "That center circle is his front yard, and he mows it every night.",
    "He gets up there first more often than not, and that's where this bet lives.",
    "Tip after tip after tip, the man just keeps winning them.",
    "He treats the opening jump like a family heirloom: he does not let it go.",
    "Ask around the league who wins the tip, and they all point at him.",
    "When the ball goes up, he's the one coming down with it.",
    "His tip record reads like a winning streak at the county fair.",
    "He controls that toss more nights than he doesn't.",
    "Nobody on the slate gets off the floor at the opening tip quite like him.",
    "Give him the circle and he'll give his team the ball. Nearly every night.",
    "He's been first to the ball on the opening toss all year.",
    "That jump ball might as well have his name stitched on it.",
    "The opening tip is his specialty, and the {t} know it.",
    "He wins the tip, and the team that wins the tip gets the first crack.",
    "He's got a knack for the tip that you just can't teach.",
    "His hand gets to that ball first like it's magnetized.",
    "The tip is where he does his best work, and he does it often.",
]
EARLY = [
    "The {t} swing it to {s}, and he lets it go without a second thought.",
    "First trip down, {s} curls off the screen and lets it rip.",
    "{s} catches it on the wing, and that trigger finger is itchy.",
    "The {t} call {s}'s number first, and he doesn't need asking twice.",
    "{s} gets the first touch, gives his man a little shimmy, and fires.",
    "Here's {s}, first possession, pulling up like the shot clock owes him rent.",
    "{s} comes off the pin-down, catches, rises, and the {t} bench is already standing.",
    "The ball's in {s}'s hands before the crowd has found its seats.",
    "{s} jab-steps, steps back, and lets the first shot of the night fly.",
    "The {t} draw it up for {s} out of the gate, and he obliges.",
    "{s} hunts that first look like a kid hunting Easter eggs.",
    "Opening set, {s} on the move, and he's shooting it before you can say tip-off.",
    "{s} gets downhill on the first possession, and nobody's stepping in front of that freight train.",
    "{s} brings it up, sizes it up, and puts it up.",
    "Early clock, {s} on the elbow, and you can see the wheels turning: he's shooting this.",
    "{s} doesn't wait for the game. He goes and gets it.",
    "The {t} love to start with {s}, and {s} loves to start with a shot.",
    "{s} hits the hesitation, and his man is still looking for his shoe.",
    "First action of the night: high screen for {s}, and he's pulling from the logo.",
    "{s} gets it in the corner, one dribble, two feet, let it go.",
    "{s} takes the opening swing for the {t} more nights than not.",
    "Before the sweat even starts, {s} has the ball and a look in his eye.",
    "The {t} run it to {s} like water running downhill.",
    "{s} gets loose in transition off the very first stop, and he's not passing it.",
    "The {t} come out of the huddle looking for {s}, and he's looking for the rim.",
    "{s} gets the ball on the first trip, rocks his man to sleep, and rises.",
    "First possession, {s} on the left wing, and he's not here to pass.",
    "{s} gets a step on the opening play and takes it all the way.",
    "The {t} set a screen for {s} before anybody's broken a sweat, and up it goes.",
    "{s} pulls the trigger first, asks questions later.",
    "{s} catches it off the curl, and you can see the shot leaving before it does.",
    "Opening minute, {s} gets the ball at the top of the key, and it's go time.",
    "The first play for the {t} has {s}'s name written all over it.",
    "{s} shakes loose on the baseline and the {t} find him on their opening trip.",
    "Here's {s}, first time down, letting it fly like a man late for dinner.",
    "{s} starts every night with a shot, and tonight should be no different.",
    "The {t} put the ball in {s}'s hands to start, and he puts it up.",
    "{s} ducks into the lane on the first possession, and here comes the floater.",
    "{s} sees daylight on the opening play and runs right through it.",
    "Early offense for the {t}, and early offense means {s}.",
    "{s} gets the first look, and he never met a first look he didn't like.",
    "{s} waves off the screen, goes one-on-one, and lets it go.",
    "Watch {s} on the opening set: one fake, one dribble, one shot.",
    "{s} is first off the screen and first to fire.",
    "The {t} swing it twice, and it ends up where it always does: {s}.",
    "{s} hits the gas on the opening possession and doesn't tap the brakes.",
    "{s} gets a clean look on the first trip and takes it before anybody can blink.",
    "The {t} offense opens with a {s} isolation, and he's licking his chops.",
]
FIN = [
    "{s} catches it at the rim and lays it in softer than a pillow.",
    "{s} rolls to the cup, and the {t} drop it right into his hands.",
    "{s} goes up strong and finishes with a little kiss off the glass.",
    "{s} slides behind the defense for the easy two, nothing but layup.",
    "{s} gets his touch at the basket, and that touch is pure butter.",
    "{s} slips the screen, catches the lob, and throws it down.",
    "{s} doesn't waste shots. He picks his spot and drops it in.",
    "Drop-off to {s}, up and in, easy as a Sunday morning.",
    "{s} finishes around the rim like he's signing an autograph.",
    "{s} seals, catches, turns, and it's in. Simple as cornbread.",
    "When {s} shoots it, it tends to go in, and that's the whole ballgame.",
    "{s} gets the dump-off in the paint and doesn't even look at the rim. Doesn't need to.",
    "{s} with the soft hook over the top, and the net barely moves.",
    "{s} just keeps making them, and a made shot is the only kind that counts here.",
]
SNEAK = [
    "Now here's a name nobody circled: {s} for the {t}.",
    "{s} floats to the corner, the defense forgets about him, and that's all it takes.",
    "Everybody's watching the stars, so {s} just strolls in for the first bucket.",
    "{s} is the fella the scouting report put on page nine, and that's where we found him.",
    "{s} for the {t}, quiet as a church mouse until he isn't.",
    "{s} catches the defense napping on the very first possession.",
    "Don't look now, but {s} is lurking for the {t}.",
    "{s} gets the leftovers, and some nights the leftovers are the whole buffet.",
    "Nobody's guarding {s}, and that's a mistake the {t} love to punish.",
    "{s} cuts backdoor while everybody's busy watching the ball.",
    "{s} is the sleeper pick, and we're setting an alarm for him.",
    "{s} sneaks in for the {t} like a cat burglar in sneakers.",
    "A little cut, a little catch, a little bucket for {s}.",
    "{s} is the kind of guy who scores first and then acts surprised about it.",
    "{s} at a long price, and long prices are where the fun lives.",
    "They'll be leaving {s} open, and he's got the receipts to make 'em pay.",
    "{s} is the dark horse in the {t} barn, and that horse can run.",
    "{s} sets up shop on the weak side and waits for somebody to forget him.",
    "You won't find {s} on the billboard outside, but you might find him on the scoreboard first.",
    "{s} is a whole lot of upside wearing a {t} jersey.",
    "Sneaky little play here: {s}, crashing the glass on the first miss.",
    "Here's {s}, flying under the radar so low he's scraping the parking lot.",
    "{s} is the surprise in the gift bag, and we love a surprise.",
    "Keep an eye on {s}, because the defense sure won't.",
    "{s} for the {t}, the name you'll be googling at halftime.",
    "Nobody drew up a play for {s}, so he drew one up for himself.",
    "{s} drifts to the dunker spot and waits for the gift.",
    "{s} is the long shot with a short memory and a quick trigger.",
    "Little-known {s} for the {t}, and the little-known guys are the fun ones.",
    "Here's {s}, the guy you'd skip on the program and shouldn't.",
    "{s} grabs the first offensive rebound and lays it right back up.",
    "Just when the defense loads up on the stars, {s} slips in the side door.",
    "{s} is a price you can't ignore and a player they'll forget to guard.",
    "Hidden gem alert: {s} for the {t}.",
]
RIFF = [
    "Mercy me!", "Somebody check the smoke detectors!", "Pass the sweet tea, we're cooking!",
    "Put that one on a postcard!", "Mm-mm-MM, that's a good-looking bucket!", "Ring the dinner bell!",
    "Lord have mercy, what a start!", "Hot biscuit, right out of the oven!", "Ohhh, it's a party now!",
    "Somebody call the fire marshal!", "Get that man a milkshake!", "Shimmy, shake and bake!",
    "Wowza-wowza!", "Fresh out of the toaster!", "Holy guacamole!", "Spicier than a plate of hot chicken!",
    "Somebody frame that one!", "Bing, bang, buckets!", "Whoo-wee!", "Like a hummingbird on a sugar rush!",
    "Smoother than grandma's gravy!", "That's a county-fair blue ribbon right there!",
    "Ohhhh, I like the way that smells!", "Butter on a biscuit!", "Tell your friends, tell your neighbors!",
    "Lightning in a mason jar!", "That's a two-scoop sundae!", "Somebody turn the porch light on!",
    "Easy-peasy, lemon-squeezy!", "Ooh, that's tasty!", "Put some mustard on that!",
    "Can I get a witness!", "Sizzle, sizzle!", "Hide the good china!", "Yes sir, yes ma'am!",
    "He's cooking with gas now!", "Fireworks, and it isn't even July!", "Oh, that's nasty!",
    "Smooth like a fresh jar of honey!", "Gimme some more of that!", "Buckle up, buttercup!",
    "Well, butter my backside!",
]
NICK = {
    'a': ['Atomic', 'All-Day', 'Avalanche'], 'b': ['Buckets', 'Big-Time', 'Bulldozer'],
    'c': ['Cannonball', 'Cool-Hand', 'Cyclone'], 'd': ['Dynamite', 'Daylight', 'Downtown'],
    'e': ['Electric', 'Easy-Money', 'Express'], 'f': ['Firecracker', 'Fast-Lane', 'Fearless'],
    'g': ['Gravy-Train', 'Greenlight', 'Gusher'], 'h': ['Hurricane', 'Hot-Hand', 'High-Rise'],
    'i': ['Ice-Water', 'Instant', 'Iron'], 'j': ['Jet-Pack', 'Jukebox', 'Jumpin\''],
    'k': ['Kilowatt', 'Knockout', 'Kaboom'], 'l': ['Lightning', 'Lights-Out', 'Lunch-Pail'],
    'm': ['Mighty', 'Money', 'Moonshot'], 'n': ['Nitro', 'Nothin\'-But-Net', 'No-Doubt'],
    'o': ['Overdrive', 'Old-School', 'Off-The-Glass'], 'p': ['Powerhouse', 'Pogo-Stick', 'Pure'],
    'q': ['Quick-Draw', 'Quicksilver', 'Queen-City'], 'r': ['Rocket', 'Rattlesnake', 'Rim-Rattlin\''],
    's': ['Splash', 'Sky-High', 'Sizzlin\''], 't': ['Thunder', 'Turbo', 'Tip-Top'],
    'u': ['Unstoppable', 'Upstairs', 'Uptown'], 'v': ['Voltage', 'Velvet', 'Vroom-Vroom'],
    'w': ['Wildfire', 'Whirlwind', 'Wrecking-Ball'], 'x': ['X-Factor'], 'y': ['Yo-Yo', 'Yowza'],
    'z': ['Zoom', 'Zippy', 'Zapper'],
}
NICKLINE = ["{k} {s}!", "Here's {k} {s}.", "They call him {k} {s}, and I just did too.", "{k} {s}, y'all."]
OPEN = [
    'Pull up a chair!',
    'Four games, four tips, one parade.',
    'Ladies and gentlemen, your starting lineup!',
    'Saddle up, partner.',
    "It's a four-course meal.",
    "Gather 'round, folks.",
    '{a} leads the conga line.',
    'Four arenas, one big night.',
    'Spin the wheel!',
    '{a} is the headliner.',
    'Everybody came hungry.',
    'Road trip! First stop, {a}.',
    "Oh, this one's a stew.",
    'Roll call!',
    'Grab a plate.',
    '{a} drives, the rest ride along.',
    "Knock knock. Who's there? Buckets.",
    'Four tips go up tonight.',
    'Fresh out the oven!',
    "The whole family's here.",
    'Here comes the parade!',
    "It's a barn dance, y'all.",
    "Four horses in this race. They're off!",
    "Line 'em up!",
    'Tip it off, baby!',
    'Strike up the band!',
    'Hold onto the porch railing.',
    'The doors are open!',
]
TEMPLE_OPEN = [
    "Welcome to Garrett's Temple: the four likeliest first scorers on the board.",
    'Garrett lays the foundation, poured from chalk.',
    'Four pillars hold up the Temple tonight.',
    "Shoes off at the door, this is Garrett's Temple.",
    'The Temple doors swing open.',
    "Sunday best, folks. It's Garrett's Temple.",
    'Garrett built this one brick by brick.',
    'Light a candle in the Temple for the chalk of the night.',
]
TAIL = [
    "Somebody tell the neighbors, this ticket's got a pulse!", "Strap in. Bumpy ride, beautiful view.",
    "Bring the big foam finger!", "We're letting it ride, baby!", "Lights down low, volume up high!",
    "Cue the confetti cannon!", "Pack a lunch, this one goes the distance.", "That's a ticket you write home about!",
    "Cross your fingers, cross your toes, cross the street if you have to!",
    "If this one hits, I'm dancing in the parking lot!", "Ticket's in, nerves are on.", "Nobody blink!",
    "Get the band warmed up!", "Light the grill, we might be celebrating early.",
    "The Queen City would be proud of this one.", "Let 'er rip!", "Put it in the oven and let it bake.",
    "It's a lottery ticket with a jump shot!", "Bold as brass, and twice as shiny.", "Hold my sweet tea!",
    "Bless its heart, this ticket's got big dreams.", "Swing big, baby!", "Ain't nothing quiet about this one.",
    "Tip it off already, I can't stand the wait!", "Somebody get the camera rolling.",
    "Four doors, four keys, let's open 'em up.", "That's the whole enchilada, folks.",
    "Fire up the jukebox, we're feeling good.",
    "Set it, forget it, and pray a little.",
    "Here's hoping the basketball gods are in a good mood.",
    "Sweet dreams are made of tickets like this.",
    "Hang on to the railing, folks.",
    "The porch light's on, come on home, ticket.",
    "Shake it up and pour it out!",
    "That's a ticket with some swagger.",
    "Let the good times roll!",
    "We're swinging for the rafters tonight.",
    "Go on and get it, boys!",
]
TEMPLE_TAIL = [
    "Say a little prayer and let the Temple stand!", "Built on rock, built on chalk, built by Garrett.",
    "The Temple's open for business!", "Amen, and pass the biscuits!", "Garrett's got the keys, and the doors are open.",
    "Ring the bells in the Temple tonight!",
]


# COLLINS3-2026-10-25. Owner: "a quick google search will do it" -- his real calls, sparingly. These are his own
# (si.com/nba/hornets "best Eric Collins quotes"; buzzbeat.substack.com "Eric Collins best quotes 2021-2025"): at most
# SIG_MAX a board, each once, and not one printed on the last two boards.
SIGNATURE = ["Hum diddly dee!", "Hotter than fish grease!", "Tougher than woodpecker lips!",
             "With the guts of a cat burglar!", "Tougher than a two-dollar steak!", "On like a pot of neckbones!",
             "Quicker than a hiccup!", "Stronger than a brand new rope!", "Quicker than a small-town rumor!",
             "With the touch of a masseuse!", "Gravel in his guts!"]
SIG_MAX = 2
# His FORMULA, our words: the homespun "-er than" comparison, matched to the angle the model earned.
COMPARE = {
    'tip': ["Tougher than a two-day-old biscuit!", "Taller than a church steeple on Easter morning!",
            "Tougher than a boiled boot!", "Sturdier than a front-porch rocker!", "Bigger than a Thanksgiving ham!",
            "Stronger than truck-stop coffee!", "Tougher than a county-fair blue-ribbon hog!", "Higher than a kite in March!",
            "Steadier than a grandfather clock!", "Taller than a tobacco barn!", "Tougher than a hickory stump!",
            "Stronger than a mule with a grudge!"],
    'early': ["Hotter than a skillet in July!", "Hotter than a pepper-eating contest!", "Hotter than a tin roof in August!",
              "Hotter than a two-dollar pistol!", "Hotter than the asphalt at a summer cookout!",
              "Hotter than a fresh-fried hush puppy!", "Quicker on the trigger than a spring-loaded mousetrap!",
              "Hotter than a jalapeño in a sauna!", "Hotter than a stolen tamale!", "Hotter than Granny's woodstove!",
              "Hotter than a tailgate grill!", "Hotter than Charlotte pavement at noon!"],
    'fin': ["Smoother than a fresh jar of honey!", "Softer than a kitten's whisper!", "Smoother than Sunday gravy!",
            "Softer than a feather pillow!", "Smoother than a church-pew bench!", "Cleaner than a Sunday shirt!",
            "Smoother than a buttered biscuit!", "Softer than a peach in June!"],
    'sneak': ["Quicker than a jackrabbit in a thunderstorm!", "Sneakier than a raccoon at the trash can!",
              "Quieter than a mouse in socks!", "Quicker than gossip at the beauty shop!",
              "Sneakier than a fox in the henhouse!", "Quicker than a cat on a hot stovetop!",
              "Slipperier than a greased pig at the fair!", "Quicker than a preacher's amen!",
              "Sneakier than a possum playing dead!", "Quicker than a squirrel crossing the highway!",
              "Sneakier than a kid in the cookie jar!", "Quicker than a hummingbird's wings!"],
}


def _flourish(angle, key, mem):
    """A signature call (rare), else his comparison formula in our words, else a riff."""
    sig = mem.__dict__.setdefault('sigs', 0)
    r = _fnv(mem.date + 'fl' + key) % 6
    if r == 0 and sig < SIG_MAX:
        x = mem.pick(SIGNATURE, 'sig|' + key)
        if x and core(x) and core(x) not in mem.recent:
            mem.sigs = sig + 1
            return x
    if r <= 3:
        return mem.pick(COMPARE.get(angle, COMPARE['sneak']), 'cmp|' + key)
    return mem.pick(RIFF, 'riff|' + key)


def _nick(sur, key, mem):
    """One nickname per man per board, and no nickname word twice on a board. None when spent."""
    nk = mem.__dict__.setdefault('nicked', set()); words = mem.__dict__.setdefault('nickwords', set())
    if sur in nk: return None
    ks = [x for x in (NICK.get((sur[:1] or 'x').lower()) or NICK['x']) if x not in words]
    if not ks: return None
    k = sorted(ks, key=lambda x: _fnv(mem.date + key + x))[0]
    nk.add(sur); words.add(k)
    return mem.pick(NICKLINE, 'nl|' + key).format(k=k, s=sur)


def _nickname(sur, key, mem):
    """COLLINS4: the nickname rides inline ("Kilowatt Kuzma takes ...") instead of as its own sentence."""
    nk = mem.__dict__.setdefault('nicked', set()); words = mem.__dict__.setdefault('nickwords', set())
    if sur in nk: return None
    ks = [x for x in (NICK.get((sur[:1] or 'x').lower()) or NICK['x']) if x not in words]
    if not ks: return None
    k = sorted(ks, key=lambda x: _fnv(mem.date + key + x))[0]
    nk.add(sur); words.add(k)
    return k + ' ' + sur


def player_line(sur, team, angle, key, mem, strong_tip=False, extra=None):
    """COLLINS4-2026-10-25 (owner: "shorten the writeups ... just a tad. theyre just a bit too wordy. keep all the eric
    collinsisms though"): one call per player; the nickname goes inline; an add-on line (his comparison, a signature
    call, or the tip record) on about one leg in three instead of two in three."""
    bank = {'tip': TIP, 'early': EARLY, 'fin': FIN}.get(angle, SNEAK)
    tpl = mem.pick(bank, angle + '|' + key)
    r = _fnv(mem.date + key) % 3
    if extra is not None:   # the caller decides which ONE leg of a ticket gets the add-on line
        r = 1 if extra else (0 if r == 0 else 2)
    who = sur
    if r == 0:
        who = _nickname(sur, key, mem) or sur
    call = tpl.replace('{s}', who, 1).format(s=sur, t=team or 'squad')
    if call[:1].islower(): call = call[:1].upper() + call[1:]
    if r == 1:
        if strong_tip:
            return call + ' ' + mem.pick(TIPWIN, 'tw|' + key).format(t=team or 'squad')
        return call + ' ' + _flourish(angle, key, mem)
    return call


def ticket_note(surs, lines, key, mem, temple=False):
    a, b, c, d = (surs + [''] * 4)[:4]
    op = mem.pick(TEMPLE_OPEN if temple else OPEN, 'open|' + key).format(a=a, b=b, c=c, d=d)
    tl = mem.pick(TEMPLE_TAIL if temple else TAIL, 'tail|' + key)
    return ' '.join([op] + lines + [tl])


# ---------------------------------------------------------------------------------------------- the cards
CARD = {
    'tipw': ["owns the center circle, and he's been winning that tip all season",
             "is the guy you want jumping center, and the tip history backs it up",
             "goes up for the opening toss and usually comes down with it",
             "has the tip-off down to a science",
             "wins the jump more often than he loses it, and that's a head start"],
    'tip': ["handles the opening tip for his side",
            "is the big fella in the center circle",
            "jumps center, so the night starts in his hands",
            "takes the opening toss, and the first look often follows",
            "stands in the circle when the ball goes up"],
    'early': ["hunts the early shots like nobody else on his team",
              "gets the ball first and shoots it first",
              "is the first name on the play sheet",
              "lets it fly in the opening minute",
              "takes the first swing of the night more than most",
              "gets his number called on the opening set",
              "has the green light from the very first possession"],
    'fin': ["finishes what he starts around the rim",
            "doesn't waste shots, he makes them",
            "has soft hands and a softer touch at the basket",
            "turns touches into buckets at a tidy clip"],
    'z': ["is out there for the opening tip, ready to rumble",
          "starts the night on the floor, and anything can happen",
          "is a sleeper with real upside",
          "is the quiet name in a loud lineup",
          "is the kind of starter defenses forget about",
          "is a long shot with a pulse",
          "is in the starting five and in the mix",
          "is the under-the-radar starter of the bunch"],
}


def card(n, angle, key, mem):
    return f"{n} {mem.pick(CARD[angle], 'card|' + key)}."
