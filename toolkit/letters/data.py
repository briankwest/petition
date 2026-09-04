"""The sixteen records-request letters: recipients, mailing addresses, items and the clauses they share.

Public officials' published contacts only. The sender (name, address, phone, signature) lives in
config/sender.local.yaml, which git ignores, so this file can be public while the letters are not.
Rendering and the DocuPost CSV are in toolkit.letters.build."""
from __future__ import annotations

NAMES = ("Emerald ProjectCo Inc.; “Project Emerald”, “Emerald” or “EmeraldCo”; the Emerald ProjectCo Data Center Project; "
         "IREN, IREN Limited, Iris Energy, IE US Holdings Inc. or any affiliate; Jason Date, Evan Horn, Marat Ahmad, Lindsay Ward, Michel Skura, "
         "Jonathan Gray, Gerald Byrd, David Shaw or Giles Walsh; Black Mountain Energy Storage or Caroline O’Brien; Tipton Capital, Mitch Stevenson, "
         "Ernst & Young or ISB Group (John Dorff), in connection with the project; Floyd & Driver PLLC or David Floyd, in connection with the project; "
         "Public Service Company of Oklahoma or Jonathan Wynn, in connection with the project; the PCDC Tax Incentive District Review Committee under any name; "
         "or, in connection with a data center, “TID”, “TIF”, “incentive district”, “tax increment”, “abatement”, “data center” or “data centre”")
COMMS = ("<b>Communications.</b> All emails, text and app messages, letters, memoranda, meeting notes, calendar entries and voicemail transcriptions "
         "sent or received by {who} that refer to any of: " + NAMES + ".")
PERIOD = ("<b>Period.</b> {start} to the date you process this request. For items that name a specific company or person, please apply no start date: "
          "those names did not appear in your records before then, so a floor adds nothing but the risk of a miss.")
FORMAT = ("<b>Format.</b> Electronic, in native format with attachments and metadata intact (for example .eml or .msg, .docx, .xlsx), or searchable PDF "
          "where no native file exists. Please produce on a rolling basis as records are located rather than holding everything for one release.")
FEES = ("<b>Fees.</b> This request is not for a commercial purpose. It is made by a county resident and taxpayer to determine whether those entrusted with "
        "public affairs are performing their duties, the purpose for which 51 O.S. § 24A.5 forbids a search fee. I will pay copying at the statutory "
        "rate. If you expect the cost to exceed $50, please send an estimate before incurring it and I will narrow the request or inspect the records in "
        "person, which the Act allows at no charge.")
WITHHOLD = ("<b>Withholding.</b> If any record or part of one is withheld, please identify it (date, author, recipient, subject) and cite the specific "
            "statutory exemption, and release every reasonably segregable portion as § 24A.5 requires. Messages about public business on personal "
            "accounts or devices are records under 2009 OK AG 12. A record does not become confidential because it was placed in a litigation or "
            "investigation file (§ 24A.20).{extra}")
RESPONSE = ("<b>Response.</b> Please acknowledge receipt and tell me when I can expect the first production; the Act requires prompt, reasonable access "
            "(§ 24A.5). I am glad to talk through scope by phone if it will speed things up.")
OPEN = ("Under the Oklahoma Open Records Act, 51 O.S. § 24A.1 et seq., I request to inspect and obtain copies of the following records of {body}, "
        "including records held by its {holders}, regardless of medium and regardless of the account or device on which they were created, sent or received.")

L = []
def letter(n, title, to, cc, re_, body, holders, items, start="1 January 2025", extra_withhold="", opening=None, closing=None, note=None, federal=False):
    L.append(dict(n=n, title=title, to=to, cc=cc, re=re_, body=body, holders=holders, items=items, start=start,
                  extra=extra_withhold, opening=opening, closing=closing, note=note, federal=federal))

