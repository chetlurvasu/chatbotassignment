import pandas as pd
import re

# additional requriements / consequences: touristic, assigned seats, children, romantic

REQUIREMENT_PATTERNS = {
    "romantic": [
        r"\bromantic\b"
    ],
    "touristic": [
        r"\btouristic\b",
        r"\btouristy\b",
        r"\btourist\b"
    ],
    "assigned_seats": [
        r"\bassigned seats?\b",
        r"\bassigned seating\b"
    ],
    "children": [
        r"\bchildren\b",
        r"\bchild[- ]friendly\b",
        r"\bsuitable for children\b",
        r"\bwith my children\b",
        r"\bchild\b",
    ]
}

DIRECT_REQUIREMENT_PATTERNS = {
    "pricerange": {
        "cheap": [
            r"\bcheap\b",
            r"\binexpensive\b",
            r"\baffordable\b",
            #-----------------------
            r"\bcheaper\b",
            r"\bcheapest\b",
            r"\bbudget\b",
            r"\bbudget friendly\b",
            r"\bon a budget\b",
            r"\blow cost\b",
            r"\blow priced\b",
            r"\blow price\b",
            r"\beconomical\b",
        ],
        "moderate": [
            r"\bmoderate\b",
            r"\bmoderately priced\b",
            #-----------------------
            r"\bmid priced\b",
            r"\bmid range\b",
            r"\bmedium priced\b",
            r"\bfairly priced\b",
            r"\breasonably priced\b",
            r"\bgood value\b",
        ],
        "expensive": [
            r"\bexpensive\b",
            r"\bpricey\b",
            #-----------------------
            r"\bpricier\b",
            r"\bcostly\b",
            r"\bhigh priced\b",
            r"\bhigh end\b",
            r"\bupscale\b",
            r"\bfine dining\b",
            r"\bluxury\b",
            r"\bsplurge\b",
        ]},
    "area": {
        "centre": [r"\bcentral\b", r"\bcity centre\b", r"\bcentre\b"],
        "north": [r"\bnorth\b"],
        "south": [r"\bsouth\b"],
        "east": [r"\beast\b"],
        "west": [r"\bwest\b"],
    },
   
    "food": {
        "british": [r"\bbritish\b"],
        "modern european": [r"\bmodern european\b"],
        "italian": [r"\bitalian\b"],
        "romanian": [r"\bromanian\b"],
        "seafood": [r"\bseafood\b"],
        "chinese": [r"\bchinese\b"],
        "steakhouse": [r"\bsteakhouse\b"],
        "asian oriental": [r"\basian oriental\b"],
        "french": [r"\bfrench\b"],
        "portuguese": [r"\bportuguese\b"],
        "indian": [r"\bindian\b"],
        "spanish": [r"\bspanish\b"],
        "european": [r"\beuropean\b"],
        "vietnamese": [r"\bvietnamese\b"],
        "korean": [r"\bkorean\b"],
        "thai": [r"\bthai\b"],
        "moroccan": [r"\bmoroccan\b"],
        "swiss": [r"\bswiss\b"],
        "fusion": [r"\bfusion\b"],
        "gastropub": [r"\bgastropub\b"],
        "tuscan": [r"\btuscan\b"],
        "international": [r"\binternational\b"],
        "traditional": [r"\btraditional\b"],
        "mediterranean": [r"\bmediterranean\b"],
        "polynesian": [r"\bpolynesian\b"],
        "african": [r"\bafrican\b"],
        "turkish": [r"\bturkish\b"],
        "bistro": [r"\bbistro\b"],
        "north american": [r"\bnorth american\b"],
        "australasian": [r"\baustralasian\b"],
        "persian": [r"\bpersian\b"],
        "jamaican": [r"\bjamaican\b"],
        "lebanese": [r"\blebanese\b"],
        "cuban": [r"\bcuban\b"],
        "japanese": [r"\bjapanese\b"],
        "catalan": [r"\bcatalan\b"],
        "pizza": [r"\bpizza\b"],
        "pasta": [r"\bpasta\b"],
    },

    "crowdedness": {
        "busy": [r"\blively\b", r"\bbusy\b"],
        "not busy": [r"\bquiet\b", r"\bnot busy\b"],
    },
    "length_of_stay": {
        "long": [r"\blong dinner\b", r"\bstay for a long time\b"],
        "short": [r"\bquick meal\b", r"\bquick dinner\b"],
    },
    "food_quality": {
        "good": [r"\bgood food quality\b", r"\bgood food\b"],
        "mediocre": [r"\bmediocre\b"],
    },
    "takeaway": {
        True: [r"\btakeaway\b", r"\btake out\b"],
    },
}

