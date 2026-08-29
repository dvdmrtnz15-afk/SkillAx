#!/usr/bin/env python3
from gate import gate

GOOD = {
    "title": "HubSpot schema unblock for voice-lead research",
    "idea": "Research delivered 10 net-new accounts at about $145k EACV. CRM sync is blocked until 24 Company and 8 Contact research properties exist. A sheet already holds the rows.",
    "next_action": "Provision the missing HubSpot properties on an authorized schema path, then rerun reconciliation.",
    "why_it_matters": "Named decision-makers stay stranded in a sheet until the schema exists.",
    "residual": "Schema path authority still needed.",
    "source_type": "gmail",
    "source_url": "https://mail.google.com/",
    "plane": "grok",
    "impact": 9,
}

LEGAL = {
    **GOOD,
    "title": "Approve parenting-time schedule",
    "idea": "Counsel asked whether to send a parenting-time progression to opposing counsel before the hearing.",
    "next_action": "Reply yes or no on the Gmail thread.",
    "why_it_matters": "Unblocks counsel before a court date.",
    "residual": "Start date still open.",
}

THIN = {**GOOD, "idea": "CRM blocked."}
DECORATIVE = {**GOOD, "why_it_matters": "might be useful"}
NO_URL_SCHEME = {**GOOD, "source_url": "not-a-url"}
NO_DELTA = {
    **GOOD,
    "title": "Hourly organism cycle",
    "idea": "Circadian receipt shows no world delta and no new sha. Organism still frozen. Hourly self-prompt fired again.",
    "next_action": "Keep going on federation architecture.",
    "why_it_matters": "Compute is burning with no state change.",
    "residual": "Cron still live.",
}
AMPLIFIED = {
    **GOOD,
    "idea": "We shipped the HubSpot schema and the buyer is Acme. Deadline is Friday and this is done.",
}
HEDGED = {
    **GOOD,
    "idea": "Source said we might have shipped a draft schema. Buyer is unnamed. Deadline is not in the thread.",
}
GESTURE = {**GOOD, "next_action": "keep going"}
HIGH_IMPACT_NO_NEXT = {**GOOD, "next_action": "", "impact": 9}
HIGH_IMPACT_LEGAL = {**LEGAL, "next_action": "", "impact": 10}


def main() -> None:
    assert gate(GOOD)["ok"], gate(GOOD)
    assert not gate(LEGAL)["ok"]
    assert "out_of_lease" in gate(LEGAL)["errors"]
    assert not gate(THIN)["ok"]
    assert not gate(DECORATIVE)["ok"]
    assert not gate(NO_URL_SCHEME)["ok"]
    nd = gate(NO_DELTA)
    assert not nd["ok"], nd
    assert "no-evidence pass" in nd["errors"]
    amp = gate(AMPLIFIED)
    assert not amp["ok"], amp
    assert "amplification in idea" in amp["errors"]
    assert gate(HEDGED)["ok"], gate(HEDGED)
    assert not gate(GESTURE)["ok"]
    hi = gate(HIGH_IMPACT_NO_NEXT)
    assert hi["ok"], hi
    assert "incomplete but high-impact exception" in hi["warnings"]
    assert not gate(HIGH_IMPACT_LEGAL)["ok"]
    print("ok")


if __name__ == "__main__":
    main()