letter(1, "Board of County Commissioners and the PCDC TID Review Committee",
  ["Hope Trammell, County Clerk, custodian of records for the Board of County Commissioners of Pittsburg County and for the PCDC Tax Incentive District Review Committee",
   "PO Box 3304 / 115 E. Carl Albert Parkway, McAlester, OK 74501 · countyclerk@pittsburgcountyok.gov · 918-423-6865"],
  ["Board of County Commissioners office, Room 100, bocc@pittsburgcountyok.gov · Commissioner Mike Haynes, district2@pittsburgcountyok.gov · Commissioners Charlie Rogers and Ross Selman via bocc@pittsburgcountyok.gov"],
  "Open Records Act request — Emerald ProjectCo Inc. / IREN data center project south of Kiowa; the Board, its members and the review committee",
  "the Board of County Commissioners of Pittsburg County and of the PCDC Tax Incentive District Review Committee",
  "officers, the three commissioners individually, the Commissioners’ office staff, the committee and its members acting as members, attorneys and other representatives",
  [COMMS.format(who="the Board, any commissioner, the Commissioners’ office, the committee, any committee member in that capacity, or the county’s counsel"),
   "<b>Drafts.</b> Every draft and version of the Project Plan, the Economic Development Agreement and the Tax Incentive Agreement, including the draft plan and draft agreement reviewed on 2 March 2026 and the plan dated 28 April 2026, with transmittal messages, comments and redlines.",
   "<b>The developer’s submissions.</b> Counsel’s written information request to the developer referred to on 17 December 2025; the questions and responses presented on 3 February 2026; the financial update presented on 2 March 2026; the phase 1 and phase 2 maps and legal descriptions; every projection, water or power statement, and other document the developer or its advisers (Tipton Capital, Ernst & Young, ISB Group) submitted; and the “new cost estimates” the Board referred to when it tabled the districts on 22 June 2026.",
   "<b>Counsel.</b> The engagement letter, fee agreement, invoices, timesheets and payment records for Floyd & Driver PLLC in connection with the project, and any agreement, invoice, receipt or correspondence under which IREN, Emerald ProjectCo Inc. or any affiliate pays or reimburses any cost of the county or the committee, including the $40,000 reimbursement reported in May 2026.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, and any request for confidentiality, involving the county, any commissioner, any employee or any committee member and any party named in item 1.",
   "<b>The Childress visit.</b> Invitations, itineraries, travel and expense records, reimbursements, notes, photographs and correspondence for the visit by committee members to IREN’s Childress, Texas facility described on 21 April 2026, including who arranged and who paid for it.",
   "<b>The committee’s formation.</b> Resolutions 26-121 (original and amended) and 26-138 with their backup; any document that created, convened or named the committee; the “list of 7 recommended names” referred to on 8 December 2025; and any communication explaining why, as the minutes of 17 November 2025 record, “the names are needed by December 1st,” and by whom.",
   "<b>Meeting records.</b> Minutes, audio or video recordings, sign-in sheets, handouts, slides and presentations for every committee meeting, including the meeting noticed for 27 January 2026 for which no minutes are posted, and for the public hearings of 8 and 22 June 2026, together with every written comment the Board or committee received.",
   "<b>State and utility contacts.</b> Communications with the Oklahoma Department of Commerce, the Corporation Commission, the Water Resources Board, the Department of Environmental Quality, the Department of Transportation, the Governor’s office, any legislator, McAlester Army Ammunition Plant, or Public Service Company of Oklahoma concerning the project.",
   "<b>Water.</b> Communications with the City of Kiowa, the Kiowa Public Works Authority, Rural Water District No. 11, the City of McAlester, the McAlester Public Works Authority or the Pittsburg County Water Authority concerning water for the project."],
  extra_withhold=" Records of the review committee are records of a public body under § 24A.3, and the County Clerk certified its final minutes as its Secretary. No executive session on this subject appears on any 2025 or 2026 agenda, so § 24A.5(1)(b) does not reach these records.")

letter(2, "City of McAlester and the McAlester Public Works Authority",
  ["Cora Middleton, City Clerk, City of McAlester and McAlester Public Works Authority",
   "28 E. Washington Avenue, PO Box 578, McAlester, OK 74502 · cora.middleton@cityofmcalester.com · 918-423-9300 ext. 4956 (also filed through the city’s online Request for Public Records)"],
  [],
  "Open Records Act request — raw water for the proposed IREN data center south of Kiowa; Black Mountain Energy Storage",
  "the City of McAlester and the McAlester Public Works Authority",
  "officers, council members and trustees individually, the City Manager and Assistant City Manager, the city attorney, public works and utility staff, and other representatives",
  ["<b>The request.</b> The letter of 30 July 2025 from Black Mountain Energy Storage to the Assistant City Manager proposing to purchase approximately six million gallons a day of raw water to cool the proposed IREN data center, with every attachment, and any earlier or later letter, email or proposal from that company.",
   "<b>The 12 August 2025 action.</b> The agenda packet, staff memorandum, presentation and audio or video recording for the council’s authorization to negotiate a raw water purchase agreement with Black Mountain Energy Storage, and any council or trust action on the subject before or after that date.",
   "<b>The agreement.</b> Every draft and version of the raw water purchase agreement, including the version at $1 per 1,000 gallons on the agenda of 10 February 2026, with redlines, transmittals, term sheets and the recording of that meeting.",
   COMMS.format(who="the City, the Authority, the Mayor, any council member or trustee, the City Manager, the Assistant City Manager, the city attorney or utility staff") + " Include in particular communications with Caroline O’Brien or anyone at Black Mountain Energy Storage, and with Pittsburg County or Floyd & Driver about the project.",
   "<b>Analyses.</b> Any water-availability, yield, engineering, rate, revenue or capacity analysis prepared or received in connection with the proposed sale, including anything on the effect of a six-million-gallon-a-day withdrawal on the city’s supply.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the City or the Authority and any party named in item 4.",
   "<b>Since February.</b> Any contact from Black Mountain Energy Storage, IREN or their representatives after 10 February 2026, when the council said the negotiating table remained open."])

