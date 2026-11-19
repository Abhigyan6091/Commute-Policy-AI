import json
import re
from app.schemas import Principal

TITLES = ['Policy overview','Employee eligibility','Grade requirements','Distance eligibility',
    'Shift eligibility','Pickup and drop arrangements','Night transportation','Security escorts',
    'Weekend transportation','Holiday transportation','Ad-hoc requests','Airport transportation',
    'Guest transportation','Cost restrictions','Booking cut-off timings','Cancellation procedures',
    'No-show penalties','Approval hierarchy','Exceptions','Transport desk and escalation']
COMPANIES = {'COMPANY_A': 'Apex Technologies', 'COMPANY_B': 'Nova Digital', 'COMPANY_C': 'Vertex Systems'}
RULES = {
'COMPANY_A': [
    'This fictional policy covers domestic employee commuting at Apex Technologies. It applies from 1 January 2026 until a newer version is activated. Transport is a scheduled workplace service, not an unrestricted travel allowance.',
    'Only confirmed full-time employees with verified HR records may enroll. Contractors and interns are excluded unless a written exception is approved under section 19. Enrollment does not guarantee a specific vehicle or seat.',
    'Grades A1 through A5 may use shared rostered transport. Grades A4 and A5 may request a dedicated cab only for approved business travel; grade alone never authorizes a personal trip.',
    'The registered residence must be at least 5 km and no more than 35 km from the assigned office by the approved road route. Addresses outside that band require the section 19 exception before booking.',
    'Rostered shifts ending at or after 8 PM or starting before 7 AM qualify for night transport. Day shifts require enrollment in an existing shared route; an unscheduled overtime claim requires manager confirmation.',
    'Shared pickups use designated safe stops. Be at the stop 5 minutes early; vehicles wait at most 3 minutes. Doorstep drops are provided on approved night routes where access is safe and legal.',
    'Eligible employees may request a 9:30 PM drop when their approved shift ends at 9:30 PM. Night trips must originate at the assigned office and end at the registered address; intermediate personal stops are prohibited.',
    'A trained security escort is mandatory for female employees on drops departing after 8 PM and before 6 AM. At exactly 8 PM this rule does not yet apply. The transport desk must arrange the escort before dispatch; employees must not waive it.',
    'Saturday and Sunday cab bookings require prior reporting-manager approval and transport-desk confirmation. Ordinary weekday enrollment does not authorize weekend travel. The approval must identify the work shift and business purpose.',
    'Public-holiday transport requires department-head approval and a published holiday duty roster. The holiday rule takes priority when a holiday falls on a weekend; an ordinary weekend approval alone is insufficient.',
    'Ad-hoc business trips require reporting-manager approval before dispatch. Submit the destination, cost centre, business purpose and timing. Verbal requests do not authorize dispatch; emergencies use section 19.',
    'Airport trips require department-head approval before booking and an approved business itinerary. Only travel between the assigned office or registered home and the approved airport is covered; personal holidays are excluded.',
    'Guests may travel only on approved business visits with a sponsoring employee and prior department-head approval. Family members are not eligible as guests. The sponsor is responsible for accurate contact and destination details.',
    'The maximum approved cab cost is INR 1200 per trip, including tolls and parking. A higher quote requires Finance approval before booking. Splitting a single trip into multiple bookings to evade the limit is prohibited.',
    'Book regular trips by 4 PM on the preceding working day. Airport requests must arrive at least 24 hours before pickup. Late regular requests become ad-hoc requests and require the separate approval in section 11.',
    'Cancel through the portal at least 2 hours before pickup. Later cancellations must be reported immediately to the transport desk and count as a no-show unless the desk records a verified service or medical emergency.',
    'The first no-show in a rolling 30-day period results in a written warning. The second results in a 7-day booking suspension after employee notification. A third requires HR review. A verified operator failure is not an employee no-show.',
    'Reporting managers approve weekend and ad-hoc requests; department heads approve airport, guest and holiday requests. Finance approves cost-limit exceptions. The transport desk checks approvals but cannot substitute its own approval.',
    'Exceptional travel outside eligibility or distance limits requires a written department-head and HR approval with an expiry date. Immediate safety emergencies go to the transport desk first; retrospective records are due the next working day.',
    'Contact transport@apex.example or extension 4101 for bookings and safety coordination. Escalate unresolved booking issues to the duty transport lead, then the HR operations head. In imminent danger use local emergency services first.'
],
'COMPANY_B': [
    'This fictional policy covers domestic employee commuting at Nova Digital. It applies from 1 January 2026 until replaced through controlled activation. Transport supports attendance on approved shifts and is not a cash benefit.',
    'Full-time employees and registered interns with current HR records may enroll. Agency contractors are excluded unless HR grants a time-limited exception. Employees must complete the safety briefing before the first trip.',
    'Grades N1 through N6 are eligible for pooled cabs. A dedicated vehicle is permitted only for approved accessibility needs, irrespective of grade. Seniority does not automatically change the approved travel category.',
    'The registered residence must be at least 3 km and no more than 40 km from the assigned office on the approved road route. HR and Admin must jointly approve addresses outside these limits.',
    'Shifts ending at or after 10 PM or starting before 6 AM qualify for night transport. Other approved shifts may use an available pooled route. The supervisor must enter the shift in the roster before the cutoff.',
    'Employees use designated pickup hubs and should arrive 10 minutes early. Vehicles wait at most 5 minutes. Night drops use the registered doorstep when road access and driver safety allow it; the desk confirms alternatives.',
    'A 9:30 PM shift end does not qualify for the night-transport category. Such employees may use an approved pooled route if one is available. A special late trip requires the ad-hoc authorization in section 11.',
    'A trained security escort is mandatory for female employees on drops departing after 10 PM and before 5 AM. At exactly 10 PM this requirement does not yet apply. The desk assigns the escort and confirms safe completion of each escorted trip.',
    'Saturday and Sunday cab booking is available to eligible employees on rostered work shifts without separate weekend approval. The shift must already appear in the approved duty roster and normal booking cutoffs still apply.',
    'Public-holiday transport is available only for an approved essential-services roster with Admin approval. A weekend roster does not automatically qualify as a holiday roster. The published office holiday calendar determines the category.',
    'Ad-hoc business trips require the project director and Admin to approve the request before dispatch. Provide an itinerary and business cost centre. An available vehicle is not evidence of authorization.',
    'Airport trips require project-director approval and Finance confirmation of the travel budget before booking. They must support a business itinerary. Personal airport transfers and companion tickets are outside this commuting policy.',
    'Guest transportation is not provided under the employee commuting program. Hosts must arrange approved vendor travel through the separate visitor-services process. A guest cannot be added to an employee roster to bypass this restriction.',
    'The maximum approved cab cost is INR 1800 per trip, including tolls and parking. Finance and Admin must jointly approve an over-limit quotation before dispatch. Unapproved excess is not automatically reimbursable.',
    'Book regular trips by 6 PM on the preceding working day. Airport requests require 48 hours notice. Missed cutoffs are handled as ad-hoc requests and may be declined if approvals or capacity are unavailable.',
    'Cancel through the portal at least 1 hour before pickup. Later cancellations normally count as no-shows. Report provider delays or verified medical emergencies to the desk so that the attendance record can be reviewed.',
    'The first two no-shows in a calendar month receive reminders without a charge. From the third no-show, an INR 300 charge applies to each incident after HR review and employee notification. Documented operator failures are excluded.',
    'Project directors approve airport and ad-hoc business purpose. Finance confirms airport budgets and excess costs; Admin controls roster and dispatch approval. Reporting managers cannot independently approve an airport trip.',
    'Distance or eligibility exceptions require joint HR and Admin approval for a stated period. A safety emergency must be reported immediately to the duty desk. A retrospective operational record is required within one working day.',
    'Contact mobility@nova.example or extension 5202 for transport support. Escalate unresolved dispatch issues to the Admin duty manager, then the people-operations director. In imminent danger use local emergency services first.'
],
'COMPANY_C': [
    'This fictional policy covers domestic employee commuting at Vertex Systems. It applies from 1 January 2026 until a replacement is activated. The program is designed for approved shift operations and audited business movements.',
    'Full-time employees and agency contractors specifically listed in the approved shift register may enroll. Interns are excluded without an HR exception. Every traveler must have a validated emergency contact and registered address.',
    'Grades V2 through V7 are eligible for regular shared transport. Grade V1 requires a written HR exception. A higher grade never authorizes a dedicated vehicle or changes the published safety obligations.',
    'The registered residence must be at least 8 km and no more than 30 km from the assigned office on the approved road route. Exceptions require both HR and operations-director approval and a documented end date.',
    'Night transport applies to approved shifts ending at or after 9 PM or starting before 7 AM. Day routes operate only where published. The operations coordinator verifies shift eligibility against the approved duty roster.',
    'Shared pickups use nominated stops with a 5-minute early-arrival requirement and a maximum 2-minute wait. Approved night drops use safe doorstep access. Notify the desk of blocked roads rather than negotiating a new personal destination.',
    'An approved 9:30 PM shift end qualifies for night transport. Employees must book the drop against their approved shift record. Changing the drop to a personal destination requires a separately approved exception.',
    'A trained security escort is mandatory for female employees on drops departing after 9 PM and before 6 AM. At exactly 9 PM this rule does not yet apply. A trip requiring an escort must not depart without one.',
    'Weekend transportation is restricted to shifts approved by the operations director and entered in the weekend roster. Ordinary eligibility alone is insufficient. Unrostered Saturday or Sunday personal travel is not permitted.',
    'Public-holiday transportation requires plant-head approval and a named production-support duty. A general weekend approval is insufficient when a public holiday overlaps a weekend. Admin validates the holiday calendar before dispatch.',
    'Ad-hoc requests require operations-director approval before dispatch and must relate to a documented business need. Provide travel timing, site, route and cost centre. The desk may combine authorized requests where safe.',
    'Airport trips require operations-director approval for business purpose and plant-head approval for the booking. Business flight details must be attached. Personal airport transfers are excluded even if a vehicle is otherwise available.',
    'Guest travel is restricted to approved technical auditors with a named employee sponsor and plant-head authorization. Other visitors must use the separate visitor-services process. Guests are never automatically added to employee shift vehicles.',
    'The maximum approved cab cost is INR 900 per trip, including tolls and parking. The plant head and Finance must approve higher amounts before dispatch. An approved business purpose does not by itself waive the cap.',
    'Book regular trips by 3 PM on the preceding working day. Airport requests require 36 hours notice. Late requests require the ad-hoc approval in section 11 and remain subject to safety and vehicle availability.',
    'Cancel at least 3 hours before pickup using the portal. Later cancellations normally count as no-shows. The desk may exclude documented operator failures or medical emergencies after reviewing the evidence with the shift supervisor.',
    'The first two no-shows in a rolling 60-day period require supervisor counselling. The third triggers HR review and a possible temporary suspension decided after employee response. No automatic cash penalty is specified.',
    'Operations directors approve weekend shifts, ad-hoc trips and airport business purpose. Plant heads approve airport bookings, holiday duty and technical-auditor guest travel. Finance participates in cost exceptions; the desk validates dispatch.',
    'Eligibility and distance exceptions require HR and operations-director approval with an expiry date. Urgent safety incidents go directly to the duty desk. Written emergency justification is due by the next working day.',
    'Contact commute@vertex.example or extension 6303 for support. Escalate unresolved incidents to the shift transport supervisor, then the operations director. In imminent danger use local emergency services first.'
]}

