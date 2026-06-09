# Product Direction: Transfer Center Protocol Engine

The goal is not just a decision tree. The target product is closer to an electronic dispatch / transfer-center protocol system inspired by EMD guidecards and ProQA-style workflows, adapted for hospital transfer center operations.

## Core Concepts

- **Call case**: One transfer center call with caller, patient, facility, acuity, timestamps, and disposition.
- **Protocol set**: A collection of related pathways, such as STEMI / Quick Cath / NSTEMI.
- **Pathway**: A runnable workflow with questions, steps, required notifications, page formats, and destination guidance.
- **Concurrent tasks**: Urgent calls may require transport, specialist contact, registration, bed assignment, and team notification at the same time.
- **Timers**: Track protocol start, step completion, callback delays, transport ETA, escalation thresholds, and total case time.
- **Audit trail**: Every opened protocol, checked step, answer, note, timestamp, and user action should be recorded.

## MVP Milestones

1. **Pathway library**
   - Upload JSON pathways.
   - Validate pathway schema.
   - Version pathways.
   - Keep inactive/archive versions.

2. **Case workspace**
   - Create a case.
   - Add caller, patient, facility, acuity, callback numbers.
   - Open multiple pathways on one case.
   - Run pathway timers concurrently.

3. **Operational workflow**
   - Check off steps.
   - Capture completion timestamps.
   - Add notes to each step.
   - Flag delayed steps.
   - Show required contacts and page formats.

4. **Decision support**
   - Structured yes/no and single-choice questions.
   - Branching to disposition or next pathway.
   - Red-flag overrides for urgent escalation.
   - Required provider confirmation points.

5. **QA and reporting**
   - Export case summary.
   - Show timeline of actions.
   - Identify missing required steps.
   - Support supervisor review.

## Later Architecture

- Backend: FastAPI or .NET API.
- Database: PostgreSQL or SQL Server for shared hospital deployment; SQLite for local pilot.
- Frontend: React or Vue for richer guidecard interactions.
- Authentication: SSO / Azure AD if used in a hospital environment.
- Audit: immutable event log.
- Deployment: internal web app, Windows desktop wrapper, or Electron app.

## Important Safety Note

Clinical and operational protocol content should be owned, reviewed, versioned, and approved by the appropriate medical, operational, legal, and compliance stakeholders before live use.