letter(3, "Kiowa Public Schools",
  ["Sam Rhyne, Superintendent and custodian of records, Kiowa Public Schools (Independent School District I-014)",
   "PO Box 6 / 406 E. 8th Street, Kiowa, OK 74553 · srhyne@kiowa.k12.ok.us · 918-432-5641 ext. 222"],
  ["The clerk of the Board of Education, whom I ask you to copy"],
  "Open Records Act request — the Emerald ProjectCo Data Center Project Plan and Tax Incentive Agreement; the district’s seat on the review committee",
  "Kiowa Public Schools and its Board of Education",
  "superintendent, board members individually, the board clerk, administrators, attorneys and other representatives",
  [COMMS.format(who="the superintendent, any board member, the board clerk or any district employee"),
   "<b>The committee seat.</b> All records created or received by the superintendent as the district’s representative on the PCDC Tax Incentive District Review Committee: agendas, packets, drafts, projections, counsel’s questions and the developer’s responses, and his notes or summaries.",
   "<b>The Childress visit.</b> Invitations, itineraries, travel and expense records, reimbursements, notes, photographs and correspondence for the visit by committee members to IREN’s Childress, Texas facility, including who arranged it and who paid.",
   "<b>Board records.</b> Every agenda, agenda packet, minute entry, recording and executive-session notice of the Board of Education that mentions the project, the incentive districts, the Tax Incentive Agreement, community betterment payments, or the projected revenue to the district.",
   "<b>What the district was given.</b> Every document the developer, its advisers or the county’s counsel provided to the district, including revenue projections such as the figure of about $11 million in the first year reported in May 2026, and any Tax Incentive Agreement draft sent for the district’s 60- or 90-day review.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the district, the superintendent or any board member and any party named in item 1."],
  extra_withhold=" The district’s decision is the one taxing-entity decision the plan cannot proceed without, which is why its file matters to the public.")

letter(4, "Town of Kiowa and the Kiowa Public Works Authority",
  ["Kristina Burgett, Town Clerk, Town of Kiowa, and Leea Shows, Clerk, Kiowa Public Works Authority",
   "PO Box 69 / 831 S. Van Buren Street, Kiowa, OK 74553 · leea@kiowaoklahoma.com · jeri@kiowaoklahoma.com (Jeriann Hasty, office manager) · 918-432-5621"],
  [],
  "Open Records Act request — water for the proposed IREN data center south of Kiowa",
  "the Town of Kiowa and the Kiowa Public Works Authority",
  "trustees and council members individually, the Mayor, the Town Clerk, the PWA Clerk, the town administrator, operators, engineers, attorneys and other representatives",
  [COMMS.format(who="the Town, the Authority, the Mayor, any trustee or council member, the clerks or any employee"),
   "<b>What the town told the developer.</b> Every will-serve, capacity, availability or comfort letter, email or statement given to IREN, Emerald ProjectCo, their advisers, Pittsburg County or Floyd & Driver about supplying water to the project. On 21 April 2026 the developer told the county’s committee it had “spoken to the City of Kiowa” and that the town “can supply the water for the ongoing operations if required”; I am asking for the paper behind that statement.",
   "<b>Rural Water District No. 11.</b> The town’s water sale contract with Rural Water District No. 11, the volume cap referred to at the committee’s meeting of 3 February 2026, and any analysis of the town’s ability to serve the district and the project at once.",
   "<b>Capacity.</b> Any engineering, yield, source, treatment-capacity, storage or water-loss study or estimate prepared or received in connection with the project, and the town’s current permitted source and treatment capacity figures.",
   "<b>Meeting records.</b> Every agenda, packet, minute entry and recording of the Town Board or the Authority that mentions the project.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the Town, the Authority or any official and any party named in item 1."])

letter(5, "Pittsburg County Rural Water District No. 11",
  ["Candice Crutchfield, Chairperson, Pittsburg County Rural Water District No. 11 (public water system OK3006105)",
   "515 E. Cherokee, McAlester, OK 74501 · t-m-c@att.net · 918-429-1440"],
  ["Vivian Moody, Manager"],
  "Open Records Act request — the proposed IREN data center south of Kiowa and the district’s supply",
  "Pittsburg County Rural Water District No. 11",
  "board members individually, the manager, the operator, engineers, attorneys and other representatives",
  [COMMS.format(who="the district, any board member, the manager or the operator"),
   "<b>Requests to serve.</b> Any inquiry, request, application or proposal from IREN, Emerald ProjectCo, Black Mountain Energy Storage, their advisers, Pittsburg County or Floyd & Driver about supplying water to or across the project site, and the district’s response.",
   "<b>The Kiowa supply.</b> The district’s water purchase contract with the Town of Kiowa, the volume cap referred to at the county committee’s meeting of 3 February 2026, and any analysis of the district’s capacity, connections, and ability to serve existing customers if the project draws on the same source.",
   "<b>The 21 April 2026 item.</b> Board agendas, minutes, recordings and correspondence about the committee’s invitation to discuss “water supply for Project EmeraldCo,” and the decision, recorded in the committee’s minutes, not to appoint a representative to speak.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the district or any board member and any party named in item 1."],
  note="A rural water district organised under Title 82 is a public body under § 24A.3. Personal notes a board member took as a resident attending the county’s meetings are not district records; anything sent or received in the district’s name is.")

