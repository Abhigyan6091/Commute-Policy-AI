# Two-minute demonstration

Prepare before recording: configure/start the app, seed policies, generate Company A employee, Company B employee and Company A admin tokens, copy COMPANY_A_v2.txt locally, and run evaluation yourself. Keep the actual evaluation report open. Do not show keys, signing secrets or bearer tokens in the recording. If evaluation or benchmarking has not been run, label that fact instead of showing invented results.

0:00–0:15: show the running UI and health endpoint. Explain that the documents and companies are fictional.

0:15–0:35: connect Company A and ask ‘When is a security escort mandatory?’ Show the after-8-PM rule with its conditions.

0:35–0:55: open the citation card; show document, section 8 and logical source page. Explain that answer wording is copied from the policy.

0:55–1:10: ask about personal bicycle purchase reimbursement. Show explicit not-covered behavior and the transport-desk fallback.

1:10–1:25: clear the session, connect Company B and ask the same escort question. Show its different after-10-PM rule.

1:25–1:40: ask for Company C's policy. Show the safe own-company/abstention result and explain that backend filters do not change. If demonstrating a direct override, show the rejected extra company_id parameter.

1:40–1:55: connect Company A admin, upload COMPANY_A_v2.txt, ask again and show after-9-PM with the new version. Precheck ingestion duration; if it exceeds the segment, use a clearly disclosed time cut rather than imply instant processing.

1:55–2:00: display actual evaluation status and measured latency only if available. State ‘not benchmarked’ when no real-provider benchmark exists.
