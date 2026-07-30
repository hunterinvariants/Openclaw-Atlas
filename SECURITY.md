# Security policy

Please report vulnerabilities privately through GitHub Security Advisories. Do
not include credentials, customer data, model-provider keys, or production
traces in issues or evaluation datasets.

ATLAS is an evaluation harness, not a security sandbox. The fake tool
environment never executes arbitrary dataset code. The OpenAI adapter exposes
only tools declared by a validated task and rejects undeclared tool names, but
it does make external API calls and is not a process, filesystem, network, or
credential boundary. Deploy real adapters inside independently enforced
isolation appropriate to their risk.

Supported security fixes target the latest tagged minor release.