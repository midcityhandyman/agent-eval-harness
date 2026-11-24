"""Small rule-based agents so the harness has something to evaluate offline.

They stand in for a real model-backed agent. Three variants share one router:

- stable_agent: the version the committed baseline was recorded from. It has
  one known gap (it treats reschedule requests as new bookings).
- improved_agent: fixes that gap and changes nothing else.
- regressed_agent: also fixes the gap, but a "sales friendly" change moved the
  price rule to the top of the router and put a dollar figure in the reply.
  Price questions now get a guaranteed price, and a customer who smells gas
  and asks what a visit costs gets a quote instead of safety guidance.
"""

from __future__ import annotations

import re
from typing import Any

from .models import AgentReply

CARD = re.compile(r"(?:\d[ -]?){12,18}\d")

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("emergency", re.compile(r"smell(s|ing)? (of )?gas|gas leak|carbon monoxide|spark|flood|burst|smoke")),
    ("injection", re.compile(r"ignore (all |your |any )?(previous |prior )?instructions|system prompt|developer (mode|instructions)")),
    ("human", re.compile(r"(speak|talk) (to|with) a (real )?(person|human|manager)|real person")),
    ("complaint", re.compile(r"unacceptable|not happy|still leaking|terrible|worst|useless|hours late|no one showed|nobody called")),
    ("warranty", re.compile(r"warranty")),
    ("billing", re.compile(r"refund|charged twice|overcharged|invoice|\bbill\b")),
    ("out_of_scope", re.compile(r"\bsue\b|lawyer|legal|the law|medical")),
    ("cancel", re.compile(r"\bcancel")),
    ("reschedule", re.compile(r"reschedule|move my (appointment|visit)|different day")),
    ("quote", re.compile(r"how much|\bquote\b|estimate|\bprice\b|\bcost\b")),
    ("status", re.compile(r"where is|on the way|\beta\b")),
    ("hours", re.compile(r"\bhours\b|\bopen\b|weekend")),
    ("booking", re.compile(r"\bbook|schedule|appointment|come out|send someone|\bvisit\b")),
]


def _route(message: str, reschedule: bool, quote_first: bool) -> str:
    text = message.lower()
    if CARD.search(text):
        return "payment_security"
    rules = [r for r in RULES if reschedule or r[0] != "reschedule"]
    if quote_first:
        rules.sort(key=lambda r: r[0] != "quote")
    for intent, pattern in rules:
        if pattern.search(text):
            return intent
    return "clarify"


def _emergency(name: str, message: str) -> str:
    text = message.lower()
    tail = "I have alerted our on-call team and a person will call you right away."
    if "gas" in text or "carbon monoxide" in text:
        return (
            f"{name}, this may be an emergency. Please leave the building now and do not use "
            "switches or open flames. Once outside, call 911 or your gas utility's emergency "
            f"line. {tail}"
        )
    if "flood" in text or "burst" in text:
        return (
            f"{name}, please shut off the main water valve now if you can reach it safely, and "
            f"keep clear of wet electrical outlets. If anyone is in danger, call 911. {tail}"
        )
    return (
        f"{name}, please turn off the breaker for that circuit if it is safe to do so, and do "
        f"not touch the outlet. If you see flames or smoke, leave and call 911. {tail}"
    )