RELAX_REQUIREMENT_PATTERNS = {
    "area": [
        r"\bany area\b",
        r"\banywhere\b",
        r"\barea doesn't matter\b",
        r"\barea does not matter\b",
        r"\bdon't mind the area\b",
        r"\bdoesn't matter where\b",
    ],
    "food": [
        r"^\s*any food\s*[.!?]*\s*$",
        r"^\s*any cuisine\s*[.!?]*\s*$",
        r"\bfood doesn't matter\b",
        r"\bcuisine doesn't matter\b",
        r"\bdon't mind the food\b",
    ],
    "pricerange": [
        r"\bany price\b",
        r"\bany price range\b",
        r"\bprice doesn't matter\b",
        r"\bprice range doesn't matter\b",
    ],
    "crowdedness": [
        r"\bany crowdedness\b",
        r"\bcrowdedness doesn't matter\b",
        r"\bany level of busy\b",
        r"\bdoesn't matter how busy\b",
    ],
    "length_of_stay": [
        r"\bany length of stay\b",
        r"\bstay length doesn't matter\b",
        r"\bdoesn't matter how long\b",
    ],
    "food_quality": [
        r"\bany food quality\b",
        r"\bfood quality doesn't matter\b",
    ],
    "romantic": [
        r"\bromantic doesn't matter\b",
        r"\bdoesn't need to be romantic\b",
        r"\bnot necessarily romantic\b",
    ],
    "touristic": [
        r"\btouristic doesn't matter\b",
        r"\bdoesn't need to be touristic\b",
    ],
    "children": [
        r"\bchildren doesn't matter\b",
        r"\bdoesn't need to be child[- ]friendly\b",
    ],
    "assigned_seats": [
        r"\bassigned seats don't matter\b",
        r"\bseating doesn't matter\b",
    ],
}

def extract_relaxed_requirements(user_input):
    text = user_input.lower()
    relaxed = []

    for requirement, patterns in RELAX_REQUIREMENT_PATTERNS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            relaxed.append(requirement)

    return relaxed

def satisfies_requirement(
    result, requirement, desired_value, restaurant_data=None
):
    # 1. Existing reasoning-based properties
    inferred_value = result["properties"].get(requirement)

    if inferred_value is not None:
        return inferred_value == desired_value

    # 2. Direct requirements based on restaurant data
    data = restaurant_data or {}

    # Price range
    if requirement == "pricerange":
        actual_value = data.get("pricerange")
        return actual_value == desired_value

    # Location
    if requirement == "area":
        actual_value = data.get("area")
        return actual_value == desired_value

    # Food: pizza and pasta are approximated by Italian cuisine
    # Food: pizza and pasta
    if requirement == "food":
        food = str(data.get("food", "")).lower()
        restaurant_name = str(
            data.get("restaurant", result.get("restaurant", ""))
        ).lower()

        if desired_value == "pizza":
            return (
                food == "italian"
                or "pizza" in restaurant_name
            )

        if desired_value == "pasta":
            return food == "italian"

        return food == desired_value

    # Lively atmosphere
    if requirement == "crowdedness":
        actual_value = data.get("crowdedness")
        return actual_value == desired_value

    # Long dinner or quick meal
    if requirement == "length_of_stay":
        actual_value = data.get("length of stay")
        return actual_value == desired_value

    # Takeaway: check the restaurant name
    if requirement == "takeaway":
        restaurant_name = str(
            data.get("restaurant", result.get("restaurant", ""))
        ).lower()

        actual_value = "takeaway" in restaurant_name
        return actual_value == desired_value

    # Food quality
    if requirement == "food_quality":
        actual_value = data.get("food quality")
        return actual_value == desired_value

    # Existing special cases
    #-----------------------
    # CHANGED: no rule ever concludes children = True (R4 only says long stay -> children = False),
    # so "suitable for children" cannot be proven for any restaurant. It is therefore not accepted.
    # Original lines:
    # if requirement == "children" and desired_value is True:
    #     return True
    if requirement == "children" and desired_value is True:
        return False
    #-----------------------

    if requirement == "assigned_seats" and desired_value is False:
        return True

    return False