letter(6, "Pittsburg County Economic Development Authority and Pittsburg County Water Authority",
  ["Hope Trammell, County Clerk, custodian of records for the Pittsburg County Economic Development Authority and the Pittsburg County Water Authority",
   "PO Box 3304 / 115 E. Carl Albert Parkway, McAlester, OK 74501 · countyclerk@pittsburgcountyok.gov"],
  ["Levenia Carey, Office Manager, Pittsburg County Water Authority, 5911 E. Adamson Road, McAlester, OK 74501"],
  "Open Records Act request — the proposed IREN data center south of Kiowa; the two county trusts",
  "the Pittsburg County Economic Development Authority and the Pittsburg County Water Authority",
  "trustees individually, officers, managers, engineers, attorneys and other representatives",
  [COMMS.format(who="either trust, any trustee, or any officer, manager or employee of either"),
   "<b>Economic Development Authority.</b> Any prospect, site-selection, incentive or inducement file, under any code name, concerning a data center in Pittsburg County or the parties named in item 1, from 1 January 2024; any resolution, letter of support, application or referral; and any contact from the Oklahoma Department of Commerce or a site-selection consultant about the project.",
   "<b>Water Authority.</b> Any inquiry, request or proposal about raw or treated water, capacity, a new connection or a sale for the project from IREN, Emerald ProjectCo, Black Mountain Energy Storage, Tipton Capital, Pittsburg County or Floyd & Driver, and the Authority’s response; and any change of scope, timing or funding in the ARPA water system improvement projects that refers to the project.",
   "<b>Meeting records.</b> Every agenda, packet, minute entry and recording of either trust that mentions the project."],
  start="1 January 2024")

letter(7, "Kiamichi Technology Center",
  ["Shelley Free, Superintendent and custodian of records, Kiamichi Technology Centers",
   "1004 Highway 2 North, Wilburton, OK 74578 · sdfree@ktc.edu · 918-465-2323"],
  ["The clerk of the Board of Education, whom I ask you to copy"],
  "Open Records Act request — the Emerald ProjectCo Data Center Project Plan and Tax Incentive Agreement; the technology center’s seat on the review committee",
  "Kiamichi Technology Centers and its Board of Education",
  "superintendent, board members individually, the board clerk, administrators, attorneys and other representatives",
  [COMMS.format(who="the superintendent, any board member, the board clerk or any employee"),
   "<b>The committee seat.</b> All records created or received by the superintendent as the technology center’s representative on the PCDC Tax Incentive District Review Committee: agendas, packets, drafts, projections, counsel’s questions and the developer’s responses, and her notes or summaries.",
   "<b>Board records.</b> Every agenda, packet, minute entry, recording and executive-session notice of the Board that mentions the project, the incentive districts, the Tax Incentive Agreement or the projected revenue to the district, reported in May 2026 as about $3.4 million a year.",
   "<b>What the district was given.</b> Every document the developer, its advisers or the county’s counsel provided to the technology center, and any Tax Incentive Agreement draft sent for its review.",
   "<b>Workforce.</b> Any communication with IREN or its advisers about training, workforce development or customised programs for the project.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the technology center, the superintendent or any board member and any party named in item 1."],
  extra_withhold=" Section 24A.10(C) lets a technology center district keep confidential business plans, feasibility studies, financing proposals, marketing plans, financial statements or trade secrets submitted by a person “seeking economic advice, business development or customized training” from the district. Material the developer gave the county’s review committee, on which the superintendent sat, was not submitted to the district for that purpose, and the exemption is permissive, not mandatory. If you rely on it, please identify each document withheld and release the rest.")

letter(8, "Southeastern Oklahoma Public Library System",
  ["Michael Hull, Executive Director and custodian of records, Southeast Oklahoma Library System",
   "2820 N. Main Street, McAlester, OK 74501 · michael.hull@seolibraries.com · 918-426-0456"],
  ["The secretary of the Board of Trustees, whom I ask you to copy"],
  "Open Records Act request — the Emerald ProjectCo Data Center Project Plan and Tax Incentive Agreement; the library system’s seat on the review committee",
  "the Southeast Oklahoma Library System and its Board of Trustees",
  "executive director, trustees individually, the board secretary, administrators, attorneys and other representatives",
  [COMMS.format(who="the executive director, any trustee, the board secretary or any employee"),
   "<b>The committee seat.</b> All records created or received by the executive director as the library system’s representative on the PCDC Tax Incentive District Review Committee: agendas, packets, drafts, projections, counsel’s questions and the developer’s responses, and his notes or summaries, including any notes on the motion to recommend the plan that he made on 7 April 2026.",
   "<b>Board records.</b> Every agenda, packet, minute entry, recording and executive-session notice of the Board of Trustees that mentions the project, the incentive districts, the Tax Incentive Agreement or the projected revenue to the system, reported in May 2026 as about $1 million a year.",
   "<b>What the system was given.</b> Every document the developer, its advisers or the county’s counsel provided to the library system, and any Tax Incentive Agreement draft sent for its review.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the system, the executive director or any trustee and any party named in item 1."])

