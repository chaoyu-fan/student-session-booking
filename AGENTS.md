# Server Agent instructions — student-session-booking

## Goal
Deliver a **working, simplified Chinese H5 appointment website** for one school counselor and students. The website does not require student logins, emails, phone numbers, Feishu, or WeChat in v1. The booking confirmation page itself is the source of truth.

## Repository state and scope
- Code: Flask web app (`app/web.py`), SQLite (`app/storage.py`), calendar rules (`app/schedule.py`), Caddy HTTPS.
- No Docker deployment has been verified on the target server. This repository is an MVP requiring server-side validation.
- Do **not** replace this with Nextcloud Calendar, which requires email confirmation.
- Do not add complex notifications, user identity, AI, analytics, student psychological notes, or access to existing services.

## Work order
1. Read README.md, docs/ACCEPTANCE.md, docs/PRIVACY.md, docs/OPERATIONS.md.
2. Inspect OS, Docker, disk, current 80/443 users, DNS and host firewall. **Never interrupt existing services without permission.**
3. Review dependencies and inspect this source code for security issues; tests are smoke tests, not an independent security audit.
4. Run `python3 -m unittest discover -s tests -v` after installing `requirements.txt` into a disposable virtual environment. Do not use genuine student data.
5. If the host has no conflicting HTTP proxy, execute `./scripts/init.sh` once, edit `.env` based on teacher-approved domain and schedule, then `./scripts/preflight.sh`, `./scripts/deploy.sh`, and `./scripts/doctor.sh`.
6. First enter the teacher's actual class periods and bell schedule in `/admin`, with correct days and class periods. Never treat bundled reference bell times as exact. Verify public booking stays closed until activation and recurring classes are protected after activation. If supplied with a real timetable JSON, import locally (not to public GitHub) using `scripts/import_local_timetable.py`.
7. Test successful booking, refusal of same-slot double booking, half-hour-overlap block refusal, manual walk-in, cancellation, admin password, unauthorized access, HTTPS, and mobile usability. Record evidence *without private student information*.
8. Perform backup then restore **to a disposable test database**, document the result. Never restore over production without authorization.
9. Hand over real DNS URL, admin credential through a private secure channel, the exact image versions / git revision, and an operations runbook.

## Safety and correctness constraints
- Never commit `.env`, SQLite databases, passwords, backup files or student records, or teacher-specific timetable files. The GitHub repo is public by the owner’s explicit choice; only source, tests, and sanitized configuration templates belong in it.
- Never run `docker compose down -v`, `docker volume prune`, broad `rm -rf`, or delete an unknown production volume.
- Never open the database port to the public Internet; SQLite has no separate network port.
- Use synthetic names for tests. Launch to real students only after school authorization and teacher acceptance.
- Children can still be impersonated or spammed: no-login cannot prove student identity. Consider teacher-approved access code and communicate this limitation. Do not collect counseling content.
- Any custom Feishu integration is **phase 2** and requires that the school uses Feishu and grants the necessary permissions. No Feishu tokens in Git.

## Acceptance gates
See `docs/ACCEPTANCE.md`. Stop and report blockers if DNS, ports, school permission, backups, or tests are unavailable. Do not claim success from container health alone.