def extract_requirements(user_input):
    text = user_input.lower()

    
    requirements = []

    # Existing reasoning-based requirements
    for requirement, patterns in REQUIREMENT_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                prefix = text[:match.start()].strip()

                negated = bool(
                    re.search(
                        r"\b(?:do not|don't|dont)\s+(?:want|need|like)\b",
                        prefix
                    )
                    or re.search(r"\bnot\s*$", prefix)
                    or re.search(r"\bno\s*$", prefix)
                )

                requirements.append((requirement, not negated))

    # Direct requirements based on DataFrame columns
    for requirement, value_patterns in DIRECT_REQUIREMENT_PATTERNS.items():
        for desired_value, patterns in value_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    prefix = text[:match.start()].strip()

                    negated = bool(
                        re.search(
                            r"\b(?:do not|don't|dont)\s+(?:want|need|like)\b",
                            prefix
                        )
                        or re.search(r"\bnot\s*$", prefix)
                        or re.search(r"\bno\s*$", prefix)
                    )

                    # Boolean requirements can be inverted
                    if isinstance(desired_value, bool):
                        value = not desired_value if negated else desired_value

                    # Do not guess the alternative to a negated category
                    else:
                        if negated:
                            continue
                        value = desired_value

                    requirements.append((requirement, value))

    # Remove duplicate requirements while preserving order
    return list(dict.fromkeys(requirements))

# detect requirement contradicitons
def detect_requirement_contradictions(requirements):

    values_by_property = {}
    for requirement, desired_value in requirements:

        values_by_property.setdefault(requirement, set()).add(desired_value)

    contradictions = {}
    for requirement, values in values_by_property.items():
        if len(values) > 1: contradictions[requirement] = values

    return contradictions

def resolve_requirement_contradictions(requirements):

    contradictions = detect_requirement_contradictions(requirements)

    if not contradictions:
        return requirements

    resolved_requirements = requirements.copy()
    for requirement in contradictions:
        # if there exists a contradition, ask the user for its preference
        preference = ask_contradiction_preference(requirement)
        preferred_requirement, preferred_value = preference

        resolved_requirements = [
            (req, value)
            for req, value in resolved_requirements
            if req != requirement
        ]

        resolved_requirements.append((preferred_requirement, preferred_value))

    return resolved_requirements

# multiple requirements that cannot be satisfied at the same time -> ask the user for its preference 
def ask_no_match_preference(requirements):

    print("\nNo restaurant satisfies all of your requirements.")
    print("\nWhich requirement is more important to you?")

    for i, (requirement, desired_value) in enumerate(requirements, start=1):
        if desired_value:
            value_text = "yes"
        else:
            value_text = "no"
        print(
            f"{i} - The restaurant should satisfy "
            f"{requirement} = {value_text}"
        )
    while True:
        choice = input("Your preference: ").strip()
        try:
            choice = int(choice)
        except ValueError:
            print("Please enter a number.")
            continue

        if 1 <= choice <= len(requirements):
            return [requirements[choice - 1]]
        else:
            print(
                f"Please choose a number between 1 and {len(requirements)}."
            )

def detect_contradictions(conclusions):
    contradictions = {}

    for property_name, values in conclusions.items():
        if len(set(values)) > 1:
            contradictions[property_name] = values

    return contradictions

# analyse data
input_file = "data/restaurant_info_extended.csv"
df = pd.read_csv(input_file,delimiter=',')