letter(9, "Pittsburg County Health Department, through the Oklahoma State Department of Health",
  ["Open Records, Oklahoma State Department of Health (on the Department’s Open Records Request Form)",
   "123 Robert S. Kerr Avenue, Suite 1702, Oklahoma City, OK 73102-6406 · OSDHOpenRecords@health.ok.gov"],
  ["Juli Montgomery, Regional Administrative Director, Pittsburg County Health Department, 1400 E. College Avenue, McAlester, OK 74501 · 918-423-1267"],
  "Open Records Act request — the Emerald ProjectCo Data Center Project Plan; the Pittsburg County Health Department’s seat on the county’s review committee",
  "the Oklahoma State Department of Health, limited to records of or concerning the Pittsburg County Health Department and its staff",
  "officers, the county health department’s administrators and staff, attorneys and other representatives",
  [COMMS.format(who="James Schulz, Juli Montgomery, or any other Pittsburg County Health Department employee, or any Department official concerning the county health department’s role"),
   "<b>The committee seat.</b> All records created or received by James Schulz as the county health department’s representative on the PCDC Tax Incentive District Review Committee: agendas, packets, drafts, projections, counsel’s questions and the developer’s responses, and his notes or summaries.",
   "<b>Public health.</b> Any assessment, inquiry, memorandum or correspondence by the Department or the county health department about the project’s water use, wastewater, noise, air quality, cooling fluids, construction workforce housing or emergency planning.",
   "<b>What the department was given.</b> Every document the developer, its advisers or the county’s counsel provided to the county health department, including the projected revenue reported in May 2026 as about $600,000 a year, and any Tax Incentive Agreement draft sent for review.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the Department, the county health department or any employee and any party named in item 1."],
  note="County health departments are units of the State Department of Health, so the request goes to the Department’s open records office on its form, with a copy to the regional director so the local file is pulled at once.")

letter(10, "Pittsburg County Assessor",
  ["Cathy Ridenour, County Assessor",
   "115 E. Carl Albert Parkway, McAlester, OK 74501 · cathy.ridenour@pittsburgcountyok.gov · 918-423-4726"],
  [],
  "Open Records Act request — valuation, base value and district boundaries for the Emerald ProjectCo incentive districts",
  "the Office of the County Assessor of Pittsburg County",
  "officers, deputies and staff, attorneys and other representatives",
  [COMMS.format(who="the Assessor or any deputy or employee"),
   "<b>Base value and boundaries.</b> Every record about the 1 January 2026 base value date, the parcels and legal descriptions of Incentive District No. 1 and No. 2 in Sections 25, 26, 27, 33, 34 and 35 of Township 3 North, Range 13 East, the maps prepared or received for them, and the assessed values of those parcels for tax years 2024, 2025 and 2026.",
   "<b>Method.</b> Any memorandum, guidance, correspondence or worksheet on how data center real and personal property would be valued and depreciated, including the five-year replacement schedule discussed at the committee’s meeting of 3 February 2026, any Oklahoma Tax Commission guidance relied on, and anything on eligibility under 68 O.S. § 2902.",
   "<b>The 7 April 2026 meeting.</b> Notes, summaries or follow-up by Lindsey Naush or any other employee who attended the committee’s meeting of 7 April 2026.",
   "<b>Ownership.</b> The current ownership record and any change of ownership recorded since 1 January 2025 for every parcel in the six sections named above, with the grantee name and recording reference.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the Assessor or any employee and any party named in item 1."])

letter(11, "Pittsburg County Clerk, land records",
  ["Hope Trammell, County Clerk, land records",
   "115 E. Carl Albert Parkway, McAlester, OK 74501 · countyclerk@pittsburgcountyok.gov · 918-423-6865"],
  [],
  "Open Records Act request — recorded instruments concerning the Emerald ProjectCo site south of Kiowa",
  "the County Clerk’s land records",
  "deputies and staff",
  ["<b>By party.</b> A copy of every instrument recorded from 1 January 2025 in which any of the following is grantor or grantee: Emerald ProjectCo Inc.; IREN Limited; Iris Energy Limited; IE US Holdings Inc.; IE US Development Holdings 3 Inc.; IE US Hardware 1 Inc., 2 Inc., 3 Inc. or 4 Inc.; Black Mountain Energy Storage; or any entity whose name contains “Emerald” or “IREN”.",
   "<b>By land.</b> A copy of every deed, option, memorandum of option, contract for deed, easement, right-of-way, affidavit, lien or plat recorded from 1 January 2025 that affects any land in Sections 25, 26, 27, 33, 34 or 35 of Township 3 North, Range 13 East.",
   "<b>The index.</b> Before copying, I would like to inspect the grantor/grantee index and the tract index for those names and sections, which § 24A.5(4) makes available for inspection, so that the copy order is limited to what is relevant."],
  opening=("Under the Oklahoma Open Records Act, 51 O.S. § 24A.1 et seq., and 19 O.S. § 284 as to recorded instruments, I request to inspect and obtain copies of the following records of the County Clerk’s land records."),
  closing="<b>Fees.</b> I will pay the statutory per-page fee for copies and for any certification I ask for at the counter. Please tell me whether the index is available on the office’s public terminals so that I can do the inspection in person.",
  note="This is an inspection request rather than a search: the indexes are public by statute and the counter is the fastest route. Certify only the deeds that end up on the site.")