PROCEDURES = [
    'The policy owner is the local HR and administration team. A published replacement is authoritative only after successful activation in the policy system. Employees should use the currently active text rather than screenshots of old answers. The program does not promise availability on routes that have not been published. Route notices provide operational schedules and cannot waive approvals, safety duties or cost limits in this policy.',
    'Submit enrollment through the employee portal using the current employee identifier. HR validates employment status and sends an eligibility confirmation to the desk. Report transfers, changes in employment status and extended leave promptly. A colleague may not lend an enrollment or travel using another employee’s identity. The desk may pause a booking while records are inconsistent and must explain which record needs correction.',
    'HR maintains the authoritative grade register. A grade change takes effect for transport after the updated record is verified; informal promotion announcements are insufficient. Employees requesting an exception must provide the approval reference rather than changing their declared grade. Grade eligibility does not replace shift, distance or cutoff requirements. The desk records any temporary category assignment and its expiry for subsequent audit.',
    'The desk calculates distance using the approved road-route tool and stores the route reference with enrollment. Straight-line map distance and personal estimates are not authoritative. An address change requires a new distance check before the first pickup at the new location. Employees should not disclose colleagues’ addresses in support requests. Changes to a safe stop are coordinated centrally and do not independently alter the approved service radius.',
    'The supervisor must enter a shift change in the scheduling system before the booking deadline. Employees should include their shift reference with any eligibility query. A clock time alone cannot establish personal eligibility without the applicable roster, employment and distance records. The desk resolves discrepancies with the supervisor. Repeated changes made only to obtain transport are reviewed by HR rather than automatically approved by dispatch.',
    'Track the assigned vehicle using the portal when available. If the vehicle or driver differs from the booking, verify the change with the desk before boarding. Do not share live location or driver contact details publicly. Route deviations must be reported to dispatch and recorded with the operational reason. Drivers may decline unsafe stops; the desk must coordinate a safe alternative and communicate it to affected travelers.',
    'Employees must verify the vehicle identifier and driver identity before boarding. A delayed employee should contact dispatch rather than request unsafe driving or informal roadside pickup. The desk tracks completion of night drops and escalates an unconfirmed arrival. Report a route or safety concern immediately. The approved booking record, actual dispatch time and incident reference are retained for review by authorized operations personnel.',
    'The desk verifies escort assignment against the actual departure time and the applicable safety rule. A driver alone is not treated as a separately assigned security escort. If an assigned escort is absent, contact the desk and wait for a safe resolution. Operational delays cannot waive the rule. Report escort conduct concerns through the same incident channel; the duty lead coordinates a safe replacement and records the action.',
    'Weekend requests must identify the date, shift, office and business purpose. Capacity remains subject to route planning and applicable cutoffs. A weekend service does not authorize personal errands, shopping or recreation. Keep the approval or roster reference available for dispatch verification. If work is cancelled, cancel the booking through the normal procedure. A holiday overlapping a weekend follows the separate holiday rule rather than whichever rule appears more convenient.',
    'Admin publishes the office holiday calendar and identifies the duty roster used for dispatch. An employee should confirm the local office calendar when sites observe different holidays. A manager’s general work message is not a substitute for the required holiday authorization. Submit corrections to Admin before the booking deadline. Safety requirements, employee eligibility, cost restrictions and cancellation obligations continue to apply to every approved holiday trip.',
    'Use the portal request form and attach the written approval reference before dispatch. The desk records route feasibility, estimated fare and the requesting cost centre. Approval of a business purpose does not override a fare cap or required security escort. Notify the approver of material itinerary changes. The final booking record must identify the actual traveler and destination rather than a generic team label that prevents accountability.',
    'Provide flight number, terminal, pickup address and scheduled departure or arrival time. The desk allows a practical airport reporting buffer but cannot guarantee airline check-in. Notify dispatch of flight changes as soon as known. Additional waiting charges count toward the applicable cost limit. An airport approval applies only to the submitted itinerary; a changed business itinerary must be reconfirmed by the authorized approver before dispatch.',
    'The sponsoring employee coordinates visitor identity verification through the approved visitor channel. Do not put passport numbers or other sensitive identity documents in ordinary chat questions. The desk checks the authorized travel category before assigning a seat. Where this policy excludes a visitor category, a host must use the separate visitor process rather than relabel the visitor as an employee. Approved passengers remain subject to vehicle safety capacity.',
    'The desk obtains a fare estimate before confirming the booking and records all required financial approval references. Include expected tolls, parking and waiting charges in the estimate. Report an unexpected overrun promptly for review; post-trip review is not a promise of reimbursement. Employees must not pay an unofficial cash supplement to bypass the approved process. Finance reconciles the final vendor invoice against the booking and authorized exceptions.',
    'All cutoff times refer to the assigned office’s local time. A preceding working day excludes days marked closed in the office calendar. Submit early when a long holiday closure affects planning. The portal timestamp is the record of submission, and a draft saved without submission is not a booking. Late requests remain unconfirmed until the required approval and capacity checks are complete; do not assume a vehicle will arrive.',
    'A portal cancellation should produce a confirmation reference. If the portal is unavailable, notify the desk using the published contact and retain the incident reference. Do not rely on a message to a colleague or driver as the only cancellation record. The desk reviews disputed late cancellations using timestamps and the reported circumstances. Cancelled work shifts do not automatically cancel employee-created ad-hoc bookings, so check each reservation.',
    'A no-show means the employee did not board the confirmed service and did not cancel within the permitted window. The desk records dispatch and wait timestamps before assigning the incident. Employees may dispute an incorrect record through the transport desk with available evidence. HR reviews contested penalties and any applicable exception. A driver’s failure to reach the approved pickup location must be investigated rather than treated as an employee absence.',
    'Approvals must be attributable, dated and specific to the trip or valid exception period. The desk records the approval reference and checks that the approver holds the required role. Delegation must be documented by HR or Admin; a copied colleague cannot create approval authority. If multiple approvals are required, obtain all of them before dispatch. Conflicting approvals are escalated to the policy owner, with no assumption that a later informal message supersedes policy.',
    'An exception records the reason, scope, approvers, start date and expiry date. It cannot override an immediate vehicle safety requirement or legal road restriction. The desk checks the exception on each affected booking and removes expired exceptions from operational use. Employees should request renewal before expiry. A previous approved exception for a different traveler, location or month does not establish a continuing entitlement for a new request.',
    'Provide the booking reference, relevant trip time and a concise description when contacting support. Do not send passwords, authentication tokens or unrelated personal documents. The desk acknowledges the incident and routes it to the duty owner; urgent safety reports take priority over routine booking changes. Keep the incident reference for follow-up. Feedback on an assistant answer helps review content but does not amend policy or create a booking approval.'
]