# for column in df.columns:
#     print(f"\n{column}:")
#     print(df[column].unique())

# R1: pricerange == "cheap" AND food quality == "good" -> touristic = True
# R2: food == "romanian" -> touristic = False
# R3: crowdedness == "busy" -> assigned_seats = True
# R4: length of stay == "long" -> children = False
# R5: crowdedness == "busy" -> romantic = False
# R6: length of stay == "long" -> romantic = True

def apply_rules(restaurant):
    conclusions = {}
    reasons = {}

    def add_conclusion(property_name, value, reason):
        conclusions.setdefault(property_name, []).append(value)
        reasons.setdefault(property_name, []).append(reason)

    # R1
    if (restaurant["pricerange"] == "cheap" and restaurant["food quality"] == "good"):
        add_conclusion("touristic",True,"it is cheap and has good food")

    # R2
    if restaurant["food"] == "romanian":
        add_conclusion("touristic",False,"since it serves romanian food, it is not recommended for tourists")

    # R3
    if restaurant["crowdedness"] == "busy":
        add_conclusion("assigned_seats",True,"it is busy so the waiter decides where you sit")

    # R4
    if restaurant["length of stay"] == "long":
        add_conclusion("children",False,"it allows a long stay which is not advised when taking children")

    # R5
    if restaurant["crowdedness"] == "busy":
        add_conclusion("romantic",False,"it is busy and thus, not romantic")

    # R6
    if restaurant["length of stay"] == "long":
        add_conclusion("romantic",True,"it allows spending a long time in the restaurant which is romantic")

    return conclusions, reasons

# User requriements can lead to contradictions as different rules fire.
# This applies for: romantic = {True, False} and touristic = {True, False}
def ask_contradiction_preference(property_name):

    if property_name == "romantic":
        print(
            "\nThere is conflicting information about the romantic requirement:\n"
            "The restaurant is busy, which is considered not romantic, but it also allows a long stay, which is considered romantic.\n\n"
            "What is more important for you?\n"
            "1 - The restaurant should be busy, which is considered not romantic.\n"
            "2 - The restaurant should allow long stays, which is considered romantic."
        )
        while True:
            choice = input("Your preference: ").strip()
            if choice == "1":
                return ("romantic", False)
            elif choice == "2":
                return ("romantic", True)
            else:
                print("Please choose 1 or 2.")

    elif property_name == "touristic":
        print(
            "\nThere is conflicting information about the touristic requirement."
            "The restaurant is cheap and has good food, which is considered touristic, but it serves Romanian food, which is considered not touristic."
            "What is more important for you?\n"
            "1 - The restaurant should be cheap and have good food, making it suitable for tourists."
            "2 - The restaurant should not serve Romanian food, as this is considered not touristic."
        )
        while True:
            choice = input("Your preference: ").strip()
            if choice == "1":
                return ("touristic", True)
            elif choice == "2":
                return ("touristic", False)
            else:
                print("Please choose 1 or 2.")

def reason_about_restaurant(restaurant):
    conclusions, reasons = apply_rules(restaurant)
    contradictions = detect_contradictions(conclusions)

    all_properties = [
        "touristic",
        "assigned_seats",
        "children",
        "romantic"
    ]
    resolved = {}
    for property_name in all_properties:

        # Contradictory conclusions: unknown until user decides
        if property_name in contradictions:
            resolved[property_name] = None

        # One clear conclusion
        elif property_name in conclusions:
            resolved[property_name] = conclusions[property_name][0]

        # No rule fired, thus unknown
        else:
            resolved[property_name] = None

    return {
        "restaurant": restaurant["restaurantname"],
        "properties": resolved,
        "reasons": reasons,
        "contradictions": contradictions,
        "data": restaurant
    }

def find_relevant_contradiction(state):
    requested_properties = {
        requirement
        for requirement, value in state["requirements"]
        if requirement in ("romantic", "touristic")
    }

    for restaurant in state["matches"]:
        result = (
            restaurant
            if "contradictions" in restaurant
            else reason_about_restaurant(restaurant)
        )

        for property_name in requested_properties:
            if property_name in result.get("contradictions", []):
                return property_name

    return None


