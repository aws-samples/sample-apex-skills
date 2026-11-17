# Guided rules

A Guided skill is a solution skill where a script does not fit, such as eks-design and eks-build: it does the task by guiding the user step by step.

Guided adds no rule id of its own. It inherits Operator's rules, `operator.artifact-checks` included: the design, project or other artifact it produces passes its declared checks before you hand it over.