def policy_text(company, updated=False):
    sections = []
    for i, (title, rule, procedure) in enumerate(zip(TITLES, RULES[company], PROCEDURES), 1):
        if updated and company == 'COMPANY_A' and i == 8:
            rule = rule.replace('8 PM', '9 PM')
        sections.append(f'{i}. {title}\n{rule}\n\nOperational procedure: {procedure}')
    pages = ['\n\n'.join(sections[i:i+4]) for i in range(0, 20, 4)]
    return f'FICTIONAL EVALUATION DOCUMENT — {COMPANIES[company]} Transport Policy\nVersion {2 if updated else 1}\n\n' + '\f'.join(pages)

def identity(company, role='employee', user='demo'):
    return Principal(user_id=user, employee_id=user, company_id=company, role=role)

TOPICS = [(8, r'escort|accompany|security'), (17, r'no.show|miss.*cab'), (9, r'weekend|saturday|sunday'),
    (10, r'holiday'), (12, r'airport'), (14, r'cost|maximum|fare'), (15, r'cut.off|deadline|book.*by'),
    (7, r'9:30|night'), (4, r'distance|kilomet|km'), (3, r'grade'), (16, r'cancel'),
    (13, r'guest'), (2, r'intern|eligible|eligibility')]

def _format_conversational_answer(q: str, chosen, evidence) -> str:
    company = chosen.company_id
    c_name = COMPANIES.get(company, company)
    sec = chosen.section_number
    txt = chosen.text

    if sec == '8':
        if 'after 9 PM' in txt:
            cutoff = 'after 9 PM'
            window = 'after 9 PM and before 6 AM'
            threshold_note = 'At exactly 9 PM this rule does not yet apply.'
        elif 'after 10 PM' in txt:
            cutoff = 'after 10 PM'
            window = 'after 10 PM and before 5 AM'
            threshold_note = 'At exactly 10 PM this requirement does not yet apply.'
        else:
            cutoff = 'after 8 PM'
            window = 'after 8 PM and before 6 AM'
            threshold_note = 'At exactly 8 PM this rule does not yet apply.'

        if 'waive' in q:
            return f"No. For {c_name}, the transport desk must arrange the security escort before dispatch; employees must not waive it under any circumstances."
        if 'driver' in q:
            return f"No. According to {c_name} operational procedures, a driver alone is not treated as a separately assigned security escort."
        if 'absent' in q or 'missing' in q:
            return f"If an assigned escort is absent, contact the transport desk immediately and wait for a safe resolution. Operational delays cannot waive the rule."
        if any(h in q for h in ['9:00', '9 pm', '9pm', '9:30']):
            if cutoff == 'after 8 PM':
                return f"Yes. For {c_name}, a trained security escort is mandatory for female employees on drops departing {window}. Since a 9 PM drop departs after 8 PM, the transport desk must arrange the escort before dispatch, and employees must not waive it."
            elif cutoff == 'after 9 PM':
                return f"At exactly 9 PM this rule does not yet apply. For {c_name}, a trained security escort is mandatory for female employees on drops departing {window}."
            else:
                return f"No. For {c_name}, a trained security escort is mandatory for female employees on drops departing {window}. A 9 PM drop departs before the {cutoff} threshold, so an escort is not required."
        if 'accompany' in q:
            return f"Yes. For {c_name}, a trained security escort is mandatory for female employees on drops departing {window}. The transport desk arranges the escort before dispatch."
        return f"A trained security escort is mandatory for female employees on drops departing {window}. {threshold_note} The transport desk must arrange the escort before dispatch; employees must not waive it."

    if sec == '9':
        if company == 'COMPANY_A':
            return f"At {c_name}, Saturday and Sunday cab bookings require prior reporting-manager approval and transport-desk confirmation. Ordinary weekday enrollment does not authorize weekend travel."
        elif company == 'COMPANY_B':
            return f"At {c_name}, Saturday and Sunday cab booking is available to eligible employees on rostered work shifts without separate weekend approval, provided the shift appears in the approved duty roster."
        else:
            return f"At {c_name}, weekend transportation is restricted to shifts approved by the operations director and entered in the weekend roster. Ordinary eligibility alone is insufficient."

    if sec == '12':
        if company == 'COMPANY_A':
            return f"At {c_name}, airport trips require department-head approval before booking and an approved business itinerary."
        elif company == 'COMPANY_B':
            return f"At {c_name}, airport trips require project-director approval and Finance confirmation of the travel budget before booking."
        else:
            return f"At {c_name}, airport trips require operations-director approval for business purpose and plant-head approval for the booking."

    if sec == '17':
        if company == 'COMPANY_A':
            return f"At {c_name}, the first no-show in a rolling 30-day period results in a written warning. The second results in a 7-day booking suspension after employee notification. A third requires HR review."
        elif company == 'COMPANY_B':
            return f"At {c_name}, the first two no-shows in a calendar month receive reminders without a charge. From the third no-show, an INR 300 charge applies to each incident after HR review."
        else:
            return f"At {c_name}, the first two no-shows in a rolling 60-day period require supervisor counselling. The third triggers HR review and a possible temporary suspension. No automatic cash penalty is specified."

    if sec == '14':
        if company == 'COMPANY_A':
            return f"At {c_name}, the maximum approved cab cost is INR 1200 per trip, including tolls and parking. A higher quote requires Finance approval before booking."
        elif company == 'COMPANY_B':
            return f"At {c_name}, the maximum approved cab cost is INR 1800 per trip, including tolls and parking. Finance and Admin must jointly approve an over-limit quotation before dispatch."
        else:
            return f"At {c_name}, the maximum approved cab cost is INR 900 per trip, including tolls and parking. The plant head and Finance must approve higher amounts before dispatch."

    if sec == '15':
        if company == 'COMPANY_A':
            return f"At {c_name}, book regular trips by 4 PM on the preceding working day. Airport requests must arrive at least 24 hours before pickup."
        elif company == 'COMPANY_B':
            return f"At {c_name}, book regular trips by 6 PM on the preceding working day. Airport requests require 48 hours notice."
        else:
            return f"At {c_name}, book regular trips by 3 PM on the preceding working day. Airport requests require 36 hours notice."

    if sec == '10':
        if company == 'COMPANY_A':
            return f"At {c_name}, public-holiday transport requires department-head approval and a published holiday duty roster."
        elif company == 'COMPANY_B':
            return f"At {c_name}, public-holiday transport is available only for an approved essential-services roster with Admin approval."
        else:
            return f"At {c_name}, public-holiday transportation requires plant-head approval and a named production-support duty."

    if sec == '16':
        if company == 'COMPANY_A':
            return f"At {c_name}, cancel through the portal at least 2 hours before pickup. Later cancellations count as a no-show unless the desk records a verified emergency."
        elif company == 'COMPANY_B':
            return f"At {c_name}, cancel through the portal at least 1 hour before pickup. Later cancellations normally count as no-shows."
        else:
            return f"At {c_name}, cancel through the portal at least 3 hours before pickup using the portal. Later cancellations normally count as no-shows."

    if sec == '4':
        if company == 'COMPANY_A':
            return f"At {c_name}, the registered residence must be at least 5 km and no more than 35 km from the assigned office by the approved road route."
        elif company == 'COMPANY_B':
            return f"At {c_name}, the registered residence must be at least 3 km and no more than 40 km from the assigned office on the approved road route."
        else:
            return f"At {c_name}, the registered residence must be at least 8 km and no more than 30 km from the assigned office on the approved road route."

    if sec == '13':
        if company == 'COMPANY_A':
            return f"At {c_name}, guests may travel only on approved business visits with a sponsoring employee and prior department-head approval. Family members are not eligible as guests."
        elif company == 'COMPANY_B':
            return f"At {c_name}, guest transportation is not provided under the employee commuting program. Hosts must arrange visitor travel through separate visitor services."
        else:
            return f"At {c_name}, guest travel is restricted to approved technical auditors with a named employee sponsor and plant-head authorization."

    if sec in ('7', '5'):
        if company == 'COMPANY_A':
            return f"At {c_name}, rostered shifts ending at or after 8 PM or starting before 7 AM qualify for night transport. Eligible employees may request a 9:30 PM drop when their approved shift ends at 9:30 PM."
        elif company == 'COMPANY_B':
            return f"At {c_name}, shifts ending at or after 10 PM or starting before 6 AM qualify for night transport. A 9:30 PM shift end does not qualify for the night-transport category."
        else:
            return f"At {c_name}, night transport applies to approved shifts ending at or after 9 PM or starting before 7 AM. An approved 9:30 PM shift end qualifies for night transport."

    rule = chosen.text.split('\n', 1)[-1].split('\n\nOperational procedure:')[0].strip()
    return f"According to {c_name}'s policy (Section {chosen.section_number} — {chosen.section_title}):\n\n{rule}"