def find_matching_restaurants(df, requirements):
    matches = []

    for _, row in df.iterrows():
        restaurant_data = row.to_dict()
        result = reason_about_restaurant(restaurant_data)

        matches_all = True

        for requirement, desired_value in requirements:
            if requirement in result["contradictions"]:
                # Keep restaurants with a contradiction for later clarification
                continue

            if not satisfies_requirement(
                result,
                requirement,
                desired_value,
                restaurant_data
            ):
                matches_all = False
                break

        if matches_all:
            matches.append(result)

    return matches


def explain_requirement(result, requirement, desired_value):
    actual_value = result["properties"].get(requirement)
    data = result["data"]

    # Contradiction
    if requirement in result["contradictions"]:
        reasons = result["reasons"].get(requirement, [])
        return (
            f"{requirement} = None "
            f"(contradiction: {' and '.join(reasons)})"
        )

    # Fulfilled
    if actual_value == desired_value:
        reasons = result["reasons"].get(requirement, [])
        if reasons:
            return (
                f"{requirement} = {actual_value}: "
                f"{' '.join(reasons)}"
            )
        return (
            f"{requirement} = {actual_value}: "
            f"the requirement is fulfilled"
        )

    # Known rule-based value, but requirement not fulfilled
    if actual_value is not None:
        reasons = result["reasons"].get(requirement, [])
        if reasons:
            return (
                f"{requirement} = {actual_value}: "
                f"{' '.join(reasons)}"
            )
        return (
            f"{requirement} = {actual_value}: "
            f"the requirement is not fulfilled"
        )

    # Unknown case: children = True
    if requirement == "children" and desired_value is True:
        if data["length of stay"] == "short":
            return (
                "The stay is short, so there is no rule indicating "
                "that children are unsuitable"
            )

    # Unknown case: assigned_seats = False
    if requirement == "assigned_seats" and desired_value is False:
        if data["crowdedness"] == "not busy":
            return (
                "The restaurant is not busy, so there is no rule "
                "indicating that seats are assigned"
            )

    # Direct information from the DataFrame
    column_mapping = {
        "pricerange": "pricerange",
        "area": "area",
        "food": "food",
        "crowdedness": "crowdedness",
        "length_of_stay": "length of stay",
        "food_quality": "food quality",
    }

    column = column_mapping.get(requirement)

    if column is not None:
        value = data.get(column)

        if value is not None and not pd.isna(value):
            if value == desired_value:
                return (
                    f"{requirement} = {value}: "
                    "the requirement is fulfilled"
                )
            return (
                f"{requirement} = {value}: "
                "the requirement is not fulfilled"
            )

    # Unknown value
    return (
        f"{requirement} = None: "
        "there is no rule-based information"
    )

def remove_requirement(state, requirement):
    """Remove a requirement category from the current preferences."""
    state["requirements"] = [
        (req, value)
        for req, value in state["requirements"]
        if req != requirement
    ]

def update_requirements(existing_requirements, new_requirements):
    updated = existing_requirements.copy()

    for new_requirement, new_value in new_requirements:
        updated = [
            (requirement, value)
            for requirement, value in updated
            if requirement != new_requirement
        ]
        updated.append((new_requirement, new_value))

    return updated

def get_restaurant_name(result):
    return result.get(
        "restaurant",
        result.get("data", {}).get("restaurant", "Unknown restaurant")
    )


def is_no_response(text):
    text = text.lower().strip()
    return bool(re.fullmatch(
        r"(no|no thanks|no thank you|none|nothing else|"
        r"no additional requirements|that's all|that is all)[.! ]*",
        text
    ))


def is_more_response(text):
    text = text.lower().strip()
    return bool(re.search(
        r"\b(more|another one|another restaurant|"
        r"give me more|show me more|anything else)\b",
        text
    ))

