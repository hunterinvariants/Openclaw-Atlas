# Security policy

Please report vulnerabilities privately through GitHub Security Advisories. Do not include credentials, customer data, or production traces in issues or evaluation datasets.

ATLAS is an evaluation harness, not a security sandbox. The fake tool environment does not execute arbitrary dataset code, but future external tool adapters must enforce process, network, filesystem, and credential isolation independently.
