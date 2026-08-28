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


def main() -> None:
    assert gate(GOOD)["ok"], gate(GOOD)
    assert not gate(LEGAL)["ok"]
    assert "out_of_lease" in gate(LEGAL)["errors"]
    assert not gate(THIN)["ok"]
    assert not gate(DECORATIVE)["ok"]
    assert not gate(NO_URL_SCHEME)["ok"]
    print("ok")


if __name__ == "__main__":
    main()