def recommend_next_restaurant(state):
    # Restaurants that have not been recommended yet
    remaining = [
        restaurant for restaurant in state["matches"]
        if get_restaurant_name(restaurant).casefold()
        not in {
            name.casefold()
            for name in state["recommended"]
        }
    ]

    if not remaining:
        return (
            "Sorry, I couldn't find any further restaurant "
            "matching your requirements: "
            + ", ".join(
                f"{req}={value}"
                for req, value in state["requirements"]
            )
        )

    restaurant = remaining[0]

    # Keep the original name for tracking
    original_name = get_restaurant_name(restaurant)

    if original_name.casefold() not in {
        name.casefold() for name in state["recommended"]
    }:
        state["recommended"].append(original_name)

    # Format the name only for displaying it
    name = original_name.title()
    name = name.replace(" And ", " and ")

    state["awaiting_additional"] = False

    # Explain why the restaurant matches the user's requirements
    reasons = []

    requirement_phrases = {
        "pricerange": {
            "cheap": "it is cheap",
            "moderate": "it has a moderate price range",
            "expensive": "it is expensive",
        },
        "area": {
            "centre": "it is in the centre",
            "north": "it is in the north",
            "south": "it is in the south",
            "east": "it is in the east",
            "west": "it is in the west",
        },
        "food": {
            "italian": "it serves Italian food",
            "indian": "it serves Indian food",
            "chinese": "it serves Chinese food",
            "british": "it serves British food",
            "french": "it serves French food",
            "thai": "it serves Thai food",
            "japanese": "it serves Japanese food",
            "pizza": "it serves pizza",
            "pasta": "it serves Italian food",
            "seafood": "it serves seafood",
        },
        "assigned_seats": {
            True: "it is busy so the waiter decides where you sit",
            False: "it is not busy, so there is no rule indicating that seats are assigned",
        },
        "romantic": {
            True: "it allows spending a long time in the restaurant which is romantic",
            False: "it is busy and thus, not romantic",
        },
        "touristic": {
            True: "it is cheap and has good food",
            False: "it serves romanian food, it is not recommended for tourists",
        },
        "children": {
            True: "the stay is short, so there is no rule indicating that children are unsuitable",
            False: "it allows a long stay which is not advised when taking children",
        },
    }
    for requirement, desired_value in state["requirements"]:
        explanation = explain_requirement(
            restaurant, requirement, desired_value
        )

        fulfilled = (
            (
                f"{requirement} = {desired_value}" in explanation
                and "not fulfilled" not in explanation
                and "contradiction" not in explanation
                )
            or (
                requirement == "children"
                and desired_value is True
            )
            or (
                requirement == "assigned_seats"
                and desired_value is False
            )
        )  
        
        if fulfilled:
            phrase = requirement_phrases.get(
                requirement, {}
            ).get(desired_value)
        
            if requirement == "assigned_seats" and phrase is None:
                if desired_value is True:
                    phrase = "it offers assigned seating"

        # Add a fallback for food types not explicitly listed
            if requirement == "food" and not phrase:
                phrase = f"it serves {desired_value.title()} food"

            if fulfilled and phrase and phrase not in reasons:
                reasons.append(phrase)

            if requirement == "food" and not phrase:
                phrase = f"it serves {desired_value.title()} food"

    # Build the final response
    if reasons:
        if len(reasons) == 1:
            reason_text = reasons[0]
        elif len(reasons) == 2:
            reason_text = f"{reasons[0]} and {reasons[1]}"
        else:
            reason_text = (
                ", ".join(reasons[:-1])
                + f", and {reasons[-1]}"
            )

        return (
            f"I recommend {name}. It matches your preferences "
            f"because {reason_text}."
        )

    return (
        f"I recommend {name}."
    )


