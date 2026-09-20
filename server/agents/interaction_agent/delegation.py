"""Validate explicit routing intent before logging or starting a worker."""


def resolve_delegation(roster, agent_name, instructions, action):
    if action not in ('reuse', 'create'):
        raise ValueError('action must explicitly be reuse or create')
    if not isinstance(agent_name, str) or not agent_name.strip():
        raise ValueError('agent_name must be a nonempty exact name')
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError('instructions must be nonempty text')
    if action == 'reuse':
        if not roster.contains(agent_name):
            raise ValueError('Existing agent not found. Search for its exact name; no agent was created.')
        return False
    if not roster.add_agent(agent_name):
        raise ValueError('Agent already exists. Use action=reuse with its exact name.')
    return True
