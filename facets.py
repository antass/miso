"""Auto-detected search facets for a recipe: course, protein, diet, method, minutes.

Keyword heuristics over title / ingredients / steps — good enough to filter on, not gospel.
"""
import re


def _rx(words):
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)


# ingredient phrases that mention an animal but don't make the dish meaty
NOT_PROTEIN = re.compile(r"\b(chicken|beef|vegetable|fish|bone|turkey|pork)\s+(broth|stock|bouillon|base|fat|bones)\b|"
                         r"\bfish sauce\b|\banchov(y|ies)\s+paste\b|\bworcestershire\b|\bpeanut butter\b|"
                         r"\bbutter(milk|nut)\b|\bcelery ribs?\b|\begg wash\b", re.I)

PROTEINS = [
    ("Chicken", _rx(["chicken", "chickens", "poussin", "cornish hens?"])),
    ("Beef", _rx(["beef", "steaks?", "brisket", "chuck", "sirloin", "rib[- ]eye", "short ribs", "flank", "skirt steak", "veal", "oxtail"])),
    ("Pork", _rx(["pork", "bacon", "ham", "sausages?", "prosciutto", "pancetta", "chorizo", "salami", "guanciale", "pork belly", "baby back ribs", "spareribs", "kielbasa"])),
    ("Lamb", _rx(["lamb", "mutton"])),
    ("Turkey", _rx(["turkey"])),
    ("Fish", _rx(["fish", "\\w+fish", "fillets? of \\w+", "salmon", "cod", "halibut", "tilapia", "trout", "sole", "snapper", "tuna", "swordfish", "sea bass", "mackerel", "sardines?", "haddock", "branzino", "catfish", "anchov(?:y|ies)", "arctic char", "maguro"])),
    ("Seafood", _rx(["shrimp", "prawns?", "scallops?", "crab", "lobster", "clams?", "mussels?", "squid", "calamari", "octopus", "oysters?"])),
    ("Tofu & tempeh", _rx(["tofu", "tempeh", "seitan"])),
    ("Beans & lentils", _rx(["chickpeas?", "lentils?", "black beans", "white beans", "cannellini", "kidney beans", "pinto beans", "edamame", "garbanzo", "split peas", "navy beans", "great northern beans", "butter beans"])),
]
MEAT = _rx(["chicken", "beef", "steak", "brisket", "veal", "oxtail", "pork", "bacon", "ham", "sausages?", "prosciutto", "pancetta",
            "chorizo", "salami", "guanciale", "lamb", "mutton", "turkey", "duck", "goose", "venison", "bison", "fish", "salmon",
            "cod", "halibut", "tilapia", "trout", "snapper", "tuna", "swordfish", "sea bass", "mackerel", "sardines?",
            "anchov(?:y|ies)", "shrimp", "prawns?", "scallops?", "crab", "lobster", "clams?", "mussels?", "squid", "calamari",
            "octopus", "oysters?", "gelatin", "lard", "fish sauce", "dashi", "bonito", "katsuobushi", "meat", "meatballs?",
            "pepperoni", "hot dogs?", "broth", "stock", "bouillon"])
VEG_STOCK = re.compile(r"\b(vegetable|veggie|mushroom|kombu)\s+(broth|stock|bouillon)\b", re.I)
DAIRY = _rx(["milk", "butter", "cream", "cheese", "cheddar", "parmesan", "parmigiano", "pecorino", "mozzarella", "feta", "ricotta",
             "yogurt", "yoghurt", "sour cream", "buttermilk", "ghee", "mascarpone", "gruyère", "gruyere", "crème fraîche",
             "creme fraiche", "half-and-half", "brie", "goat cheese", "whey", "paneer", "queso"])
NONDAIRY = re.compile(r"\b(coconut|almond|oat|soy|cashew|rice)\s+(milk|cream|butter|yogurt)\b|\bpeanut butter\b|\bnut butter\b|"
                      r"\bcocoa butter\b|\bcream of tartar\b|\bbutternut\b|\bbutter beans\b|\bvegan\b", re.I)
EGGS = _rx(["eggs?", "egg yolks?", "egg whites?", "mayonnaise", "mayo", "honey", "aioli"])

