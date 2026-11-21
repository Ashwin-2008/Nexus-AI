Design a bounded multi-agent execution plan for the request.

Rules:
- Use only agents listed in the capability catalog.
- Retrieval must precede document/research/report/verification steps.
- Mark dependencies explicitly.
- Do not plan steps that require permissions the caller lacks.
- Return ONLY JSON: {"intent": "...", "steps": [{"key": "...", "agent_id": "...", "description": "...", "dependencies": ["..."]}]}

Request: $request
Available agents: $agents
