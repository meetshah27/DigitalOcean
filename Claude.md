I'm in a timed interview (3 hours) for a SWE I role at DigitalOcean.
Task: 
Mandatory Environment Rules
To ensure your work is saved and evaluated correctly, you must adhere to the following operational constraints:

Stay in the Workspace: All development must occur inside the /workspaces directory within your IDE.
No Host Saving: Do not save code or assets to the host machine’s Desktop or Downloads folder. These areas are not bridged to the container; data saved there will be permanently lost when the session ends.
Final Submission: You must push your code and architecture diagram to a personal GitHub repository before the timer expires.
Session Cleanup: Sign out of all personal accounts (GitHub, Cursor, Browser) before handing back the workstation.
Logistics and Tooling
Item

Details

Time Limit

3 Hours

Supported Languages

Go, Python, Java, or TypeScript / Node.js.

(Standard extensions for YAML, Python, Go, and Java are highly recommended).

IDE Environment

VS Code or Cursor, bridged directly to a Ubuntu 24 Dockerized container.

AI Assistance

GitHub Copilot, Claude Code, and Cursor are permitted.

You are encouraged to use Chrome, documentation, and any AI tools to assist your development. You must sign in using your personal accounts and remain fully responsible for the review, architecture, and correctness of all generated outputs.

Permissions

You have passwordless sudo access to install additional dependencies via apt or brew.

Pre-Installed Utilities

GitHub CLI (gh), doctl, s3cmd, jq, yq, neovim, and core image processing libraries.

Project Objective
Summary: Build a production-ready REST API service that accepts a long URL, generates a shortened URL (alias), redirects users to the original URL, and returns metadata about the created short links.

Functional Expectations
At a minimum, your service should demonstrate:

Creation: Accept a long URL and generate a unique shortened URL.
Customization: Support either automatically generated short codes or user-defined custom aliases (with appropriate validation).
Redirection: Redirect users to the original URL when the shortened link is accessed.
Metadata & Retrieval: Return metadata about the shortened URL and allow the retrieval of metadata for an existing short URL
Engineering Expectations
Your solution should reflect what you believe constitutes a production-ready service. We require:

Architecture Flow Diagram: Include a diagram in your repository mapping the request lifecycle and data flow at a high level. This will serve as the anchor for your technical review.
Validation: Sensible error handling, input validation, and edge-case management.
Testing: Unit or integration tests that demonstrate correctness.
CI/CD: A basic pipeline configuration (e.g., GitHub Actions).
Documentation: A well-organized codebase and a README providing clear setup, execution, and testing instructions.
Extensions & Next Steps
If time permits, you are encouraged to expand on your solution:

Deployment: Deploy your service to DigitalOcean.
Customer-Centric Features: Add additional features you would expect a product like this to have, using your imagination and thinking from a customer's perspective.
Good luck. We look forward to reviewing your solution.
.

Stack: Python 3.11 + FastAPI + Pydantic v2. Storage: <SQLite | Postgres>.
Deploy: DigitalOcean App Platform (Dockerfile, GitHub autodeploy). Repo: <url>.
They evaluate: engineering quality, automated testing, automation/CI, operational excellence
(observability, configurability, scalability).

Working rules for this whole session:
1. Explain before writing. Before creating or editing ANY file, explain in plain words what you will write,
   where, and why — then wait for my "go". No code before my approval.
2. Small steps, one idea per commit. Run tests (and the app when relevant) before every push.
3. After each change: what changed, why, how it was verified, then 1 quick check question for me.
4. Simplest correct design; no speculative features. Explain any new dependency.
5. Never log user content, PII, or secrets. Never return internal error details to clients.
6. All tunable values come from environment config with safe defaults, validated at startup.
7. Keep a README "Decisions & trade-offs" section updated as we go.
8. When the build is complete, give me a code tour (see "Final code tour" in my prompts): request order,
   one file per stop, real line numbers, why each key line exists, an interview sentence, one check question.
   Wait for my answer before the next stop.