letter(12, "Oklahoma Department of Commerce",
  ["Chase Horn, Public Information Coordinator, Oklahoma Department of Commerce",
   "301 NW 63rd Street, Suite 300, Oklahoma City, OK 73116 · Chase.Horn@okcommerce.gov · 405-815-6552"],
  [],
  "Open Records Act request — IREN Limited / Emerald ProjectCo Inc. data center project in Pittsburg County (“Project Emerald”)",
  "the Oklahoma Department of Commerce",
  "officers, business development, site selection and incentive staff, regional representatives, attorneys, contractors and other representatives",
  ["<b>The project file.</b> Every prospect, project, site-selection or incentive file, under any code name including “Project Emerald,” concerning a data center or AI computing facility in Pittsburg County or near Kiowa, or concerning IREN Limited, Iris Energy, Emerald ProjectCo Inc. or any IE US entity, from 1 January 2024.",
   COMMS.format(who="the Department, any employee, contractor or regional representative") + " Include communications with site-selection consultants acting for the company, with Public Service Company of Oklahoma, with the Governor’s office, with any legislator, with Pittsburg County or its counsel, and with the Pittsburg County Economic Development Authority.",
   "<b>Incentives.</b> Every application, estimate, model, offer letter, term sheet or approval concerning a state incentive for the project, including Quality Jobs, investment or new jobs tax credits, the ad valorem reimbursement fund under 62 O.S. § 193, training funds, or any discretionary inducement, and any calculation of the state’s cost.",
   "<b>Visits and meetings.</b> Calendars, itineraries, briefing papers, attendance lists and notes for any site visit, meeting or call with the company or its advisers about the project.",
   "<b>Confidentiality.</b> Any non-disclosure, confidentiality or exclusivity agreement, or request for one, involving the Department and any party named in item 2."],
  start="1 January 2024",
  extra_withhold=" Section 24A.10(B) allows the prospective location of a business to be kept confidential only “prior to public disclosure of such prospect.” The county placed this project on a public agenda on 7 November 2025 and the company announced it to investors on 5 February 2026, so that exemption has expired. Section 24A.10(C) is permissive and reaches only the business plans, feasibility studies, financing proposals, marketing plans, financial statements and trade secrets the company itself submitted; if you rely on it, please identify each document withheld and release everything else, including the Department’s own correspondence and calculations.")

letter(13, "Oklahoma Water Resources Board",
  ["Sara Gibson, General Counsel, Oklahoma Water Resources Board",
   "3800 N. Classen Boulevard, Oklahoma City, OK 73118 · Sara.Gibson@owrb.ok.gov · 405-530-8802"],
  [],
  "Open Records Act request — water for the proposed IREN / Emerald ProjectCo data center south of Kiowa, Pittsburg County",
  "the Oklahoma Water Resources Board",
  "officers, water rights, planning and financial assistance staff, attorneys and other representatives",
  ["<b>Applications and permits.</b> Every application, permit, provisional temporary permit, amendment, pre-application meeting record or inquiry, from 1 January 2024, for stream water or groundwater in Pittsburg County by or on behalf of IREN Limited, Iris Energy, Emerald ProjectCo Inc., any IE US entity, Black Mountain Energy Storage, Tipton Capital, or any applicant describing a data center, AI computing or cooling use near Kiowa.",
   COMMS.format(who="the Board or any employee") + " Include communications with the City of McAlester or its Public Works Authority about the proposed sale of six million gallons a day of raw water, and with the Town of Kiowa, Rural Water District No. 11, the Pittsburg County Water Authority or Pittsburg County about serving the project.",
   "<b>Supply and planning.</b> Any analysis, memorandum or correspondence on the capacity of the McAlester, Kiowa or Rural Water District No. 11 systems, or of the relevant stream system or aquifer, to supply the project, and any financial-assistance application by any of those systems that refers to it.",
   "<b>SB 259.</b> Any guidance, analysis or correspondence about how the Groundwater Modernization Act, effective 1 November 2026, applies to this project."],
  start="1 January 2024")

letter(14, "Oklahoma Department of Environmental Quality",
  ["Central Records, Oklahoma Department of Environmental Quality (on the Central Records Request Form)",
   "PO Box 1677, Oklahoma City, OK 73101-1677 · 707 N. Robinson, 2nd Floor, Oklahoma City, OK 73102 · 405-702-1188"],
  [],
  "Records request — proposed IREN / Emerald ProjectCo data center, Sections 25–27 and 33–35, T3N R13E, Pittsburg County (Water Quality, Air Quality, Land Protection and Environmental Complaints & Local Services divisions)",
  "the Oklahoma Department of Environmental Quality",
  "officers, division staff, attorneys and other representatives",
  ["<b>Permits and applications.</b> Every application, pre-application meeting record, permit, authorization, notice of intent or determination, from 1 January 2024, by or on behalf of IREN Limited, Iris Energy, Emerald ProjectCo Inc., any IE US entity, Black Mountain Energy Storage or Tipton Capital, or for any facility described as a data center or AI computing facility near Kiowa in Pittsburg County, under the air quality, construction stormwater, industrial wastewater, underground injection, solid waste or public water supply programs.",
   "<b>Public water supply.</b> Any capacity development review, new-service or engineering-report approval, or correspondence concerning the ability of the Kiowa Public Works Authority (OK3006106 or as identified), Pittsburg County Rural Water District No. 11 (OK3006105) or the City of McAlester to serve the project, and any correspondence with those systems that refers to it.",
   COMMS.format(who="the Department or any employee"),
   "<b>Complaints.</b> Any complaint, inquiry or inspection record concerning the site or the project."],
  start="1 January 2024",
  note="DEQ’s form asks for a date range, a facility identifier, the county and the division. There is no facility ID yet; give the county, the sections and the party names, and tick all four divisions.")