COURSES = [
    ("Breakfast", _rx(["breakfast", "brunch", "pancakes?", "waffles?", "oatmeal", "oats", "granola", "muffins?", "frittatas?", "omelets?",
                       "omelettes?", "scramble", "scrambled", "french toast", "porridge", "hash browns?", "egg bakes?", "quiche",
                       "scones?", "crêpes?", "crepes?", "shakshuka", "chia pudding", "breakfast burritos?", "bagels?", "huevos"])),
    ("Soups & stews", _rx(["soups?", "stews?", "chili", "chowders?", "bisque", "ramen", "pho", "gumbo", "pozole", "posole", "minestrone",
                           "gazpacho", "congee", "dal", "dahl", "tagine", "goulash", "bouillabaisse", "cioppino", "borscht", "curry"])),
    ("Salads", _rx(["salads?", "slaw", "coleslaw", "tabbouleh", "panzanella", "niçoise", "nicoise", "caesar"])),
    ("Pasta & noodles", _rx(["pasta", "spaghetti", "linguine", "penne", "lasagna", "lasagne", "noodles?", "mac(?:aroni)?", "gnocchi",
                             "ravioli", "orzo", "rigatoni", "fettuccine", "ziti", "udon", "soba", "lo mein", "pad thai", "tortellini",
                             "bucatini", "orecchiette", "pappardelle", "fusilli", "farfalle", "cacio e pepe", "carbonara", "bolognese"])),
    ("Sandwiches & burgers", _rx(["sandwich(?:es)?", "burgers?", "sliders?", "wraps?", "panini", "subs?", "hoagies?", "grilled cheese",
                                  "sloppy joes?", "banh mi", "toasts?", "quesadillas?"])),
    ("Tacos & bowls", _rx(["tacos?", "burritos?", "enchiladas?", "fajitas?", "bowls?", "nachos", "tostadas?", "poke"])),
    ("Pizza & flatbreads", _rx(["pizzas?", "flatbreads?", "calzones?", "focaccia", "tart flambée", "flammkuchen"])),
    ("Sides", _rx(["sides?", "mashed", "pilaf", "gratin", "fries", "roasted (?:potatoes|carrots|broccoli|cauliflower|vegetables|veggies|brussels sprouts|beets|squash|asparagus|green beans|radishes|parsnips|sweet potatoes)",
                   "glazed carrots", "green beans", "brussels sprouts", "asparagus", "corn on the cob", "creamed spinach",
                   "succotash", "polenta", "risotto", "rice", "potatoes", "stuffing", "dressing \\(stuffing\\)", "biryani"])),
    ("Desserts", _rx(["cakes?", "cookies?", "brownies?", "blondies?", "pies?", "tarts?", "crisp", "cobbler", "puddings?", "ice cream",
                      "sorbet", "gelato", "granita", "fudge", "bars", "cupcakes?", "cheesecakes?", "mousse", "frosting", "icing",
                      "candy", "toffee", "truffles?", "pops", "popsicles?", "custard", "crumble", "doughnuts?", "donuts?",
                      "macarons?", "meringues?", "pavlova", "panna cotta", "tiramisu", "shortbread", "biscotti", "brittle",
                      "caramel", "ganache", "sundae", "parfait", "trifle", "pandowdy", "galette", "baklava", "churros"])),
    ("Breads & baking", _rx(["breads?", "loaf", "loaves", "rolls", "biscuits", "brioche", "baguettes?", "sourdough", "dough", "bagels?",
                             "naan", "tortillas", "pita", "challah", "buns", "pretzels?", "crackers", "starter", "levain", "boule",
                             "ciabatta", "english muffins?", "popovers?", "cornbread", "soda bread"])),
    ("Snacks & appetizers", _rx(["dips?", "hummus", "chips", "bites", "crostini", "salsa", "guacamole", "wings", "popcorn", "snacks?",
                                 "appetizers?", "poppers", "deviled eggs", "bruschetta", "spreads?", "tapenade", "pâté", "pate",
                                 "skewers", "kebabs?", "dumplings?", "gyoza", "pot ?stickers", "spring rolls?", "egg rolls?",
                                 "empanadas?", "fritters?", "croquettes?", "nuts", "trail mix", "energy balls?", "board",
                                 "platter", "crudités", "crudites", "arancini", "samosas?", "sushi", "maki", "nigiri"])),
    ("Drinks", _rx(["smoothies?", "cocktails?", "punch", "lemonade", "tea", "lattes?", "spritzers?", "spritz", "margaritas?",
                    "shakes?", "milkshakes?", "juice", "mimosas?", "sangria", "mocktails?", "cider", "hot chocolate", "cocoa",
                    "martini", "negroni", "paloma", "mojito", "eggnog", "horchata", "lassi", "agua fresca", "kombucha"])),
    ("Sauces & basics", _rx(["sauces?", "dressings?", "vinaigrettes?", "pesto", "stock", "broth", "seasoning", "spice (?:mix|blend|rub)",
                             "rubs?", "marinades?", "aioli", "mayonnaise", "chutney", "relish", "jam", "jelly", "preserves",
                             "pickles?", "pickled", "compound butter", "syrup", "glaze", "gravy", "salsa verde", "chimichurri",
                             "tahini", "ketchup", "mustard", "harissa", "curry paste", "tare", "dashi", "ghee", "ricotta",
                             "yogurt", "butter", "croutons", "breadcrumbs", "salt", "oil", "vinegar", "extract"])),
]
MAIN_HINT = _rx(["casseroles?", "curry", "stir[- ]?fry", "stir[- ]?fried", "skillet", "roast", "roasted chicken", "braised?", "braise",
                 "meatballs?", "meatloaf", "chops?", "steaks?", "fillets?", "thighs", "breasts?", "drumsticks", "wings", "pot pie",
                 "shepherd'?s pie", "enchiladas?", "tacos?", "pizza", "bowls?", "fried rice", "paella", "jambalaya", "kebabs?",
                 "cutlets?", "parm(?:esan)?", "schnitzel", "katsu", "teriyaki", "tikka", "korma", "tagine", "ragù", "ragu",
                 "dinner", "supper", "sheet[- ]pan", "one[- ]pot", "pot roast", "pulled pork", "carnitas", "short ribs"])