class FakeLLM:
    async def complete(self, question, evidence, budget, correction=False):
        budget.consume()
        q = question.lower()
        status, chosen = 'not_covered', None
        if re.search(r'^(hi|hello|hey|help|who are you|good morning)[!?,. ]*$', q):
            return json.dumps({
                'status': 'not_covered',
                'answer': 'Hello! I am your company transportation policy assistant. You can ask me about shift eligibility, security escorts, weekend cab bookings, cost limits, cancellations, or penalties.',
                'citation_chunk_ids': [],
                'support': [],
                'clarifying_question': None
            })
        if re.search(r'cab tomorrow|am i eligible|can i book a cab[?]?$|my shift', q):
            status = 'needs_clarification'
        elif not re.search(r'bicycle|pet |salary|reveal|ignore|company [abc]|nova|vertex|apex', q):
            section = next((s for s, pattern in TOPICS if re.search(pattern, q)), None)
            chosen = next((c for c in evidence if c.section_number == str(section)), None)
            if not chosen and evidence and not re.search(r'bicycle|pet|salary|foreign', q):
                chosen = evidence[0]
            if chosen:
                status = 'answered'
        quote = chosen.text.split('\n', 1)[-1].split('\n\nOperational procedure:')[0].strip() if chosen else ''
        answer = _format_conversational_answer(q, chosen, evidence) if (status == 'answered' and chosen) else quote
        return json.dumps({
            'status': status,
            'answer': answer,
            'citation_chunk_ids': [chosen.chunk_id] if chosen else [],
            'support': [{'chunk_id': chosen.chunk_id, 'quote': quote}] if chosen else [],
            'clarifying_question': 'Please specify your shift and trip type.' if status == 'needs_clarification' else None
        })
    async def close(self):
        return None