letter(15, "Oklahoma Department of Transportation",
  ["Office of General Counsel, Oklahoma Department of Transportation (open records)",
   "200 NE 21st Street, Oklahoma City, OK 73105 · jpostman@odot.org · alayton@odot.org · 405-521-4698 · or through the GovQA portal at odot.govqa.us"],
  [],
  "Open Records Act request — US-69 access and right-of-way for the proposed IREN / Emerald ProjectCo data center south of Kiowa, Pittsburg County",
  "the Oklahoma Department of Transportation",
  "officers, Division 2 and right-of-way, traffic and permits staff, attorneys and other representatives",
  ["<b>Access and permits.</b> Every driveway or access permit application, utility or encroachment permit application, right-of-way or easement request, and related determination, from 1 January 2025, for US-69 or any state highway adjoining Sections 25, 26, 27, 33, 34 or 35 of Township 3 North, Range 13 East, by or on behalf of IREN Limited, Emerald ProjectCo Inc., any IE US entity, Black Mountain Energy Storage, Public Service Company of Oklahoma in connection with the project, or any contractor or engineer acting for them.",
   "<b>Traffic and improvements.</b> Any traffic impact study, turn-lane, signal or interchange analysis, construction-traffic plan or improvement request concerning the project, and any communication with Pittsburg County, Commissioner Haynes’s district or the developer about road improvements for construction, which the developer told the county’s committee on 3 February 2026 it would “discuss with the Commissioner.”",
   COMMS.format(who="the Department or any employee")])

# letter 16 is the FEDERAL dict below


# the federal letter is written out rather than templated, since its statute and clauses differ
FEDERAL = dict(n=16, title="McAlester Army Ammunition Plant (federal Freedom of Information Act)",
  to=["Freedom of Information Act Officer, U.S. Army, through the Army FOIA portal (foia.army.mil → Submit a FOIA request), for records of McAlester Army Ammunition Plant, Joint Munitions Command, Army Materiel Command",
      "Army Records Management Directorate, 9301 Chapek Road, Building 1458, Fort Belvoir, VA 22060 · 571-515-0306"],
  cc=["Public Affairs Office, McAlester Army Ammunition Plant, 1 C Tree Road, McAlester, OK 74501 · usarmy.mcalester.usamc.mbx.pa@army.mil · 918-420-6591, with a request to forward to the installation FOIA officer"],
  re="Freedom of Information Act request — McAlester Army Ammunition Plant records concerning the proposed IREN / Emerald ProjectCo data center south of Kiowa, Oklahoma",
  paras=[
   "Under the Freedom of Information Act, 5 U.S.C. § 552, I request copies of the following records of McAlester Army Ammunition Plant (MCAAP), including records of its command group and of Brian D. Lott, Civilian Deputy to the Commander, who attended the Pittsburg County tax incentive district review committee’s meeting of 3 February 2026 concerning this project.",
   "<b>1. Communications.</b> All emails, memoranda, letters, text messages on government devices, meeting notes, calendar entries, briefing slides and read-aheads, from 1 January 2025 to the date of your search, that refer to any of: Emerald ProjectCo Inc.; “Project Emerald” or “Emerald”; IREN, IREN Limited, Iris Energy or any affiliate; Jason Date, Evan Horn, Marat Ahmad or any other IREN representative; Black Mountain Energy Storage; Tipton Capital, Ernst & Young or ISB Group in connection with the project; Floyd & Driver PLLC or David Floyd; Public Service Company of Oklahoma in connection with the project; the Pittsburg County Board of County Commissioners or its tax incentive district review committee; or a data center or AI computing facility near Kiowa, Oklahoma.",
   "<b>2. The installation’s interest.</b> Any assessment, memorandum, staff study or correspondence on the project’s effect on MCAAP: electrical supply and Public Service Company of Oklahoma capacity, water supply, transportation on US-69, encroachment or compatible use, the Army Compatible Use Buffer or any Joint Land Use Study, explosive safety arcs, workforce or housing, and any position the installation or Joint Munitions Command took or was asked to take.",
   "<b>3. Meetings.</b> Records of Mr. Lott’s and any other MCAAP official’s attendance at, or briefings before or after, the review committee’s meetings and the public hearings of 8 and 22 June 2026, including any report up the chain of command.",
   "<b>4. Contacts with the company.</b> Any communication between MCAAP or Joint Munitions Command and IREN, Emerald ProjectCo or their representatives, and any visit by them to the installation.",
   "<b>Format.</b> Please provide records electronically, in native format with attachments where possible, and on a rolling basis.",
   "<b>Fees and fee waiver.</b> I am not a commercial requester. I request a waiver of fees under 5 U.S.C. § 552(a)(4)(A)(iii): disclosure is in the public interest because it will contribute significantly to public understanding of a federal installation’s role in a proposed $25 billion-per-phase private development next to it, which the county is being asked to subsidise; the records will be published in full at petition.mcalester.net, a public information site on the proposal, and I have no commercial interest. If the waiver is denied, please treat me as an “other” requester and tell me before incurring fees above $50.",
   "<b>Withholding.</b> If any record or portion is withheld, please state the exemption relied on for each, release all reasonably segregable non-exempt portions as § 552(b) requires, and identify the volume withheld. Factual material in briefings and notes is not protected by the deliberative-process privilege, and the names and official actions of federal officials acting in their official capacity are not protected by Exemption 6.",
   "<b>Response.</b> The Act requires a determination within 20 working days (§ 552(a)(6)(A)). Please acknowledge receipt with a tracking number, and tell me the estimated completion date if the request is placed in a queue. I am happy to discuss scope by phone.",
  ],
  note="Federal, not Oklahoma: FOIA has its own clock, fee categories and exemptions. The Army portal assigns the request to the right command; the copy to the plant’s Public Affairs office makes sure the installation knows it is coming.")