# dish types that are a meal on their own, protein or not
DISH_HINT = _rx(["casseroles?", "curry", "stir[- ]?fry", "stir[- ]?fried", "pot pie", "shepherd'?s pie", "enchiladas?", "tacos?",
                 "pizza", "bowls?", "fried rice", "paella", "jambalaya", "lasagna", "chili", "risotto", "frittata", "quiche",
                 "dinner", "supper", "sheet[- ]pan supper"])

METHODS = [
    ("Air fryer", _rx(["air[- ]?fry(?:er|ing)?", "air[- ]?fried", "air fryer basket"])),
    ("Slow cooker", _rx(["slow[- ]?cooker", "slow cook(?:ed|ing)?", "crock[- ]?pot"])),
    ("Instant Pot / pressure", _rx(["instant pot", "pressure[- ]?cook(?:er|ing|ed)?", "high pressure", "quick[- ]release", "natural(?:ly)? release"])),
    ("Sheet pan", _rx(["sheet[- ]pan"])),
    ("One pot / skillet", _rx(["one[- ]pot", "one[- ]pan", "dutch oven", "skillet"])),
    ("Grill", _rx(["grill", "grilled", "grilling", "barbecue", "bbq"])),
    ("Sous vide", _rx(["sous[- ]?vide", "immersion circulator"])),
    ("No-cook", None),   # computed: no heat words anywhere
    ("Freezer-friendly", _rx(["freez(?:e|es|ing)", "freezer", "frozen for up to", "keeps? frozen", "thaw(?:ed)?"])),
    ("Make-ahead", _rx(["make[- ]ahead", "to make ahead", "meal[- ]prep", "(?:up to )?\\d+ (?:days?|hours?) (?:ahead|in advance)",
                        "can be (?:made|prepared|refrigerated)"])),
]
HEAT = _rx(["oven", "bake", "baked", "baking", "roast", "roasted", "broil", "broiler", "grill", "grilled", "sauté", "saute", "sautéed",
            "fry", "fried", "frying", "simmer", "boil", "boiling", "heat", "heated", "microwave", "toast", "toasted", "cook",
            "cooked", "cooking", "sear", "seared", "steam", "steamed", "poach", "poached", "braise", "pressure", "slow cooker",
            "air fryer", "skillet", "saucepan", "pan", "griddle", "melt", "melted", "warm", "preheat"])

TIME_PART = re.compile(r"(\d+(?:\.\d+)?)\s*(?:to|-|–)?\s*(?:\d+\s*)?(hours?|hrs?|hr|h\b|minutes?|mins?|min|m\b)", re.I)
STEP_TIME = re.compile(r"(\d+)(?:\s*(?:to|-|–)\s*(\d+))?\s*(hours?|hrs?|minutes?|mins?)\b", re.I)


def _minutes(text):
    total = 0
    for n, unit in TIME_PART.findall(text):
        total += float(n) * (60 if unit.lower().startswith("h") else 1)
    return int(round(total)) or None


def recipe_minutes(r):
    """(minutes, estimated?) from yield/time lines, else a rough estimate from times in the method."""
    total = prep = cook = None
    for m in r.get("meta") or []:
        low = m.lower()
        if re.match(r"^(total|ready in|start to finish|time\b)", low):
            total = total or _minutes(m)
        elif low.startswith(("prep", "active", "hands")):
            prep = prep or _minutes(m)
        elif low.startswith(("cook", "bake", "pressure", "slow")):
            cook = cook or _minutes(m)
    if total:
        return total, False
    if prep and cook:
        return prep + cook, False
    # estimate: largest duration in each step, summed, plus a little prep
    est = 0
    for s in r.get("steps") or []:
        best = 0
        for a, b, unit in STEP_TIME.findall(s.get("t", "")):
            v = int(b or a) * (60 if unit.lower().startswith("h") else 1)
            best = max(best, v)
        est += min(best, 12 * 60)
    if est:
        return est + (prep or 10), True
    return (prep or cook), bool(prep or cook)


