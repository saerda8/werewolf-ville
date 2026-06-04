from dataclasses import dataclass, field

@dataclass
class HuntCandidate:
    name: str
    path_length: int
    witness_risk: int
    reachable: bool

    @property
    def score(self) -> int:
        # Lower score is better. Favor short path_length and low witness_risk.
        # witness_risk is scaled up significantly as a deterrent.
        return self.path_length + self.witness_risk * 20


@dataclass
class NightHuntState:
    started_at: float
    deadline_at: float
    stage: str = "choosing"
    target_name: str = ""
    target_changes: list[str] = field(default_factory=list)
    witnessed_by: set[str] = field(default_factory=set)
    killed_name: str = ""
    withdrawal_complete: bool = False
    forced_completion: bool = False


def choose_forced_target(candidates: list[HuntCandidate]) -> HuntCandidate | None:
    # Filter reachable candidates
    reachable = [candidate for candidate in candidates if candidate.reachable]
    if not reachable:
        return None
    # Return the candidate with the lowest score
    return min(reachable, key=lambda candidate: candidate.score)


def build_trace_clues(
    victim_name: str,
    location: str,
    witnesses: list[str],
    forced_completion: bool
) -> list[dict]:
    clues = []

    # 1. Normal kill must produce at least one trace clue
    base_clue = {
        "clue_type": "struggle_mark",
        "summary": f"Signs of a physical struggle and unusual hair fibers were found at the {location} where {victim_name} met their end.",
        "source": "crime_scene",
        "related_person": victim_name,
        "location": location,
    }
    clues.append(base_clue)

    # 2. Each witness increases clues or gives a witness clue (deterministic ordering)
    for witness in sorted(witnesses):
        witness_clue = {
            "clue_type": "witness_statement",
            "summary": f"{witness} observed suspicious movements or heard growls near the {location} during the night.",
            "source": witness,
            "related_person": victim_name,
            "location": location,
        }
        clues.append(witness_clue)

    # 3. Forced completion produces strictly more clues than a clean unwitnessed kill
    if forced_completion:
        forced_clue = {
            "clue_type": "disturbed_trail",
            "summary": f"A heavily disturbed path and deep claw marks indicate a rushed, forced werewolf kill on {victim_name}.",
            "source": "forced_attack",
            "related_person": victim_name,
            "location": location,
        }
        clues.append(forced_clue)

    return clues