L.append(FEDERAL)

# Mailing addresses for the DocuPost CSV: 40-character fields, 2-letter state, 5-digit ZIP, one row per
# letter, plus the copies worth posting on paper. address2 is optional; company carries the body's name.
MAIL = {
    1: dict(name="Hope Trammell, County Clerk", company="Pittsburg County", address="PO Box 3304", address2="", city="McAlester", state="OK", zip="74501"),
    2: dict(name="Cora Middleton, City Clerk", company="City of McAlester", address="PO Box 578", address2="", city="McAlester", state="OK", zip="74502"),
    3: dict(name="Sam Rhyne, Superintendent", company="Kiowa Public Schools", address="PO Box 6", address2="", city="Kiowa", state="OK", zip="74553"),
    4: dict(name="Kristina Burgett, Town Clerk", company="Town of Kiowa", address="PO Box 69", address2="", city="Kiowa", state="OK", zip="74553"),
    5: dict(name="Candice Crutchfield, Chair", company="Pittsburg County RWD No. 11", address="515 E Cherokee", address2="", city="McAlester", state="OK", zip="74501"),
    6: dict(name="Hope Trammell, County Clerk", company="Pittsburg County EDA and PCWA", address="PO Box 3304", address2="", city="McAlester", state="OK", zip="74501"),
    7: dict(name="Shelley Free, Superintendent", company="Kiamichi Technology Centers", address="1004 Highway 2 North", address2="", city="Wilburton", state="OK", zip="74578"),
    8: dict(name="Michael Hull, Executive Director", company="Southeast Oklahoma Library System", address="2820 N Main St", address2="", city="McAlester", state="OK", zip="74501"),
    9: dict(name="Open Records", company="Oklahoma State Department of Health", address="123 Robert S. Kerr Ave", address2="Suite 1702", city="Oklahoma City", state="OK", zip="73102"),
    10: dict(name="Cathy Ridenour, County Assessor", company="Pittsburg County", address="115 E Carl Albert Pkwy", address2="", city="McAlester", state="OK", zip="74501"),
    11: dict(name="Hope Trammell, County Clerk", company="Pittsburg County, Land Records", address="115 E Carl Albert Pkwy", address2="", city="McAlester", state="OK", zip="74501"),
    12: dict(name="Chase Horn, Public Info Coordinator", company="Oklahoma Department of Commerce", address="301 NW 63rd St", address2="Suite 300", city="Oklahoma City", state="OK", zip="73116"),
    13: dict(name="Sara Gibson, General Counsel", company="Oklahoma Water Resources Board", address="3800 N Classen Blvd", address2="", city="Oklahoma City", state="OK", zip="73118"),
    14: dict(name="Central Records", company="Oklahoma Dept of Environmental Quality", address="PO Box 1677", address2="", city="Oklahoma City", state="OK", zip="73101"),
    15: dict(name="Office of General Counsel", company="Oklahoma Department of Transportation", address="200 NE 21st St", address2="", city="Oklahoma City", state="OK", zip="73105"),
    16: dict(name="FOIA Officer", company="Army Records Management Directorate", address="9301 Chapek Road", address2="Building 1458", city="Fort Belvoir", state="VA", zip="22060"),
}
COPIES = [  # paper copies worth sending alongside a letter; same PDF, flagged role=copy in the CSV
    (1, dict(name="Board of County Commissioners", company="Pittsburg County, Room 100", address="115 E Carl Albert Pkwy", address2="", city="McAlester", state="OK", zip="74501")),
    (1, dict(name="Mike Haynes, Commissioner", company="Pittsburg County District 2", address="615 Pittsburg Road", address2="", city="Pittsburg", state="OK", zip="74560")),
    (9, dict(name="Juli Montgomery, Regional Director", company="Pittsburg County Health Department", address="1400 E College Ave", address2="", city="McAlester", state="OK", zip="74501")),
    (16, dict(name="Public Affairs Office", company="McAlester Army Ammunition Plant", address="1 C Tree Road", address2="", city="McAlester", state="OK", zip="74501")),
]
SLUGS = {1: "county-board-and-committee", 2: "city-of-mcalester", 3: "kiowa-public-schools", 4: "town-of-kiowa", 5: "rural-water-district-11",
         6: "county-eda-and-water-authority", 7: "kiamichi-technology-center", 8: "library-system", 9: "health-department-osdh", 10: "county-assessor",
         11: "county-clerk-land-records", 12: "dept-of-commerce", 13: "water-resources-board", 14: "deq", 15: "odot", 16: "mcaap-army-foia"}

def letters() -> list[dict]:
    return sorted(L, key=lambda x: x["n"])