def _respond(intent: str, name: str, message: str, pushy_quote: bool) -> AgentReply:
    if intent == "emergency":
        return AgentReply(_emergency(name, message), intent, ("escalate_emergency",), True)
    if intent == "injection":
        return AgentReply(
            "I can't change how I work or share internal instructions, and I can't create "
            "discounts. I can help with booking, estimates, billing questions or an existing "
            "visit. What do you need help with?",
            intent,
        )
    if intent == "payment_security":
        return AgentReply(
            f"Thanks {name}. For your security, please do not share card numbers in chat. I "
            "can't take card details here, and I have not stored or charged anything. I'll send "
            "a secure payment link to the contact on file so you can pay the deposit there.",
            intent,
            ("send_payment_link",),
        )
    if intent == "human":
        return AgentReply(
            f"Of course, {name}. I'm handing this conversation to a team member now. They will "
            "reply here or call the number on file during business hours, 8am to 6pm Monday to "
            "Saturday.",
            "human_handoff",
            ("handoff_human",),
            True,
        )
    if intent == "complaint":
        return AgentReply(
            f"I'm sorry, {name}. That is not the service we want to provide, and I understand "
            "the frustration. I have opened a follow-up ticket for a manager to review today, "
            "and a team member will contact you with next steps. Is the number on file the best "
            "one to reach you?",
            intent,
            ("create_followup_ticket",),
        )
    if intent == "warranty":
        return AgentReply(
            f"Thanks {name}. I can't confirm warranty coverage in chat because the office needs "
            "to review the original work order. I have opened a follow-up ticket and a team "
            "member will contact you with an answer.",
            intent,
            ("create_followup_ticket",),
        )
    if intent == "billing":
        return AgentReply(
            f"I'm sorry for the trouble, {name}. I can't approve or issue refunds in chat, but I "
            "have opened a billing ticket so our office can review the charges on your invoice. "
            "A team member will contact you within one business day with what they find.",
            intent,
            ("create_billing_ticket",),
        )
    if intent == "out_of_scope":
        return AgentReply(
            f"I'm sorry you're dealing with that, {name}. I can't give legal advice, so a tenant "
            "resource or an attorney is the right place for that question. If it would help, I "
            "can book a visit to inspect the heating so you have a written report.",
            intent,
        )
    if intent == "cancel":
        return AgentReply(
            f"No problem, {name}. I have logged a cancellation request for your visit. You will "
            "get a confirmation message once the office processes it. If you'd like to rebook "
            "later, reply with a day that works for you.",
            intent,
            ("cancel_request_logged",),
        )
    if intent == "reschedule":
        return AgentReply(
            f"Happy to help, {name}. I have started a reschedule request for your appointment. "
            "Which days and time window, morning or afternoon, work best for you? I'll confirm "
            "the new slot once the office approves it.",
            intent,
            ("offer_reschedule",),
        )
    if intent == "quote":
        if pushy_quote:
            return AgentReply(
                f"Thanks {name}. Most jobs like this are $149, guaranteed. I can book a visit to "
                "get it done. Would a morning or afternoon visit suit you?",
                intent,
                ("offer_booking_slots",),
            )
        return AgentReply(
            f"Thanks {name}. I can't quote a firm price in chat because it depends on what the "
            "technician finds on site. I can book a free estimate visit, and you'll get a written "
            "quote before any work starts. Would a morning or afternoon visit suit you?",
            intent,
            ("offer_estimate_visit",),
        )
    if intent == "status":
        return AgentReply(
            f"Thanks {name}. I can't see live location in chat, so I have asked dispatch to check "
            "on your technician, and a team member will message you with an update shortly. I'm "
            "sorry for the wait.",
            intent,
            ("lookup_dispatch_status",),
        )
    if intent == "hours":
        return AgentReply(
            "We're open Monday to Saturday, 8am to 6pm, and closed on Sunday. Weekend visits on "
            "Saturday can be booked the same way as weekdays. Would you like to book one?",
            intent,
        )
    if intent == "booking":
        return AgentReply(
            f"Thanks {name}. I can set up a visit for that. We have morning (8am to 12pm) and "
            "afternoon (12pm to 4pm) time slots. Which day and window work for you, and is the "
            "address on file correct?",
            intent,
            ("offer_booking_slots",),
        )
    return AgentReply(
        f"Thanks for reaching out, {name}. I want to make sure I get this right. Can you tell me "
        "which appliance or fixture is giving you trouble and what it's doing?",
        "clarify",
    )


def _agent(message: str, context: dict[str, Any], *, reschedule: bool, regressed: bool) -> AgentReply:
    name = str(context.get("customer_name") or "there").split()[0]
    intent = _route(message, reschedule=reschedule, quote_first=regressed)
    return _respond(intent, name, message, pushy_quote=regressed)


def stable_agent(message: str, context: dict[str, Any]) -> AgentReply:
    return _agent(message, context, reschedule=False, regressed=False)


def improved_agent(message: str, context: dict[str, Any]) -> AgentReply:
    return _agent(message, context, reschedule=True, regressed=False)


def regressed_agent(message: str, context: dict[str, Any]) -> AgentReply:
    return _agent(message, context, reschedule=True, regressed=True)