def compute(r, book_title=""):
    title = r.get("title", "")
    ings = [i["t"] for i in r.get("ingredients", []) if not i.get("h")]
    ing_text = " \n ".join(ings)
    ing_clean = NOT_PROTEIN.sub(" ", ing_text)
    steps = " ".join(s.get("t", "") for s in r.get("steps", []))
    notes = " ".join((r.get("notes") or []) + (r.get("headnote") or []))
    everything = " ".join([title, steps, notes, book_title, " ".join(r.get("meta") or [])])
    # "We don't recommend making this ahead / freezing it" shouldn't count
    everything = re.sub(r"[^.]*\b(?:don.t|do not|not recommended|doesn.t|does not|won.t|cannot|can.t)\b[^.]*\.?", " ", everything, flags=re.I)

    protein = [name for name, rx in PROTEINS if rx.search(title) or rx.search(ing_clean)]
    eggs = len(re.findall(r"\beggs?\b", ing_text, re.I))
    if re.search(r"\b(eggs?|frittata|omelet|omelette|quiche|shakshuka)\b", title, re.I) or \
            (eggs and re.search(r"\b([3-9]|1[0-9]|a dozen|6|8)\s+(large\s+)?eggs\b", ing_text, re.I)):
        protein.append("Eggs")

    meat_text = VEG_STOCK.sub(" ", ing_text + " " + title)
    meat_text = re.sub(r"\bbutter(milk|nut)\b|\bpeanut butter\b|\bmeat(less|-free)\b", " ", meat_text, flags=re.I)
    diet = []
    meaty = {"Chicken", "Beef", "Pork", "Lamb", "Turkey", "Fish", "Seafood"} & set(protein)
    if not meaty and not MEAT.search(meat_text) and not re.search(r"(fish|steaks)\b", meat_text, re.I):
        diet.append("Vegetarian")
        dairy_text = NONDAIRY.sub(" ", ing_text)
        if not DAIRY.search(dairy_text) and not EGGS.search(dairy_text):
            diet.append("Vegan")
    if not DAIRY.search(NONDAIRY.sub(" ", ing_text)):
        diet.append("Dairy-free")
    if not re.search(r"\b(flour|bread|breadcrumbs|panko|pasta|noodles|spaghetti|couscous|barley|farro|bulgur|wheat|soy sauce|"
                     r"tortillas?|crackers|beer|croutons|pita|buns?|rolls|cake|cookies|biscuits|pastry|puff pastry|phyllo|"
                     r"orzo|semolina|seitan|rye|malt|graham|sandwich(?:es)?|pizzas?|toasts?|burgers?|sliders?|pies?|tarts?|dumplings?|"
                     r"pancakes?|waffles?|muffins?|scones?|brownies?|croissants?|bagels?|focaccia|lasagna|ravioli|gnocchi)\b", ing_text + " " + title, re.I) or \
            re.search(r"gluten[- ]free", ing_text + " " + title, re.I):
        diet.append("Gluten-free*")

    course = [name for name, rx in COURSES if rx.search(title)]
    sweetish = {"Desserts", "Drinks", "Breakfast", "Breads & baking", "Sauces & basics", "Snacks & appetizers"}
    real_protein = [p for p in protein if p not in ("Eggs", "Beans & lentils")]
    lighter = {"Sides", "Salads"} & set(course)
    dish = DISH_HINT.search(title)
    if not (set(course) & sweetish) and ((real_protein and not lighter) or (dish and not lighter)
                                         or (real_protein and MAIN_HINT.search(title)) or (real_protein and not course)):
        course.append("Mains")
    if not course and re.search(r"\bside", book_title, re.I):
        course.append("Sides")
    if "Sauces & basics" in course and len(course) > 1 and not re.search(r"\b(sauce|dressing|vinaigrette|pesto|stock|broth)$", title, re.I):
        course.remove("Sauces & basics")

    method = []
    for name, rx in METHODS:
        if rx is None:
            if not HEAT.search(steps) and steps:
                method.append(name)
        elif rx.search(title) or rx.search(everything):
            method.append(name)
    # "skillet" is everywhere — only count one-pot when the title / book says so
    if "One pot / skillet" in method and not re.search(r"one[- ]pot|one[- ]pan|skillet", title + " " + book_title, re.I):
        method.remove("One pot / skillet")
    if "Grill" in method and not re.search(r"grill|barbecue|bbq", title + " " + book_title, re.I) and \
            len(re.findall(r"\bgrill", steps, re.I)) < 2:
        method.remove("Grill")

    minutes, est = recipe_minutes(r)
    return {"course": course, "protein": protein, "diet": diet, "method": method,
            "minutes": minutes, "minutesEst": est, "nIng": len(ings)}
