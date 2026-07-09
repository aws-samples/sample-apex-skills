.PHONY: scan scan-skills scan-devops-agent

scan: scan-skills scan-devops-agent

scan-skills:
	skillspector scan ./skills/ --no-llm -b misc/skillspector/skills-baseline.json

scan-devops-agent:
	skillspector scan ./devops-agent/ --no-llm -b misc/skillspector/devops-agent-baseline.json