def process_user_input(df, user_input, state):
    text = user_input.lower().strip()

    # 1. Handle the answer to "Do you want an alternative?"
    if state.get("awaiting_alternative"):
        if re.fullmatch(
            r"(yes|y|yes please|sure|of course)[.! ]*", text
        ):
            state["awaiting_alternative"] = False
            return recommend_next_restaurant(state)

        if is_no_response(text):
            state["awaiting_alternative"] = False
            state["finished"] = True
            return "You're welcome! Enjoy your meal."

        # Handle "yes, in the west" or similar
        if re.match(r"^(yes|y|yes please|sure)\b", text):
            user_input = re.sub(
                r"^(yes|y|yes please|sure)\b[,. ]*",
                "",
                user_input,
                count=1,
                flags=re.IGNORECASE
            ).strip()
            text = user_input.lower().strip()

        state["awaiting_alternative"] = False

    # 2. Identify relaxed and new requirements
    relaxed_requirements = extract_relaxed_requirements(user_input)
    new_requirements = extract_requirements(user_input)

    # 3. Remove relaxed requirements
    for requirement in relaxed_requirements:
        state["requirements"] = [
            (req, value)
            for req, value in state["requirements"]
            if req != requirement
        ]

    # 4. Add/update new requirements
    state["requirements"] = update_requirements(
        state["requirements"],
        new_requirements
    )

    # 5. Recalculate matching restaurants
    state["matches"] = find_matching_restaurants(
        df,
        state["requirements"]
    )
    
    contradiction = find_relevant_contradiction(state)

    if contradiction:
        preference = ask_contradiction_preference(contradiction)

        state["requirements"] = update_requirements(
            state["requirements"],
            [preference]
        )

        state["matches"] = find_matching_restaurants(
            df,
            state["requirements"]
        )

        state["recommended"] = []


    # Reset recommendations when requirements change
    if new_requirements or relaxed_requirements:
        state["recommended"] = []

    # 6. Handle requests that only relax requirements
    if relaxed_requirements and not new_requirements:
        if not state["matches"]:
            return (
                "Sorry, I couldn't find any restaurant matching your "
                "remaining requirements: "
                + ", ".join(
                    f"{req}={value}"
                    for req, value in state["requirements"]
                )
            )

        return recommend_next_restaurant(state)

    # 7. User asks for another recommendation
    if is_more_response(text) and state["matches"]:
        return recommend_next_restaurant(state)

    # 8. User declines to add further requirements
    if state["awaiting_additional"] and is_no_response(text):
        return recommend_next_restaurant(state)

    # 9. Handle input with no recognized requirements
    if not new_requirements and not relaxed_requirements:
        if state["awaiting_additional"]:
            return (
                "Do you have any additional requirements? "
                "For example, a preferred area, price range, "
                "or type of food."
            )

        return (
            "I'm sorry, I couldn't identify a requirement "
            "in your request. Could you specify what you "
            "are looking for?"
        )

    # 10. No matching restaurants
    if not state["matches"]:
        return (
            "Sorry, I couldn't find any restaurant matching "
            "all your requirements: "
            + ", ".join(
                f"{req}={value}"
                for req, value in state["requirements"]
            )
        )

    # 11. Exactly one matching restaurant
    if len(state["matches"]) == 1:
        return recommend_next_restaurant(state)

    # 12. Several matches: ask for additional requirements
    state["awaiting_additional"] = True

    return (
        "I found some restaurants matching your preferences. "
        "Do you have any additional requirements?"
    )

#--------------------------------------------------------------------------------------------
# Test

state = {
    "requirements": [],
    "matches": [],
    "recommended": [],
    "awaiting_additional": False,
    "awaiting_alternative": False,
    "finished": False,
}

first_input = True


while True:
    if first_input:
        user_input = input(
            "Hello, welcome to the Cambridge restaurant recommendation system. "
            "How may I help you? "
        )
        first_input = False
    else:
        user_input = input("")

    if user_input.lower().strip() in ["quit", "exit", "bye"]:
        print("Goodbye!")
        break

    response = process_user_input(df, user_input, state)
    print(response)

    if state.get("finished"):
        break

    # After the first recommendation, offer an alternative
    if state["recommended"] and not state.get("awaiting_alternative"):
        remaining = [
            r for r in state["matches"]
            if get_restaurant_name(r) not in state["recommended"]
        ]

        if remaining:
            print("Do you want an alternative?")
            state["awaiting_alternative"] = True
        else:
            break
